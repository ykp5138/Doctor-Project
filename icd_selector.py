"""Grounded ICD selection using model-selected IDs, never invented quotations."""
import hashlib
import json
import os
import re
import time
from pathlib import Path
import uuid

import requests

from icd_evidence import build_evidence_spans, validate_evidence_span, assertion_reason, tokens
from icd10_utils import is_complete_code, get_codes_for_range_input

MODEL = "llama3"
URL = "http://localhost:11434/api/generate"


def _supported(candidate, evidence):
    text_tokens = set(tokens(evidence["phrase"]))
    contexts = candidate.get("matched_concepts", [])
    if contexts and all(item.get("category") == "procedures_ordered" for item in contexts) and not candidate["code"].startswith("Z"):
        # Ordering an investigation is not the result of that investigation.
        target = " ".join(token for token in tokens(candidate["description"]) if token not in ("unspecified", "other"))
        if target not in " ".join(tokens(evidence["phrase"])):
            return False
    names = [candidate["description"]]
    ignore = set("a an the to of for in on and or is are was were with without patient has have had mild moderate severe unspecified other current mentioned diagnosis type".split())
    for name in names:
        relevant = {token for token in tokens(name) if not token.isdigit()} - ignore
        if relevant and relevant & text_tokens:
            return True
    # A medication/procedure similarity hit must not create an unstated disease
    # (e.g. multivitamin -> vitamin deficiency). Such queries can support relevant
    # encounter/current-use Z codes, but disease evidence needs clinical context.
    clinical = [item for item in contexts if item.get("category") in
                ("diagnoses_mentioned", "symptoms", "vitals_exam_findings", "history_relevant")]
    if candidate["code"].startswith("Z"):
        clinical = contexts
    if not contexts:
        clinical = [{"text": candidate.get("matched_query", "")}]
    for item in clinical:
        relevant = {token for token in tokens(item.get("text", "")) if not token.isdigit()} - ignore
        if relevant and relevant & text_tokens:
            return True
    return False


def _context_rejection(code, phrase):
    normalized = " ".join(tokens(phrase))
    diabetes_types = set(re.findall(r"\btype\s+([12])\s+diabetes\b", normalized))
    if (code.startswith("E10") and diabetes_types == {"2"}) or (code.startswith("E11") and diabetes_types == {"1"}):
        return "diabetes type conflicts with the supporting transcript span"
    if code[:1] in ("V", "W", "X", "Y"):
        injury = r"\b(injury|injured|fracture|fractured|broken|fell|fall|struck|trauma|accident|sprain|strain|wound|cut|laceration|contusion|burn|burned|poisoning|overdose)\b"
        if not re.search(injury, normalized):
            return "external cause code without a documented injury event"
    maternity = code.startswith(("O", "Z3A", "Z33", "Z34"))
    not_pregnant = re.search(r"\b(not|never|no longer)\s+(?:currently\s+)?pregnant\b", normalized)
    completed_pregnancy = re.search(r"\b(postpartum|delivery|delivered|childbirth|miscarriage|abortion|puerperium)\b", normalized)
    if maternity and not_pregnant and not completed_pregnancy:
        return "pregnancy code but the evidence explicitly says not pregnant"
    return None


def _direct_quote(candidate, spans, words):
    """Repair only an already selected code with its explicit, positive name."""
    names = [candidate["description"]]
    if candidate.get("matched_alias"):
        names.append(re.sub(r"\([^)]*\)", "", candidate["matched_alias"]))
    for span in spans:
        if _question_only(span["text"]):
            continue
        for name in names:
            target = " ".join(tokens(name))
            actual = " " + " ".join(tokens(span["text"])) + " "
            if target and " " + target + " " in actual and not assertion_reason(name, span["text"], candidate["code"]):
                evidence = validate_evidence_span(span["span_id"], spans, words)
                if evidence:
                    return evidence
    return None


def _question_only(phrase):
    return phrase.rstrip().endswith("?")


def suggest_icd(concepts, summary, words, code_range=None, *, retriever=None,
                retrieval_mode="enhanced", guardrail=None, post=None, diagnostics=None):
    """Return the existing UI shape and record observable validation decisions.

    This is selection support, not a guarantee of clinical/coding correctness.
    Exact diagnosis retrieval is an anchor; a code still requires model selection,
    a real transcript span, complete-code validation, and contextual guardrails.
    """
    started = time.perf_counter()
    trace = {"pipeline": "grounded-spans-v1", "retrieval_mode": retrieval_mode,
             "model": MODEL, "options": {"temperature": 0, "seed": 42, "num_ctx": 8192},
             "decisions": []}
    if diagnostics is not None:
        diagnostics.update(trace)
        trace = diagnostics
    if not words:
        trace["error"] = "No transcript words supplied; cannot ground evidence"
        return []
    if retriever is None:
        from icd10_retriever import get_retriever
        retriever = get_retriever()
    if retrieval_mode == "enhanced" and hasattr(retriever, "retrieve_for_concepts"):
        candidates = retriever.retrieve_for_concepts(concepts, top_k=8, max_candidates=25)
    else:
        from main import _flatten_concepts
        candidates = retriever.retrieve(_flatten_concepts(concepts), top_k=8)[:25]
    candidates = [item for item in candidates if is_complete_code(item["code"])]
    if code_range and code_range.strip():
        allowed = {item["code"].upper() for item in get_codes_for_range_input(code_range, max_codes=1000000)}
        candidates = [item for item in candidates if item["code"].upper() in allowed]
    trace["candidates"] = candidates
    if not candidates:
        trace["error"] = "No complete candidate codes in the requested range"
        return []
    spans = build_evidence_spans(words, concepts, candidates)
    trace["spans"] = spans
    if not spans:
        return []
    by_code = {item["code"].upper(): item for item in candidates}
    schema = {
        "type": "object", "properties": {"picks": {"type": "array", "maxItems": 8,
            "items": {"type": "object", "properties": {
                "code": {"type": "string", "enum": list(by_code)},
                "span_id": {"type": "string", "enum": [span["span_id"] for span in spans]},
            }, "required": ["code", "span_id"], "additionalProperties": False}}},
        "required": ["picks"], "additionalProperties": False,
    }
    candidate_lines = "\n".join(f'{item["code"]}: {item["description"]}' for item in candidates)
    span_lines = "\n".join(f'[{span["span_id"]}] {span["text"]}' for span in spans)
    prompt = f"""Select supported ICD-10-CM codes for THIS patient's current encounter.
Return JSON using the supplied schema. You must choose a code from CANDIDATES
and the ID of one TRANSCRIPT SPAN that supports that code. Do not write quotes,
paraphrase evidence, or invent IDs/codes. An exact candidate name does not prove
the patient has the condition: inspect the transcript context.

RULES:
- Select current diagnoses or symptoms explicitly supported for this patient.
- Reject negated, ruled-out, hypothetical, screening-only, resolved, and family
  diagnoses as current disease codes. Do not infer pregnancy from trying to conceive.
- Do not diagnose cancer from inflammation, injury from a test order, poisoning
  from routine medication use, or postoperative disease without an actual procedure.
- For routine ongoing medication use, a supported current-use Z code may apply.
- Prefer the most specific supported candidate; do not select several subtypes
  of the same condition or a broader duplicate. Do not invent unstated specificity.
- Social chat, weather, and hobbies are not diagnoses. Return {{"picks":[]}} if
  no candidate is clinically supported. An empty list is better than an unsupported code.
- Evidence IDs must come from spoken transcript spans. Concepts and summaries
  are generated context and are NOT evidence. Include clearly stated diagnoses
  when the supplied transcript supports them, even if other candidates are irrelevant.

CANDIDATES:
{candidate_lines}

GENERATED CONCEPTS (context only):
{json.dumps(concepts, ensure_ascii=False)}

GENERATED SUMMARY (context only):
{(summary or '')[:1600]}

TRANSCRIPT SPANS (verbatim; may cover early or late parts of the recording):
{span_lines}

Return only {{"picks":[{{"code":"<candidate code>","span_id":"<supporting span ID>"}}]}}.
"""
    trace["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
    request = {"model": MODEL, "prompt": prompt, "stream": False, "format": schema,
               "options": trace["options"]}
    try:
        response = (post or requests.post)(URL, json=request, timeout=120)
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("response", "").strip()
        trace["raw_response"] = raw
        parsed = json.loads(raw)
        picks = parsed.get("picks", []) if isinstance(parsed, dict) else parsed
        if not isinstance(picks, list):
            raise ValueError("Model reply did not contain a picks array")
    except (requests.RequestException, ValueError, TypeError) as exc:
        trace["error"] = str(exc)
        print(f"[icd-spans] selection failed: {type(exc).__name__}")
        return []
    suggestions = {}
    for pick in picks[:8]:
        if not isinstance(pick, dict):
            continue
        code = str(pick.get("code", "")).strip().upper()
        decision = {"code": code, "span_id": pick.get("span_id")}
        trace["decisions"].append(decision)
        if code not in by_code:
            decision["rejected"] = "code not in candidate set"
            continue
        candidate = by_code[code]
        evidence = validate_evidence_span(pick.get("span_id"), spans, words)
        if evidence is None:
            evidence = _direct_quote(candidate, spans, words)
            if evidence:
                decision["repaired"] = "used explicit verbatim diagnosis for selected code"
        if evidence is None:
            decision["rejected"] = "no valid transcript span"
            continue
        # The model may choose a nearby question or an unsupported short span
        # for the right code. Repair only that already chosen code, and only
        # from an explicit positive name/inclusion term in the actual transcript.
        if _question_only(evidence["phrase"]) or not _supported(candidate, evidence):
            repaired = _direct_quote(candidate, spans, words)
            if repaired:
                evidence = repaired
                decision["repaired"] = "used explicit verbatim diagnosis for selected code"
        reason = assertion_reason(candidate["description"], evidence["phrase"], code)
        if not reason and _question_only(evidence["phrase"]):
            reason = "a question alone does not confirm this diagnosis"
        if not reason:
            reason = _context_rejection(code, evidence["phrase"])
        if not reason and not _supported(candidate, evidence):
            reason = "evidence has no clinical term supporting this candidate"
        if not reason and guardrail:
            reason = guardrail(code, candidate["description"], evidence["phrase"], concepts)
        if reason:
            decision["rejected"] = reason
            continue
        decision["accepted"] = True
        if code not in suggestions:
            suggestions[code] = {"code": code, "description": candidate["description"], "evidence": []}
        if evidence not in suggestions[code]["evidence"]:
            suggestions[code]["evidence"].append(evidence)
    trace["seconds"] = round(time.perf_counter() - started, 3)
    print(f"[icd-spans] selected {list(suggestions)}; rejected "
          f"{[(item['code'], item['rejected']) for item in trace['decisions'] if 'rejected' in item]}")
    if os.getenv("ICD_DIAGNOSTICS", "").lower() in ("1", "true"):
        directory = Path(__file__).parent / "outputs" / "icd_diagnostics"
        directory.mkdir(parents=True, exist_ok=True)
        trace["prompt"] = prompt
        (directory / f"{uuid.uuid4().hex}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    return list(suggestions.values())
