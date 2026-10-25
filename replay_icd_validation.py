"""Revalidate recorded ICD model choices without retrieval or new inference.

Only synthetic evaluate_icd_accuracy.py reports are accepted. Recorded candidates
and raw model replies are reused, and the newly constructed prompt must match
the recorded prompt hash. Baseline rows are preserved, rather than re-executed.
Detailed reports stay in ignored outputs/ by default.
"""
import argparse
import contextlib
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path

from evaluate_icd_accuracy import BASELINE_REF, ROOT, make_words, score_selection, selection_error, summarize
from icd_eval_cases import build_cases, build_holdout_cases, build_context_cases


class ReplayError(ValueError):
    pass


def case_catalog():
    cases = build_cases() + build_holdout_cases() + build_context_cases()
    result = {case["name"]: case for case in cases}
    if len(result) != len(cases):
        raise ReplayError("The synthetic corpus contains duplicate case names")
    return result


def verify_case(row, catalog):
    case = catalog.get(row.get("case"))
    if case is None:
        raise ReplayError(f"Unknown synthetic case: {row.get('case')!r}")
    expected_hash = hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()
    if row.get("input_sha256") != expected_hash:
        raise ReplayError(f"Frozen input changed for case {case['name']!r}; new inference is required")
    return case


class RecordedRetriever:
    def __init__(self, candidates):
        self.candidates = candidates

    def retrieve_for_concepts(self, *args, **kwargs):
        return deepcopy(self.candidates)

    def retrieve(self, *args, **kwargs):
        return deepcopy(self.candidates)


class RecordedResponse:
    def __init__(self, raw):
        self.raw = raw

    def raise_for_status(self):
        return None

    def json(self):
        return {"response": self.raw}


def recorded_raw_response(row):
    raw = row.get("diagnostics", {}).get("raw_response")
    if isinstance(raw, str):
        return raw
    for generation in reversed(row.get("generations", [])):
        response = generation.get("response", {})
        if isinstance(response, dict) and isinstance(response.get("response"), str):
            return response["response"]
    return None


def serialized_request(request):
    return json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def replay_row(row, catalog=None):
    """Replay one enhanced row, refusing changed inputs or model prompts."""
    catalog = catalog if catalog is not None else case_catalog()
    case = verify_case(row, catalog)
    variant = row.get("variant")
    if variant == "legacy":
        result = deepcopy(row)
        result["replay"] = {"mode": "preserved_baseline", "new_inference": False}
        return result
    if variant not in ("enhanced_mean", "enhanced_cls", "spans_legacy"):
        raise ReplayError(f"Unsupported variant: {variant!r}")
    original_trace = row.get("diagnostics", {})
    candidates = original_trace.get("candidates")
    if not isinstance(candidates, list):
        raise ReplayError("Recorded enhanced row has no candidate list")
    expected_prompt = original_trace.get("prompt_sha256")
    raw = recorded_raw_response(row)
    recorded_generations = row.get("generations", [])
    expected_request = None
    if recorded_generations:
        if len(recorded_generations) != 1 or not isinstance(recorded_generations[0].get("request"), dict):
            raise ReplayError("Replay requires one full recorded request when a generation is present")
        expected_request = recorded_generations[0]["request"]
    early_empty = not candidates and expected_prompt is None and raw is None
    if not early_empty and (not isinstance(expected_prompt, str) or len(expected_prompt) != 64 or raw is None):
        raise ReplayError("Recorded enhanced row lacks a prompt hash or raw model reply")

    # Imports are lazy; no embedding/retrieval model is constructed. Both the
    # retriever and HTTP callback are supplied explicitly to the current selector.
    from icd_selector import suggest_icd
    from main import _guardrail_reject

    generations, validation_errors = [], []

    def reject(message):
        validation_errors.append(message)
        raise ReplayError(message)

    def recorded_post(url, *, json, **kwargs):
        prompt_hash = hashlib.sha256(json["prompt"].encode()).hexdigest()
        if prompt_hash != expected_prompt:
            reject("Current prompt differs from the recorded prompt; new inference is required")
        if expected_request is not None and serialized_request(json) != serialized_request(expected_request):
            reject("Current model request differs from the recorded request; new inference is required")
        if raw is None or generations:
            reject("Replay cannot issue an unrecorded model request")
        generations.append({"http_status": 200, "request": json, "response": {"response": raw}})
        return RecordedResponse(raw)

    words = make_words(case["transcript"])
    trace, logs = {}, io.StringIO()
    with contextlib.redirect_stdout(logs):
        selected = suggest_icd(case["concepts"], "", words, "", retriever=RecordedRetriever(candidates),
                               retrieval_mode=original_trace.get("retrieval_mode", "enhanced"),
                               guardrail=_guardrail_reject, post=recorded_post, diagnostics=trace)
    if validation_errors:
        raise ReplayError(validation_errors[0])
    if trace.get("prompt_sha256") != expected_prompt:
        raise ReplayError("Current prompt differs from the recorded prompt; new inference is required")
    if not early_empty and len(generations) != 1:
        raise ReplayError("Recorded model reply was not consumed exactly once")
    # suggest_icd catches ValueError, including ReplayError, while parsing. The
    # independent hash and consumption checks above prevent that from concealing
    # a mismatched prompt or an attempted unrecorded request.
    error = selection_error(variant, candidates, generations, logs.getvalue(), trace)
    score = score_selection(selected, case["expected_codes"], case["allowed_codes"], words, error)
    result = deepcopy(row)
    result.update(score)
    result.update(expected=sorted(case["expected_codes"]), allowed=sorted(case["allowed_codes"]),
                  error=error, diagnostics=trace, logs=logs.getvalue(), suggestions=selected,
                  replay={"mode": "current_postprocessing", "new_inference": False,
                          "prompt_sha256_verified": expected_prompt is not None,
                          "full_request_verified": expected_request is not None,
                          "request_sha256": hashlib.sha256(serialized_request(expected_request).encode()).hexdigest()
                              if expected_request is not None else None,
                          "early_empty": early_empty, "original_codes": row.get("codes", []),
                          "original_passed": row.get("passed"), "original_error": row.get("error")})
    return result


def replay_reports(inputs, destination):
    catalog = case_catalog()
    rows, groups = [], []
    for input_path in inputs:
        input_path = Path(input_path)
        if input_path.resolve() == Path(destination).resolve():
            raise ReplayError("Replay output must not overwrite an input report")
        content = input_path.read_bytes()
        original = json.loads(content.decode("utf-8-sig"))
        if original.get("synthetic_cases") is not True or original.get("retrieval_only"):
            raise ReplayError(f"{input_path} is not a synthetic selection report")
        if original.get("baseline_commit") != BASELINE_REF:
            raise ReplayError(f"{input_path} uses a different baseline commit")
        original_rows = original.get("rows")
        if not isinstance(original_rows, list) or not original_rows:
            raise ReplayError(f"{input_path} has no recorded selection rows")
        group_rows = []
        for original_row in original_rows:
            try:
                row = replay_row(original_row, catalog)
            except (ReplayError, TypeError, KeyError) as exc:
                row = deepcopy(original_row)
                row.update(codes=[], optional_codes=[], tp=0, fp=0, fn=len(row.get("expected", [])),
                           grounded=False, passed=False, error=f"Replay validation failed: {exc}",
                           replay={"mode": "rejected", "new_inference": False,
                                   "original_codes": original_row.get("codes", [])})
            row["original_report"] = str(input_path)
            group_rows.append(row)
            rows.append(row)
        groups.append({"input_path": str(input_path), "input_sha256": hashlib.sha256(content).hexdigest(),
                       "original_provenance": original.get("provenance"),
                       "original_summary": original.get("summary"),
                       "replayed_summary": summarize(group_rows)["summary"], "rows": len(group_rows)})
    source_names = ("replay_icd_validation.py", "evaluate_icd_accuracy.py", "icd_eval_cases.py", "main.py",
                    "icd_selector.py", "icd_evidence.py", "icd10_retriever.py", "icd10_utils.py")
    report = summarize(rows)
    report.update(replay_only=True, new_inference=False,
                  limitation="Recorded candidates and model choices were reused. Only current postprocessing was revalidated, with unchanged prompt hashes and full model requests wherever a generation was recorded. Raw-only inputs verify the prompt alone. Baseline rows were preserved. This is not a new retrieval or inference evaluation, or a general clinical accuracy estimate.",
                  replay_metadata={"created_utc": datetime.now(timezone.utc).isoformat(),
                                   "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                                     for name in source_names}},
                  groups=groups)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(destination)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/icd_accuracy/replayed-validation.json")
    args = parser.parse_args()
    report = replay_reports(args.inputs, args.output)
    print(json.dumps(report["summary"], indent=2))
    if any(row.get("replay", {}).get("mode") == "rejected" for row in report["rows"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
