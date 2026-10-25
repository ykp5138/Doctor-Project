"""Compare the saved selector and proposed variants on frozen synthetic cases.

Results are regression evidence, not a population/clinical accuracy guarantee.
No speech or paid transcription APIs are called. All generations use local Ollama.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from unittest.mock import patch

import requests

from icd_eval_cases import build_cases, build_holdout_cases, build_context_cases
from icd_evidence import tokens

ROOT = Path(__file__).parent
BASELINE_REF = "5af8d8a32e35069ce7df4c3d0481c48974a2923e"


def baseline_module():
    directory = ROOT / "outputs" / "icd_accuracy" / "baseline_source"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "main.py"
    if not path.exists():
        result = subprocess.run(["git", "show", BASELINE_REF + ":main.py"], check=True, stdout=subprocess.PIPE, cwd=ROOT)
        path.write_bytes(result.stdout)
    spec = importlib.util.spec_from_file_location("saved_icd_baseline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_words(text):
    return [{"text": word, "start": index * .25, "end": (index + 1) * .25, "speaker": "SPEAKER_00"}
            for index, word in enumerate(text.split())]


def grounded_evidence(evidence, words):
    indices = evidence.get("word_indices", [])
    if not indices or any(type(i) is not int or i < 0 or i >= len(words) for i in indices):
        return False
    if indices != list(range(indices[0], indices[-1] + 1)):
        return False
    wanted = " ".join(tokens(evidence.get("phrase", "")))
    actual = " ".join(tokens(" ".join(words[index]["text"] for index in indices)))
    return bool(wanted) and (" " + wanted + " ") in (" " + actual + " ")


def score_selection(selected, expected, allowed, words, error=None):
    """Score required codes and explicitly report permitted optional selections."""
    expected, allowed = set(expected), set(allowed)
    codes = {item["code"] for item in selected}
    tp, fp, fn = len(codes & expected), len(codes - expected - allowed), len(expected - codes)
    grounded = all(bool(item.get("evidence")) and
                   all(grounded_evidence(evidence, words) for evidence in item["evidence"])
                   for item in selected)
    return dict(codes=sorted(codes), optional_codes=sorted((codes & allowed) - expected),
                tp=tp, fp=fp, fn=fn, grounded=grounded,
                passed=not error and fp == 0 and fn == 0 and grounded)


def _legacy_reply_parseable(raw):
    """Match the baseline's prose-tolerant parser, including a valid empty array."""
    if not isinstance(raw, str):
        return False
    decoder = json.JSONDecoder()
    index = 0
    while index < len(raw):
        if raw[index] in "[{":
            try:
                value, end = decoder.raw_decode(raw, index)
            except ValueError:
                index += 1
                continue
            if value == [] or isinstance(value, dict) and isinstance(value.get("code"), str):
                return True
            if isinstance(value, list) and value and all(isinstance(item, dict) and isinstance(item.get("code"), str) for item in value):
                return True
            index = max(end, index + 1)
        else:
            index += 1
    return False


def selection_error(variant, candidates, generations, logs, trace, raised_error=None):
    """Do not let an infrastructure/parse failure pass an expected-empty case."""
    if raised_error:
        return raised_error
    for generation in generations:
        if generation.get("error"):
            return generation["error"]
        if generation.get("http_status", 200) >= 400:
            return f"Ollama returned HTTP {generation['http_status']}"
        payload = generation.get("response")
        if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
            return "Ollama response did not contain a text generation"
    trace_error = trace.get("error")
    # Empty retrieval is a legitimate empty result; positive cases still lose
    # recall. It is not a transport/model parsing failure.
    if trace_error == "No complete candidate codes in the requested range" and not generations:
        return None
    if trace_error:
        return trace_error
    if "[icd-rag] Ollama error:" in logs:
        return "Baseline selector reported an Ollama failure"
    if candidates and not generations:
        return "Candidate codes existed but no generation was recorded"
    if variant == "legacy" and generations and not any(
            _legacy_reply_parseable(item["response"]["response"]) for item in generations):
        return "Baseline model reply contained no parseable code picks or empty array"
    return None


def collect_provenance(variants, repeats, cases, retrieval_only, holdout):
    files = ("main.py", "icd_selector.py", "icd_evidence.py", "icd10_retriever.py",
             "icd_embeddings.py", "icd10_utils.py", "icd_eval_cases.py", "evaluate_icd_accuracy.py")
    result = dict(python=platform.python_version(), variants=variants, repeats=repeats,
                  case_names=[case["name"] for case in cases], holdout=holdout,
                  retrieval_only=retrieval_only,
                  source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files})
    baseline_path = ROOT / "outputs/icd_accuracy/baseline_source/main.py"
    result["baseline_source_sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    baseline_git = subprocess.run(["git", "show", BASELINE_REF + ":main.py"], check=True,
                                  stdout=subprocess.PIPE, cwd=ROOT).stdout
    if hashlib.sha256(baseline_git).hexdigest() != result["baseline_source_sha256"]:
        raise ValueError("Saved baseline source differs from the stated Git commit")
    result["indexes"] = {}
    for directory in ("indexes", "indexes_sapbert", "indexes_sapbert_cls"):
        path = ROOT / directory / "icd10_metadata.json"
        if path.exists():
            result["indexes"][directory] = {"metadata_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    # These optional loopback-only reads describe the local model used. An old
    # Ollama without this metadata API must not prevent the regression run.
    for endpoint in ("version", "tags"):
        try:
            response = requests.get(f"http://localhost:11434/api/{endpoint}", timeout=2)
            response.raise_for_status()
            payload = response.json()
            result["ollama_" + endpoint] = payload if endpoint == "version" else [
                {key: model.get(key) for key in ("name", "digest", "modified_at")}
                for model in payload.get("models", []) if model.get("name", "").split(":")[0] == "llama3"]
        except (requests.RequestException, ValueError, TypeError) as exc:
            result["ollama_" + endpoint] = {"unavailable": type(exc).__name__}
    return result


def run(variants, repeats, destination, names=None, retrieval_only=False, holdout=False, context=False):
    if repeats < 1:
        raise ValueError("repeats must be positive")
    os.environ.setdefault("ICD_EMBEDDING_DEVICE", "cpu")
    os.environ.setdefault("ICD_LOCAL_MODELS_ONLY", "1")
    import torch
    torch.set_num_threads(4)
    import icd10_retriever as retrieval
    import main
    from icd_selector import suggest_icd
    baseline = baseline_module()
    print("Loading baseline embedding models on CPU...", flush=True)
    legacy = retrieval.HybridRetriever()
    models = {"legacy": legacy, "spans_legacy": legacy, "enhanced_mean": legacy}
    if "enhanced_cls" in variants:
        proposed = retrieval.HybridRetriever.__new__(retrieval.HybridRetriever)
        proposed.minilm = legacy.minilm
        proposed.sapbert = retrieval.ICD10Retriever("indexes_sapbert_cls")
        models["enhanced_cls"] = proposed
    corpus = build_context_cases() if context else build_holdout_cases() if holdout else build_cases()
    cases = [case for case in corpus if not names or case["name"] in names]
    if not cases or names and set(names) - {case["name"] for case in cases}:
        raise ValueError("No matching cases or an unknown case name was requested")
    provenance = collect_provenance(variants, repeats, cases, retrieval_only, holdout)
    provenance["context_cases"] = context
    rows = []
    destination.parent.mkdir(parents=True, exist_ok=True)
    original_post = requests.post
    for repeat in range(repeats):
        for case in cases:
            words = make_words(case["transcript"])
            frozen_hash = hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()
            for variant in variants:
                model = models[variant]
                if variant in ("legacy", "spans_legacy"):
                    candidates = model.retrieve(baseline._flatten_concepts(case["concepts"]), top_k=8)[:25]
                else:
                    candidates = model.retrieve_for_concepts(case["concepts"], top_k=8, max_candidates=25)
                expected = set(case["expected_codes"])
                candidate_codes = {item["code"] for item in candidates}
                candidate_order = [item["code"] for item in candidates]
                request_log = []
                def capture_post(*args, **kwargs):
                    entry = {"request": kwargs.get("json")}
                    request_log.append(entry)
                    try:
                        response = original_post(*args, **kwargs)
                        entry["http_status"] = response.status_code
                        entry["response"] = response.json()
                        return response
                    except (requests.RequestException, ValueError) as exc:
                        entry["error"] = repr(exc)
                        raise
                start = time.perf_counter()
                logs, trace = io.StringIO(), {}
                selected = []
                error = None
                if not retrieval_only:
                    try:
                        with contextlib.redirect_stdout(logs):
                            if variant == "legacy":
                                with patch.object(retrieval, "get_retriever", return_value=model), patch.object(baseline.requests, "post", side_effect=capture_post):
                                    selected = baseline._suggest_icd_rag(case["concepts"], "", words, "")
                            else:
                                selected = suggest_icd(case["concepts"], "", words, "", retriever=model,
                                                      retrieval_mode="legacy" if variant == "spans_legacy" else "enhanced",
                                                      guardrail=main._guardrail_reject, post=capture_post, diagnostics=trace)
                    except Exception as exc:
                        error = repr(exc)
                allowed = set(case["allowed_codes"])
                if not retrieval_only:
                    error = selection_error(variant, candidates, request_log, logs.getvalue(), trace, error)
                score = score_selection(selected, expected, allowed, words, error)
                row = dict(case=case["name"], variant=variant, repeat=repeat, input_sha256=frozen_hash,
                           **score, expected=sorted(expected), allowed=sorted(allowed),
                           candidate_hits=len(expected & candidate_codes), candidate_total=len(expected),
                           candidate_ranks=[candidate_order.index(code) + 1 if code in candidate_order else 0 for code in sorted(expected)],
                           candidate_codes=sorted(candidate_codes), seconds=round(time.perf_counter() - start, 3),
                           error=error, logs=logs.getvalue(), diagnostics=trace,
                           generations=request_log)
                rows.append(row)
                report = summarize(rows, retrieval_only, provenance)
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                temporary.replace(destination)
                state = f"retrieval {row['candidate_hits']}/{row['candidate_total']}" if retrieval_only else f"codes={row['codes']} expected={sorted(expected)} pass={row['passed']}"
                print(f"{variant:14} {case['name']:30} {state} ({row['seconds']}s)", flush=True)
    return summarize(rows, retrieval_only, provenance)


def paired_comparisons(rows):
    """Compare the same frozen case/repeat, so aggregate gains cannot hide losses."""
    if not any(row.get("variant") == "legacy" for row in rows):
        return {}
    by_variant = {}
    for row in rows:
        if not all(key in row for key in ("case", "input_sha256", "repeat")):
            continue
        key = (row["case"], row["input_sha256"], row["repeat"])
        variant_rows = by_variant.setdefault(row["variant"], {})
        if key in variant_rows:
            raise ValueError(f"Duplicate paired evaluation row for {row['variant']}: {key}")
        variant_rows[key] = row
    baseline = by_variant.get("legacy", {})
    result = {}
    for variant, proposed in by_variant.items():
        if variant == "legacy":
            continue
        common = set(baseline) & set(proposed)
        regressions, improvements = [], []
        both_passed = both_failed = 0
        for key in sorted(common):
            old, new = baseline[key], proposed[key]
            old_passed, new_passed = bool(old["passed"]), bool(new["passed"])
            detail = {"case": key[0], "input_sha256": key[1], "repeat": key[2],
                      "baseline_codes": old.get("codes", []), "proposed_codes": new.get("codes", []),
                      "baseline_error": old.get("error"), "proposed_error": new.get("error")}
            if old_passed and not new_passed:
                regressions.append(detail)
            elif not old_passed and new_passed:
                improvements.append(detail)
            elif old_passed:
                both_passed += 1
            else:
                both_failed += 1
        result[variant] = {"paired_runs": len(common), "regression_count": len(regressions),
                           "improvement_count": len(improvements), "both_passed": both_passed,
                           "both_failed": both_failed, "regressions": regressions,
                           "improvements": improvements,
                           "baseline_only_runs": len(set(baseline) - set(proposed)),
                           "proposed_only_runs": len(set(proposed) - set(baseline))}
    return result


def summarize(rows, retrieval_only=False, provenance=None):
    summaries = {}
    for variant in dict.fromkeys(row["variant"] for row in rows):
        subset = [row for row in rows if row["variant"] == variant]
        tp = sum(row["tp"] for row in subset)
        fp = sum(row["fp"] for row in subset)
        fn = sum(row["fn"] for row in subset)
        hits, total = sum(row["candidate_hits"] for row in subset), sum(row["candidate_total"] for row in subset)
        summaries[variant] = dict(runs=len(subset), passed=sum(row["candidate_hits"] == row["candidate_total"] if retrieval_only else row["passed"] for row in subset), tp=tp if not retrieval_only else None, fp=fp if not retrieval_only else None, fn=fn if not retrieval_only else None,
                                  precision=round(tp / (tp + fp), 4) if not retrieval_only and tp + fp else None,
                                  recall=round(tp / (tp + fn), 4) if not retrieval_only and tp + fn else None,
                                  optional_selected=sum(len(row.get("optional_codes", [])) for row in subset),
                                  candidate_recall=round(hits / total, 4) if total else None,
                                  retrieval_mrr=round(sum(1 / rank if rank else 0 for row in subset for rank in row.get("candidate_ranks", [])) / total, 4) if total else None,
                                  errors=sum(bool(row["error"]) for row in subset),
                                  ungrounded=sum(not row["grounded"] for row in subset))
    return dict(baseline_commit=BASELINE_REF, synthetic_cases=True,
                limitation="Synthetic software regression evaluation; not a clinician-validated estimate of general accuracy.",
                scoring="Recall requires every expected code. Explicitly allowed optional codes are reported separately and excluded from false positives and precision. Any other additional code is a false positive. Infrastructure and parse errors fail a selection case, including expected-empty cases.",
                comparison="Aggregate gains do not imply no regressions. Paired comparisons match case, input hash, and repeat; unpaired runs are reported separately.",
                provenance=provenance, retrieval_only=retrieval_only, summary=summaries,
                paired_comparisons={} if retrieval_only else paired_comparisons(rows), rows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", nargs="+", choices=("legacy", "spans_legacy", "enhanced_mean", "enhanced_cls"), default=["legacy", "enhanced_cls"])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--holdout", action="store_true")
    parser.add_argument("--context", action="store_true")
    parser.add_argument("--fail-on-regression", nargs="?", const="enhanced_cls",
                        choices=("spans_legacy", "enhanced_mean", "enhanced_cls"),
                        help="Exit 1 on paired regressions for VARIANT (enhanced_cls if omitted after the flag)")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/icd_accuracy/comparison.json")
    args = parser.parse_args()
    if args.holdout and args.context:
        parser.error("Choose either --holdout or --context")
    if args.fail_on_regression:
        if "legacy" not in args.variants or args.fail_on_regression not in args.variants:
            parser.error("--fail-on-regression requires legacy and the selected variant in --variants")
        if args.retrieval_only:
            parser.error("--fail-on-regression checks selection results and cannot use --retrieval-only")
    result = run(args.variants, args.repeats, args.output, args.cases, args.retrieval_only, args.holdout, args.context)
    print(json.dumps(result["summary"], indent=2), flush=True)
    if args.fail_on_regression:
        comparison = result.get("paired_comparisons", {}).get(args.fail_on_regression)
        if not comparison or not comparison["paired_runs"]:
            parser.error("No matching baseline/proposed selection runs were available")
        print(json.dumps({args.fail_on_regression: comparison}, indent=2), flush=True)
        if comparison["regression_count"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
