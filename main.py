from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import os
import sys
import subprocess
import uuid
import traceback
import json
import re
import datetime
import threading
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@app.get("/health")
def health():
    return {"ok": True}


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _run_downstream(whisper_out, assembly_out, keywords=None, patient_name=None):
    """
    Run the post-transcription pipeline on existing WhisperX/AssemblyAI output:
    Kevin merge + summary + structured concept extraction.

    Persists the concepts JSON next to the other kevin outputs and returns
    (words, summary, concepts). Shared by /transcribe and /replay so both stay
    in sync.
    """
    from kevin import merge_for_api, extract_clinical_concepts

    words, summary, final_words = merge_for_api(
        whisper_out, assembly_out, keywords=keywords, patient_name=patient_name
    )

    print("🔎 Extracting clinical concepts...")
    concepts = extract_clinical_concepts(final_words, keywords, patient_name)

    # Persist concepts JSON next to the other kevin outputs (_transcript.txt, _summary.txt)
    kevin_out_dir = os.path.join(BASE_DIR, "outputs", "kevin")
    os.makedirs(kevin_out_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(whisper_out))[0].replace("_full_output", "")
    concepts_path = os.path.join(kevin_out_dir, f"{base_name}_concepts.json")
    try:
        with open(concepts_path, "w", encoding="utf-8") as f:
            json.dump(concepts, f, indent=2)
    except Exception:
        traceback.print_exc()

    return words, summary, concepts


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    keywords: Optional[str] = Form(None),
    patient_name: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """
    Pipeline:
      1) Save uploaded audio with a UUID-prefixed name
      2) Run WhisperX  -> outputs/whisperx/{base}_full_output.json
      3) Run AssemblyAI -> outputs/assembly/{base}_confidence.json
      4) Merge with Kevin -> words list + summary text
      5) Return both to frontend
    """
    try:
        suffix = os.path.splitext(file.filename or "audio")[1] or ".mp3"
        base = f"{uuid.uuid4().hex}{suffix.replace('.', '_')}"
        audio_path = os.path.join(BASE_DIR, "audio", f"{base}{suffix}")

        content = await file.read()
        with open(audio_path, "wb") as f:
            f.write(content)

        py = sys.executable

        # Step 1: WhisperX
        print("🎙️ Running WhisperX...")
        subprocess.run(
            [py, os.path.join(BASE_DIR, "transcriber_scripts", "whisperX_transcriber.py"), audio_path],
            check=True,
            cwd=BASE_DIR,
        )
        whisper_out = os.path.join(BASE_DIR, "outputs", "whisperx", f"{base}_full_output.json")

        # Step 2: AssemblyAI
        print("🎙️ Running AssemblyAI...")
        subprocess.run(
            [py, os.path.join(BASE_DIR, "transcriber_scripts", "assemblyAI_transcriber.py"), audio_path],
            check=True,
            cwd=BASE_DIR,
        )
        assembly_out = os.path.join(BASE_DIR, "outputs", "assembly", f"{base}_confidence.json")

        # Step 3-4: Kevin merge + summary + structured concept extraction
        print("🧠 Running Kevin merge...")
        words, summary, concepts = _run_downstream(
            whisper_out, assembly_out, keywords=keywords, patient_name=patient_name
        )

        # Keep the audio by default so replay/snippet-playback works while developing.
        # Set DELETE_AUDIO=1 (production) to remove it after processing.
        if _truthy_env("DELETE_AUDIO"):
            try:
                os.remove(audio_path)
            except Exception:
                pass

        return {
            "words": words,
            "summary": summary,
            "concepts": concepts,
            "meta": {
                "filename": file.filename,
                "bytes": len(content),
                "base": base,  # so feedback records can trace back to this recording
            },
        }

    except subprocess.CalledProcessError as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline step failed: {e}")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class ReplayRequest(BaseModel):
    base: str
    keywords: Optional[str] = None
    patient_name: Optional[str] = None


@app.post("/replay")
def replay(req: ReplayRequest) -> Dict[str, Any]:
    """
    Dev/testing: re-run the downstream pipeline (Kevin merge + summary + concepts)
    on already-transcribed output, skipping the expensive WhisperX/AssemblyAI steps.

    Expects a `base` matching a cached pair:
      outputs/whisperx/{base}_full_output.json
      outputs/assembly/{base}_confidence.json
    Returns the same shape as /transcribe.
    """
    whisper_out = os.path.join(BASE_DIR, "outputs", "whisperx", f"{req.base}_full_output.json")
    assembly_out = os.path.join(BASE_DIR, "outputs", "assembly", f"{req.base}_confidence.json")

    missing = [os.path.basename(p) for p in (whisper_out, assembly_out) if not os.path.exists(p)]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"No cached transcription for base '{req.base}': missing {', '.join(missing)}",
        )

    try:
        print(f"♻️  Replaying base '{req.base}' (skipping transcription)...")
        words, summary, concepts = _run_downstream(
            whisper_out, assembly_out, keywords=req.keywords, patient_name=req.patient_name
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "words": words,
        "summary": summary,
        "concepts": concepts,
        "meta": {
            "base": req.base,
            "replay": True,
        },
    }


@app.get("/replay/list")
def replay_list() -> Dict[str, Any]:
    """List cached transcription bases available for /replay (scans outputs/whisperx/)."""
    whisper_dir = os.path.join(BASE_DIR, "outputs", "whisperx")
    suffix = "_full_output.json"
    bases = []
    if os.path.isdir(whisper_dir):
        for name in os.listdir(whisper_dir):
            if name.endswith(suffix):
                bases.append(name[: -len(suffix)])
    bases.sort()
    return {"bases": bases}


class RetrieveTestRequest(BaseModel):
    concepts: Dict[str, Any]
    top_k: int = 10


_CONCEPT_KEYS = [
    "symptoms",
    "diagnoses_mentioned",
    "medications_discussed",
    "procedures_ordered",
    "history_relevant",
    "vitals_exam_findings",
]


@app.post("/retrieve-test")
def retrieve_test(req: RetrieveTestRequest) -> Dict[str, Any]:
    """
    Diagnostic endpoint (Stage 2): semantic retrieval of candidate ICD-10-CM codes
    from an extracted concepts object. Not wired into suggestion yet — for testing
    retrieval quality in isolation.
    """
    # Flatten via the shared, field-aware helper (expands med/procedure terms).
    queries = _flatten_concepts(req.concepts)

    # Lazy import: loading the retriever pulls in the model + index, which is slow.
    # Keep it out of module scope so FastAPI startup stays fast — load on first use.
    try:
        from icd10_retriever import get_retriever
        retriever = get_retriever()
        candidates = retriever.retrieve(queries, top_k=req.top_k)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    return {"candidates": candidates[:30], "query_count": len(queries)}


def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, split on whitespace -> list of word tokens."""
    return [t for t in re.sub(r"[^\w\s]", " ", text.lower()).split() if t]


def _normalize_for_match(text: str) -> str:
    """Lowercased, punctuation-stripped, single-spaced form for substring matching."""
    return " ".join(_tokenize(text))


def _find_phrase_word_indices(phrase: str, words: list) -> List[int]:
    """
    Locate the transcript word indices that best match an evidence phrase.

    Slides a window the size of the phrase's tokens over the transcript words
    (both lowercased + punctuation-stripped) and scores each window by how many
    phrase tokens appear in order within it. Returns the indices of the best
    window (ties broken by earliest position), or [] if the best window matches
    fewer than 50% of the phrase tokens.

    Fixes the prior bug where evidence word_indices was always []: clicking an
    evidence row in the UI can now highlight the matching words and play the clip.
    """
    phrase_tokens = _tokenize(phrase)
    if not phrase_tokens or not words:
        return []

    # One representative token per transcript word, preserving index alignment.
    flat = []
    for w in words:
        toks = _tokenize(w.get("text", "") if isinstance(w, dict) else str(w))
        flat.append(toks[0] if toks else "")

    n = len(phrase_tokens)
    window = min(n, len(flat))
    if window == 0:
        return []

    best_score = 0
    best_i = -1
    for i in range(0, len(flat) - window + 1):
        p = 0  # in-order match pointer into phrase_tokens
        for tok in flat[i:i + window]:
            if p < n and tok == phrase_tokens[p]:
                p += 1
        if p > best_score:  # strict > => earliest window wins ties
            best_score = p
            best_i = i

    if best_i < 0 or (best_score / n) < 0.5:
        return []

    return list(range(best_i, best_i + window))


_EXPAND_FIELDS = {"medications_discussed", "procedures_ordered"}


def _flatten_concepts(concepts: dict) -> List[str]:
    """
    Flatten the six concept lists into a single query list.

    Terms from medications_discussed / procedures_ordered are run through
    expand_query_term (drug/procedure -> class use-phrase, brand -> generic) so
    long-term-use / encounter Z-codes surface. The other four fields (symptoms,
    diagnoses, history, exam findings) already retrieve well RAW and are left as-is.
    """
    from icd10_retriever import expand_query_term

    queries = []
    for key in _CONCEPT_KEYS:
        for item in (concepts.get(key) or []):
            if isinstance(item, str) and item.strip():
                term = item.strip()
                if key in _EXPAND_FIELDS:
                    term = expand_query_term(term)
                queries.append(term)
    return queries


_CONCEPT_LABELS = {
    "symptoms": "Symptoms",
    "diagnoses_mentioned": "Diagnoses mentioned",
    "medications_discussed": "Medications discussed",
    "procedures_ordered": "Procedures ordered",
    "history_relevant": "Relevant history",
    "vitals_exam_findings": "Vitals/exam findings",
}


def _parse_llm_code_picks(raw: str) -> List[Dict[str, Any]]:
    """
    Robustly extract code-pick dicts from an LLM response.

    llama3 sometimes emits MULTIPLE JSON arrays (e.g. one per line) or wraps the
    array in prose. A naive first-'[' to last-']' slice then spans several arrays
    and fails json.loads with "Extra data", silently yielding zero codes even when
    the model picked correctly. Instead, scan the whole string and merge the items
    of every valid JSON array (and any bare objects) via raw_decode.
    """
    items: List[Dict[str, Any]] = []
    decoder = json.JSONDecoder()
    i, n = 0, len(raw)
    while i < n:
        if raw[i] in "[{":
            try:
                val, end = decoder.raw_decode(raw, i)
            except json.JSONDecodeError:
                i += 1
                continue
            if isinstance(val, list):
                items.extend(x for x in val if isinstance(x, dict))
            elif isinstance(val, dict):
                items.append(val)
            i = max(end, i + 1)
        else:
            i += 1
    return items


# --- Deterministic guardrail (Stage 3) ----------------------------------------
# 8B LLMs ignore some negative constraints even with explicit prompt examples, so
# these rule-based filters run AFTER LLM selection + candidate validation to drop
# well-defined categorical errors. Each rule is its own function and listed in
# _GUARDRAIL_RULES; comment one out to disable it if it proves too aggressive.

_USE_WORDS = ("daily", "takes", "taking", "take ", " on ", "uses", "use ", "current",
              "regular", "routine", "every", "at bedtime", "bid", "tid", "qd", "qhs")
# Adverse-event language for E67.x hypervitaminosis (unchanged).
_ADVERSE_WORDS = ("overdose", "poisoning", "poisoned", "adverse reaction", "adverse effect",
                  "toxicity", "toxic", "underdosing", "intentional", "ingested", "side effect",
                  "reaction to", "too much", "excess")
# Adverse-event language required to justify a T36-T50 drug poisoning/adverse code.
_DRUG_ADVERSE_WORDS = ("overdose", "poisoning", "adverse reaction", "adverse effect",
                       "toxicity", "underdosing", "intentional", "accidental exposure",
                       "intoxication")
_NEOPLASM_WORDS = ("tumor", "tumour", "mass", "neoplasm", "cancer", "carcinoma", "lesion",
                   "growth", "malignan", "benign", "metasta")
# EXPLICIT injury language only — a bare mechanism ("lifted heavy box", "twisted ankle")
# without one of these words does NOT justify an S-code (matched as whole words).
_INJURY_WORDS = ("injury", "injured", "fracture", "fractured", "broken", "fell", "fall",
                 "struck", "trauma", "traumatic", "accident", "tore", "tear", "torn",
                 "ruptured", "sprain", "strain", "wound", "cut", "laceration", "contusion",
                 "bruise", "dislocation", "dislocated")


def _concepts_text(concepts: dict) -> str:
    """All concept phrases joined + lowercased, for keyword scanning."""
    return " ".join(
        str(v) for key in _CONCEPT_KEYS for v in (concepts.get(key) or [])
    ).lower()


def _mentions_word(text: str, words) -> bool:
    """Whole-word keyword match (so 'cut' does not match 'acute', etc.)."""
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


def _is_t36_t50(code_u: str) -> bool:
    """True for T36-T50 (poisoning/adverse/underdosing of drugs) codes."""
    return len(code_u) >= 3 and code_u[0] == "T" and code_u[1:3].isdigit() and 36 <= int(code_u[1:3]) <= 50


def _rule_substance_use(code, description, evidence_phrase, concepts):
    """Rule A — a patient USING a substance does not have poisoning/toxicity from it.
    Drops hypervitaminosis (E67.x) and drug-poisoning (T36-T50) codes whose evidence
    describes routine use rather than an overdose/adverse reaction."""
    code_u = code.upper()
    ev = (evidence_phrase or "").lower()
    # E67.x hypervitaminosis — unchanged: routine supplement use (and no adverse language) drops it.
    if code_u.startswith("E67"):
        has_use = any(w in ev for w in _USE_WORDS)
        has_adverse = any(w in ev for w in _ADVERSE_WORDS)
        if (has_use or "vitamin" in ev or "supplement" in ev) and not has_adverse:
            return "Rule A (substance use): hypervitaminosis code but evidence is routine supplement use"
    # T36-T50 drug poisoning/adverse — drop unless the evidence has explicit adverse-event language.
    if _is_t36_t50(code_u) and not any(w in ev for w in _DRUG_ADVERSE_WORDS):
        return "Rule A (substance use): T36-T50 drug code but no adverse-event language in evidence"
    return None


def _rule_postprocedural(code, description, evidence_phrase, concepts):
    """Rule B — drop 'postprocedural'/'postoperative' codes when no procedure was performed
    (no procedures_ordered entries and no recent-procedure language anywhere)."""
    desc = (description or "").lower()
    if "postprocedural" in desc or "post-procedural" in desc or "postoperative" in desc:
        procedures = [p for p in (concepts.get("procedures_ordered") or []) if isinstance(p, str) and p.strip()]
        ctext = _concepts_text(concepts)
        mentions_proc = any(w in ctext for w in ("post-op", "postop", "postoperative", "after surgery",
                                                 "after the procedure", "following surgery", "underwent",
                                                 "was performed", "had surgery", "status post", "s/p"))
        if not procedures and not mentions_proc:
            return "Rule B (postprocedural): code is postprocedural but no procedure was performed"
    return None


def _rule_neoplasm(code, description, evidence_phrase, concepts):
    """Rule C — drop neoplasm codes (C-chapter, D00-D49) when no tumor/mass/cancer is
    mentioned. Inflammation words (erythematous, swollen) do NOT justify a neoplasm."""
    code_u = code.upper()
    is_neo = code_u[:1] == "C"
    if code_u[:1] == "D" and len(code_u) >= 3 and code_u[1:3].isdigit() and int(code_u[1:3]) <= 49:
        is_neo = True
    if is_neo:
        text = _concepts_text(concepts) + " " + (evidence_phrase or "").lower()
        if not any(w in text for w in _NEOPLASM_WORDS):
            return "Rule C (neoplasm): neoplasm code but no tumor/mass/cancer mentioned"
    return None


def _rule_injury(code, description, evidence_phrase, concepts):
    """Rule D — drop S-chapter (and injury-subset T) codes unless EXPLICIT injury
    language appears in the concepts/evidence. A bare mechanism phrase like
    'lifted heavy box at work last week' (no injury word) is NOT enough — the real
    problem is usually already captured by an M-/R-chapter code the LLM picked."""
    code_u = code.upper()
    is_injury = code_u[:1] == "S"
    if code_u[:1] == "T" and len(code_u) >= 3 and code_u[1:3].isdigit():
        nn = int(code_u[1:3])
        if (7 <= nn <= 34) or (66 <= nn <= 88):  # injury/effects T-codes (poisoning T36-T50 -> Rule A)
            is_injury = True
    if is_injury:
        text = _concepts_text(concepts) + " " + (evidence_phrase or "").lower()
        # Keep only when EXPLICIT injury language is present anywhere in the concepts/evidence.
        # A bare mechanism ("lifted heavy box") is not enough.
        if _mentions_word(text, _INJURY_WORDS):
            return None
        return "Rule D (injury): injury code but no explicit injury language in the encounter"
    return None


# Toggle a rule by commenting it out here.
_GUARDRAIL_RULES = [
    _rule_substance_use,   # A
    _rule_postprocedural,  # B
    _rule_neoplasm,        # C
    _rule_injury,          # D
]


def _guardrail_reject(code: str, description: str, evidence_phrase: str, concepts: dict) -> Optional[str]:
    """Run each enabled guardrail rule; return the first drop reason, else None."""
    for rule in _GUARDRAIL_RULES:
        reason = rule(code, description, evidence_phrase, concepts)
        if reason:
            return reason
    return None


def _suggest_icd_rag(concepts: dict, transcript_text: str, words: list, code_range: str = None) -> list:
    """
    Retrieval-augmented ICD-10 suggestion (Stage 3).

    1. Flatten concepts -> queries; semantically retrieve candidate codes.
    2. Optionally constrain candidates to a user-specified code_range.
    3. Ask the LLM to SELECT (never invent) clinically supported codes.
    4. Validate picks against the candidate list, resolve evidence -> word indices.

    Returns the SAME shape as kevin.suggest_icd_codes:
        [{"code", "description", "evidence": [{"phrase", "word_indices"}]}]
    """
    queries = _flatten_concepts(concepts)
    if not queries:
        print("[icd-rag] no concept queries -> no codes")
        return []

    from icd10_retriever import get_retriever
    retriever = get_retriever()
    candidates = retriever.retrieve(queries, top_k=8)[:25]

    # Constrain to the doctor-specified ICD range, if any (preserves the
    # existing code_range feature). Pass a high cap so the full range expands
    # rather than being reduced to 3-char categories.
    if code_range and code_range.strip():
        try:
            from icd10_utils import get_codes_for_range_input
            allowed_list = get_codes_for_range_input(code_range, max_codes=1000000)
            allowed = {c["code"].upper() for c in allowed_list}
            before = len(candidates)
            candidates = [c for c in candidates if c["code"].upper() in allowed]
            print(f"[icd-rag] code_range '{code_range}': {before} -> {len(candidates)} candidate(s) after range filter")
        except Exception as e:
            print(f"[icd-rag] code_range filter failed ({e}); using unfiltered candidates")

    if not candidates:
        print("[icd-rag] no candidates after retrieval/filtering -> no codes")
        return []

    cand_map = {c["code"].upper(): c for c in candidates}

    print(f"[icd-rag] {len(queries)} queries -> {len(candidates)} candidate(s) sent to LLM")
    print(f"[icd-rag] CANDIDATES (codes): {[c['code'] for c in candidates]}")
    for c in candidates:  # detailed view (code: description <- concept) for debugging
        print(f"    {c['code']}: {c['description']}  (<- \"{c['matched_query']}\")")

    # Group candidates by chapter (first char of code) to aid the LLM's reasoning.
    by_chapter: Dict[str, list] = {}
    for c in candidates:
        by_chapter.setdefault(c["code"][0].upper(), []).append(c)
    cand_lines = []
    for chapter in sorted(by_chapter):
        cand_lines.append(f"[Chapter {chapter}]")
        for c in by_chapter[chapter]:
            cand_lines.append(f"{c['code']}: {c['description']} (from concept: \"{c['matched_query']}\")")
    candidate_block = "\n".join(cand_lines)

    # Structured findings block from the concepts.
    finding_lines = []
    for key in _CONCEPT_KEYS:
        items = [i.strip() for i in (concepts.get(key) or []) if isinstance(i, str) and i.strip()]
        if items:
            finding_lines.append(f"{_CONCEPT_LABELS[key]}: " + "; ".join(items))
    findings_block = "\n".join(finding_lines) if finding_lines else "(none)"

    summary_block = (transcript_text or "").strip()[:2000]

    # The VERBATIM transcript, reconstructed from the resolved words. This is the only
    # text evidence_phrases may be quoted from (and what word_indices map back to).
    # NOTE: transcript_text above is the paraphrased clinical summary, NOT the transcript.
    transcript_full = " ".join(
        str(w.get("text", "")) for w in words
        if isinstance(w, dict) and str(w.get("text", "")).strip()
    )
    transcript_block = transcript_full[:4000]
    transcript_norm = _normalize_for_match(transcript_full)

    prompt = f"""You are a medical coding assistant. From the candidate ICD-10 codes provided, select ONLY the codes that are clinically supported by the encounter findings. Do NOT invent codes — only select from the provided list.

CANDIDATE ICD-10 CODES (grouped by chapter):
{candidate_block}

ENCOUNTER FINDINGS (paraphrased concepts — context only, do NOT quote from here):
{findings_block}

CLINICAL SUMMARY (paraphrased — context only, do NOT quote from here):
{summary_block}

TRANSCRIPT (the actual spoken words — quote evidence VERBATIM from here ONLY):
{transcript_block}

SELECTION RULES:
1. SELECT codes that ARE positively supported by the findings. This includes: confirmed diagnoses, symptoms the patient HAS, procedures performed, and MEDICATIONS THE PATIENT IS CURRENTLY/ROUTINELY TAKING. A current medication is codeable — pick its "long-term (current) use" Z-code (e.g., routine aspirin use -> Z79.82).
2. REJECT codes for any condition that is explicitly NEGATED in the findings (e.g., if findings say "no chest pain", do NOT select chest pain codes even if they appear in the candidate list).
3. REJECT casual, social, lifestyle, or small-talk mentions that are NOT presented as a clinical problem. Attending a sporting event, drinking coffee, nice weather, a verbal argument, or hobbies are NOT codeable medical conditions. If the whole encounter is non-clinical chit-chat, return [].
4. REJECT codes describing POISONING, ADVERSE EFFECT, UNDERDOSING, TOXICITY, or HYPERVITAMINOSIS from a substance UNLESS the encounter explicitly says the patient was poisoned, overdosed, or had an adverse reaction. A patient simply TAKING a medication, vitamin, or supplement does NOT have poisoning/toxicity from it (e.g., "multivitamin daily" is NOT E67.0 Hypervitaminosis A; "lisinopril daily" is NOT an adverse-effect code). For routine current use, choose the "long-term (current) use" Z-code instead.
5. REJECT injury, dislocation, subluxation, and fracture codes (chapters S and T, and external-cause chapters V, W, X, Y — e.g. "struck by football", "subluxation of lumbar vertebra") UNLESS an ACTUAL injury is described and evaluated in THIS encounter. Ordering a diagnostic test does NOT mean the patient has the condition it screens for (e.g., "lumbar spine x-ray" does NOT imply a vertebral dislocation; the test is a procedure, not a diagnosis).
6. REJECT "postprocedural" / "postoperative" codes UNLESS the encounter describes a procedure having actually occurred (e.g., fever from an infection is NOT R50.82 Postprocedural fever).
7. REJECT neoplasm, tumor, or cancer codes UNLESS the encounter explicitly mentions a tumor, mass, neoplasm, or cancer diagnosis. Inflammation or redness is NOT a neoplasm (e.g., "erythematous posterior pharynx" is NOT D10.9 Benign neoplasm of pharynx), and joint swelling from arthritis is NOT hemarthrosis (blood in the joint).
8. REJECT "personal history of" codes when the concept explicitly states there is NO such history (e.g., "no prior psychiatric history" must NOT map to Z86.59).
9. Prefer the MOST SPECIFIC code that fits. If two candidates describe the same condition at different specificity levels, choose the more specific one.
10. Prefer codes where the description directly matches what the patient has, not what they might develop or what is congenital, unless that is what the encounter describes. Also reject casual/social/lifestyle small-talk that is not a clinical problem (a sporting event, coffee, weather, a verbal argument are not codeable).
11. EVIDENCE GROUNDING (critical): the "evidence_phrase" for each selected code MUST be a VERBATIM quote of 1-15 CONSECUTIVE words copied word-for-word from the TRANSCRIPT section above. Single-word quotes are acceptable when the relevant evidence is a single clinical term (medication name, finding, condition) — e.g. "Aspirin", "warfarin", "echocardiogram". Do NOT paraphrase, summarize, or rewrite. Do NOT quote from the FINDINGS or CLINICAL SUMMARY sections — those are paraphrases. The quote must appear word-for-word in the TRANSCRIPT.
12. If you cannot find a verbatim phrase in the TRANSCRIPT that supports a code, do NOT select that code — even if the CONCEPTS/FINDINGS mention it.
13. Rejecting irrelevant/negated findings is correct, but you MUST still select the codes that ARE positively supported by a genuine clinical problem AND backed by a verbatim transcript quote. Return an EMPTY array when nothing qualifies. Otherwise return between 1 and 8 codes.

Return ONLY valid JSON — a SINGLE JSON array, no prose, no markdown, no multiple arrays. Format:
[{{"code":"J18.9","evidence_phrase":"<verbatim transcript quote>"}}]

EVIDENCE EXAMPLES:
  RIGHT (single word, transcript says "...started on Aspirin..."): {{"code":"Z79.82","evidence_phrase":"Aspirin"}}
  RIGHT (multi-word, transcript says "...this is likely community-acquired pneumonia..."): {{"code":"J18.9","evidence_phrase":"likely community-acquired pneumonia"}}
  WRONG (paraphrase, NOT a literal transcript quote): {{"code":"Z79.82","evidence_phrase":"patient takes aspirin daily"}}

Worked example A — TRANSCRIPT contains "I take an aspirin every day"; candidates include Z79.82 and R07.9; findings note "no chest pain":
[{{"code":"Z79.82","evidence_phrase":"I take an aspirin every day"}}]
(Z79.82 selected with a verbatim quote; R07.9 rejected because chest pain is negated.)
Worked example B — casual small talk only, no clinical problem in the transcript:
[]
(Nothing is a clinical problem.)
If nothing is appropriate: []
"""

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                # temperature 0 = deterministic; num_ctx raised so the transcript block fits.
                "options": {"temperature": 0, "num_ctx": 8192},
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "[]").strip()
    except Exception as e:
        print(f"[icd-rag] Ollama error: {e}")
        return []

    picks = _parse_llm_code_picks(raw)
    if not picks:
        print(f"[icd-rag] no valid code picks parsed from LLM response (raw len {len(raw)}): {raw[:200]!r}")
        return []
    print(f"[icd-rag] parsed {len(picks)} pick(s) from LLM response")

    suggestions: list = []
    by_code: Dict[str, dict] = {}
    rejected_invented: List[str] = []
    rejected_guardrail: List[str] = []
    rejected_phantom: List[str] = []
    for p in picks:
        if not isinstance(p, dict):
            continue
        code = str(p.get("code", "")).strip().upper()
        phrase = str(p.get("evidence_phrase", "")).strip()
        if not code:
            continue
        if code not in cand_map:
            rejected_invented.append(code)  # critical: never surface invented codes
            continue
        # Deterministic guardrail: drop clinically implausible code patterns the LLM
        # picks despite the prompt (e.g. hypervitaminosis from taking a multivitamin).
        reason = _guardrail_reject(code, cand_map[code]["description"], phrase, concepts)
        if reason:
            rejected_guardrail.append(f'{code} [{reason}] evidence="{phrase}"')
            continue
        # Evidence-grounding safety net: the phrase MUST be a verbatim transcript quote
        # that maps to real word indices. Otherwise the UI shows "(not found in transcript)"
        # and the audio snippet is dead — better to drop the code than show phantom evidence.
        indices = _find_phrase_word_indices(phrase, words) if phrase else []
        phrase_norm = _normalize_for_match(phrase)
        if not phrase_norm or phrase_norm not in transcript_norm or not indices:
            rejected_phantom.append(f'{code} evidence="{phrase}"')
            print(f"[icd-rag] [Evidence not in transcript: {code} evidence={phrase}]")
            continue
        if code in by_code:
            by_code[code]["evidence"].append({"phrase": phrase, "word_indices": indices})
        else:
            entry = {
                "code": code,
                "description": cand_map[code]["description"],
                "evidence": [{"phrase": phrase, "word_indices": indices}],
            }
            by_code[code] = entry
            suggestions.append(entry)

    suggestions = suggestions[:8]
    selected = [s["code"] for s in suggestions]
    not_selected = [c["code"] for c in candidates if c["code"].upper() not in by_code]
    print(f"[icd-rag] SELECTED {len(selected)}: {selected}")
    if rejected_invented:
        print(f"[icd-rag] REJECTED (invented, not in candidates): {rejected_invented}")
    if rejected_guardrail:
        print(f"[icd-rag] REJECTED (guardrail): {rejected_guardrail}")
    if rejected_phantom:
        print(f"[icd-rag] REJECTED (evidence not in transcript): {rejected_phantom}")
    print(f"[icd-rag] NOT SELECTED ({len(not_selected)} candidate(s)): {not_selected}")

    # Surface likely "obvious miss" cases: empty result despite a strong semantic
    # match and explicit clinical content in the concepts.
    if not suggestions:
        top_score = max((c.get("score", 0.0) for c in candidates), default=0.0)
        clinical = [x for x in ((concepts.get("diagnoses_mentioned") or []) + (concepts.get("symptoms") or []))
                    if isinstance(x, str) and x.strip()]
        if top_score > 0.7 and clinical:
            print(f"[icd-rag] WARNING: empty selection but top candidate score={top_score:.2f} and concepts "
                  f"contain diagnoses/symptoms {clinical} — possible missed code. LLM picks were: "
                  f"{[p.get('code') for p in picks if isinstance(p, dict)]}")

    return suggestions


class SuggestRequest(BaseModel):
    word: str
    context: str


class SuggestCodesRequest(BaseModel):
    # words/concepts optional so legacy callers (no concepts) still validate.
    words: Optional[List[Dict[str, Any]]] = None
    summary: str = ""
    code_range: Optional[str] = ""
    concepts: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    code: str
    description: Optional[str] = ""
    evidence_phrase: Optional[str] = ""
    word_indices: List[int] = []
    is_correct: bool
    transcript_base: Optional[str] = None
    concepts: Optional[Dict[str, Any]] = None


# Serializes concurrent appends to the feedback log (simultaneous ✓/✗ clicks).
_feedback_lock = threading.Lock()


@app.post("/suggest-codes")
def suggest_codes(req: SuggestCodesRequest) -> Dict[str, Any]:
    """
    Suggest ICD-10-CM codes for the transcript.

    Stage 3 (retrieval-augmented selection) runs when `concepts` is provided and
    non-empty. Otherwise we fall back to the original kevin.suggest_icd_codes
    extraction path for backward compatibility. Both paths return the same shape:
    {"suggestions": [{"code", "description", "evidence": [{"phrase", "word_indices"}]}]}.
    """
    words = req.words or []

    # Use RAG only if concepts were actually sent (an all-empty concepts object
    # is still a valid "non-medical encounter" signal and should NOT fall back).
    if req.concepts is not None:
        try:
            suggestions = _suggest_icd_rag(
                req.concepts,
                req.summary or "",
                words,
                code_range=req.code_range,
            )
        except Exception as e:
            traceback.print_exc()
            print(f"[suggest-codes] RAG path failed: {e}")
            suggestions = []
        return {"suggestions": suggestions}

    # Legacy fallback: no concepts in the request.
    from kevin import suggest_icd_codes
    feedback_path = os.path.join(BASE_DIR, "feedback_store.json")
    suggestions = suggest_icd_codes(
        words=words,
        summary=req.summary or "",
        code_range=req.code_range or "",
        feedback_path=feedback_path,
    )
    return {"suggestions": suggestions}


@app.post("/feedback")
def store_feedback(req: FeedbackRequest) -> Dict[str, Any]:
    """
    Log a clinician's correction on an ICD-10 suggestion to feedback/feedback.jsonl
    (one JSON object per line). Every click is recorded with no deduplication —
    a doctor toggling ✗/✓/✗ on the same code is itself signal for later analysis.
    """
    logged_at = datetime.datetime.now().isoformat()
    entry = {
        "timestamp": logged_at,
        "code": req.code,
        "description": req.description or "",
        "evidence_phrase": req.evidence_phrase or "",
        "word_indices": req.word_indices,
        "is_correct": req.is_correct,
        "transcript_base": req.transcript_base,
        "concepts": req.concepts,
    }

    # Stored OUTSIDE the OneDrive-synced project tree so editor/OneDrive saves can
    # never race with or clobber the server's appends — this is irreplaceable PHI
    # training data. Override with FEEDBACK_DIR if needed; default persists across reboots.
    feedback_dir = os.getenv("FEEDBACK_DIR", r"C:\DoctorProjectData\feedback")
    os.makedirs(feedback_dir, exist_ok=True)
    feedback_path = os.path.join(feedback_dir, "feedback.jsonl")
    line = json.dumps(entry, ensure_ascii=False) + "\n"

    # Lock + single atomic append-write so concurrent clicks can't interleave a line.
    with _feedback_lock:
        with open(feedback_path, "a", encoding="utf-8") as f:
            f.write(line)

    return {"ok": True, "logged_at": logged_at}


@app.post("/suggest")
def suggest_word(req: SuggestRequest) -> Dict[str, Any]:
    """Ask Ollama for up to 3 alternative words for a low-confidence flagged word."""
    prompt = (
        f'A word in a medical transcript was flagged as low-confidence.\n'
        f'Context: "...{req.context}..."\n'
        f'Flagged word: "{req.word}"\n\n'
        f'List up to 3 alternative words or short phrases that could have been said instead of "{req.word}". '
        f'Consider homophones, similar-sounding words, and medical terminology that fits the context. '
        f'If the original word looks correct, return fewer alternatives or none.\n\n'
        f'Return ONLY a valid JSON array of strings and nothing else. Examples:\n'
        f'["calling", "falling", "stalling"]\n'
        f'["prescription", "description"]\n'
        f'[]'
    )
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=30)
        raw = resp.json().get("response", "[]").strip()
        # Extract the JSON array from the response
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            suggestions = json.loads(raw[start:end])
        else:
            suggestions = []
        return {"suggestions": [s for s in suggestions if s != req.word][:3]}
    except Exception as e:
        return {"suggestions": []}
