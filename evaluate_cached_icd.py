"""Check required codes against cached ASR words without re-running transcription.

This uses the cached WhisperX transcript, not a reconstructed/UI merged transcript.
Expected codes are required-code checks only: additional codes are unadjudicated,
so this report does not estimate precision or general clinical coding accuracy.
Model requests go only to the local Ollama service. Detailed local output may
contain transcript text and stays under the ignored outputs/ directory by default.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
from unittest.mock import patch

import requests

from evaluate_icd_accuracy import BASELINE_REF, ROOT, baseline_module, grounded_evidence


def load_cached(base):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", base) or base in (".", ".."):
        raise ValueError("--base must be a recording base name, not a path")
    transcript_path = ROOT / "outputs" / "whisperx" / f"{base}_full_output.json"
    concepts_path = ROOT / "outputs" / "kevin" / f"{base}_concepts.json"
    transcript_bytes = transcript_path.read_bytes()
    concepts_bytes = concepts_path.read_bytes()
    data = json.loads(transcript_bytes.decode("utf-8-sig"))
    segments = data.get("word_segments", [])
    if not isinstance(segments, list) or not segments:
        raise ValueError("Cached WhisperX output has no word_segments")
    if any(not isinstance(word, dict) for word in segments):
        raise ValueError("Cached word_segments must contain word objects")
    # Keep every ASR entry, including any empty word, so word indices do not move.
    words = [{**word, "text": str(word.get("word", word.get("text", "")))} for word in segments]
    concepts = json.loads(concepts_bytes.decode("utf-8-sig"))
    if not isinstance(concepts, dict):
        raise ValueError("Cached concepts must be an object")
    provenance = {
        "transcript_path": str(transcript_path.relative_to(ROOT)),
        "transcript_sha256": hashlib.sha256(transcript_bytes).hexdigest(),
        "concepts_path": str(concepts_path.relative_to(ROOT)),
        "concepts_sha256": hashlib.sha256(concepts_bytes).hexdigest(),
        "word_count": len(words),
    }
    return words, concepts, provenance


def summarize(rows):
    result = {}
    for variant in dict.fromkeys(row["variant"] for row in rows):
        subset = [row for row in rows if row["variant"] == variant]
        result[variant] = {
            "runs": len(subset),
            "required_codes_present": sum(row["required_codes_present"] for row in subset),
            "passed": sum(row["passed"] for row in subset),
            "errors": sum(bool(row["error"]) for row in subset),
            "ungrounded": sum(not row["grounded"] for row in subset),
        }
    return result


def run(base, expected_codes, repeats, destination, variants):
    words, concepts, provenance = load_cached(base)
    expected = {code.strip().upper() for code in expected_codes if code.strip()}
    if not expected or repeats < 1:
        raise ValueError("Supply at least one expected code and a positive repeat count")
    os.environ["ICD_EMBEDDING_DEVICE"] = "cpu"
    os.environ["ICD_LOCAL_MODELS_ONLY"] = "1"
    import torch
    torch.set_num_threads(4)
    import icd10_retriever as retrieval
    import main
    from icd_selector import suggest_icd

    baseline = baseline_module()
    legacy = retrieval.HybridRetriever()
    models = {"legacy": legacy, "enhanced_mean": legacy}
    if "enhanced_cls" in variants:
        proposed = retrieval.HybridRetriever.__new__(retrieval.HybridRetriever)
        proposed.minilm = legacy.minilm
        proposed.sapbert = retrieval.ICD10Retriever("indexes_sapbert_cls")
        models["enhanced_cls"] = proposed

    rows = []
    report = {
        "baseline_commit": BASELINE_REF,
        "recording_base": base,
        "transcript_source": "cached WhisperX word_segments; not the UI merged transcript",
        "input_provenance": provenance,
        "expected_codes": sorted(expected),
        "additional_codes": "Unadjudicated; neither counted correct nor counted false positive",
        "limitation": "Required-code and transcript-grounding check on one cached recording; not a precision or general accuracy estimate.",
        "summary_context": "Blank for every variant to compare identical cached inputs",
        "rows": rows,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    original_post = requests.post
    for repeat in range(repeats):
        for variant in variants:
            retriever = models[variant]
            generations, diagnostics = [], {}
            logs = io.StringIO()

            def capture_post(*args, **kwargs):
                generation = {"request": kwargs.get("json")}
                generations.append(generation)
                try:
                    response = original_post(*args, **kwargs)
                    generation["status_code"] = response.status_code
                    generation["response"] = response.json()
                    return response
                except Exception as exc:
                    generation["error"] = repr(exc)
                    raise

            started = time.perf_counter()
            selected, error = [], None
            try:
                with contextlib.redirect_stdout(logs):
                    if variant == "legacy":
                        with patch.object(retrieval, "get_retriever", return_value=retriever), patch.object(baseline.requests, "post", side_effect=capture_post):
                            selected = baseline._suggest_icd_rag(concepts, "", words, "")
                    else:
                        selected = suggest_icd(concepts, "", words, "", retriever=retriever,
                                               retrieval_mode="enhanced", guardrail=main._guardrail_reject,
                                               post=capture_post, diagnostics=diagnostics)
            except Exception as exc:
                error = repr(exc)
            error = error or diagnostics.get("error")
            failed_generations = [item for item in generations if item.get("error") or item.get("status_code", 200) >= 400]
            if failed_generations:
                error = error or "Local Ollama request failed; see generations"
            if "[icd-rag] Ollama error:" in logs.getvalue():
                error = error or "Legacy selector caught an Ollama error; see logs"
            codes = {item["code"] for item in selected}
            grounded = all(item.get("evidence") and all(grounded_evidence(evidence, words)
                            for evidence in item["evidence"]) for item in selected)
            present = expected <= codes
            row = {
                "variant": variant, "repeat": repeat,
                "codes": sorted(codes), "missing_required_codes": sorted(expected - codes),
                "unadjudicated_additional_codes": sorted(codes - expected),
                "required_codes_present": present,
                "grounded": grounded, "passed": present and grounded and not error,
                "error": error, "seconds": round(time.perf_counter() - started, 3),
                "suggestions": selected, "diagnostics": diagnostics,
                "logs": logs.getvalue(), "generations": generations,
            }
            rows.append(row)
            report["summary"] = summarize(rows)
            destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{variant:14} repeat={repeat + 1} codes={sorted(codes)} required={present} grounded={grounded} error={bool(error)}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--expected-code", action="append", required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--variants", nargs="+", choices=("legacy", "enhanced_mean", "enhanced_cls"), default=["legacy", "enhanced_mean", "enhanced_cls"])
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/icd_accuracy/cached-check.json")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    report = run(args.base, args.expected_code, args.repeats, args.output, args.variants)
    print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
