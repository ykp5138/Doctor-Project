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
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

        # Step 3: Kevin merge + summary
        print("🧠 Running Kevin merge...")
        from kevin import merge_for_api
        words, summary = merge_for_api(whisper_out, assembly_out, keywords=keywords, patient_name=patient_name)

        # Clean up audio
        try:
            os.remove(audio_path)
        except Exception:
            pass

        return {
            "words": words,
            "summary": summary,
            "meta": {
                "filename": file.filename,
                "bytes": len(content),
            },
        }

    except subprocess.CalledProcessError as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline step failed: {e}")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ── E/M time thresholds — 2021 AMA guidelines, office/outpatient ──
_EM_NEW = [
    (15, 29, "99202", "Straightforward"),
    (30, 44, "99203", "Low complexity"),
    (45, 59, "99204", "Moderate complexity"),
    (60, 74, "99205", "High complexity"),
]
_EM_ESTABLISHED = [
    (10, 19, "99212", "Straightforward"),
    (20, 29, "99213", "Low complexity"),
    (30, 39, "99214", "Moderate complexity"),
    (40, 54, "99215", "High complexity"),
]


def _em_from_time(minutes: float, new_patient: bool) -> Optional[Dict[str, str]]:
    table = _EM_NEW if new_patient else _EM_ESTABLISHED
    for lo, hi, code, label in table:
        if lo <= minutes <= hi:
            return {"code": code, "label": label}
    # Beyond the top bracket
    if new_patient and minutes > 74:
        return {"code": "99205", "label": "High complexity (>74 min)"}
    if not new_patient and minutes > 54:
        return {"code": "99215", "label": "High complexity (>54 min)"}
    return None


class SuggestCodesRequest(BaseModel):
    summary: str
    transcript_text: str
    duration_seconds: float = 0.0


@app.post("/suggest-codes")
def suggest_codes(req: SuggestCodesRequest) -> Dict[str, Any]:
    """Suggest ICD-10 diagnostic codes and E/M billing codes from a transcript summary."""
    from icd10_utils import validate_and_describe

    icd = _suggest_icd(req.summary, validate_and_describe)
    em = _suggest_em(req.summary, req.duration_seconds)
    return {"icd": icd, "em": em}


def _suggest_icd(summary: str, validate_fn) -> list:
    prompt = (
        "You are a medical coding assistant. Analyze the clinical encounter and suggest "
        "the most appropriate ICD-10-CM diagnostic codes.\n\n"
        f"CLINICAL SUMMARY:\n{summary[:3000]}\n\n"
        "Return ONLY a valid JSON array — no prose. Format:\n"
        '[{"code":"J06.9","description":"Acute upper respiratory infection, unspecified",'
        '"evidence_phrase":"sore throat and runny nose"}]\n\n'
        "Rules: only suggest codes for conditions clearly mentioned or strongly implied; "
        "use the most specific code possible; 1–8 codes maximum; "
        "if no medical content is found return []."
    )
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        raw = resp.json().get("response", "[]").strip()
        start, end = raw.find("["), raw.rfind("]") + 1
        if start == -1 or end <= start:
            return []
        suggestions = json.loads(raw[start:end])
    except Exception as exc:
        print(f"[ICD] suggestion error: {exc}")
        return []

    result = []
    for item in suggestions:
        code = str(item.get("code", "")).strip().upper()
        if not code:
            continue
        verified_desc = validate_fn(code)
        description = verified_desc if verified_desc else item.get("description", "") + " (unverified)"
        result.append({
            "code": code,
            "description": description,
            "evidence": [{"phrase": item.get("evidence_phrase", ""), "word_indices": []}],
        })
    return result


def _suggest_em(summary: str, duration_seconds: float) -> Dict[str, Any]:
    duration_minutes = duration_seconds / 60.0 if duration_seconds > 0 else 0.0

    # Time-based options (both patient types — doctor confirms which applies)
    time_based: Dict[str, Any] = {}
    if duration_minutes >= 10:
        new_match = _em_from_time(duration_minutes, True)
        est_match = _em_from_time(duration_minutes, False)
        if new_match:
            time_based["new_patient"] = new_match
        if est_match:
            time_based["established_patient"] = est_match

    # MDM complexity assessment via LLM
    mdm_prompt = (
        "You are a medical billing specialist. Assess the Medical Decision Making (MDM) "
        "complexity for E/M coding based on this clinical note.\n\n"
        f"CLINICAL SUMMARY:\n{summary[:2000]}\n\n"
        "MDM levels:\n"
        "- straightforward: 1 minor/self-limited problem, minimal data, minimal risk (OTC meds)\n"
        "- low: stable chronic illness or 2+ minor problems, limited data review, low risk\n"
        "- moderate: chronic illness with exacerbation or new problem needing workup, "
        "moderate data review, Rx drug management\n"
        "- high: severe exacerbation, life-threatening condition, extensive data review, "
        "or decision for hospitalization\n\n"
        "Return ONLY valid JSON, no prose:\n"
        '{"complexity":"moderate","code_new_patient":"99204",'
        '"code_established_patient":"99214","reasoning":"brief 1-2 sentence explanation"}'
    )
    mdm: Dict[str, Any] = {}
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": mdm_prompt, "stream": False},
            timeout=60,
        )
        raw = resp.json().get("response", "{}").strip()
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start != -1 and end > start:
            mdm = json.loads(raw[start:end])
    except Exception as exc:
        print(f"[EM] MDM assessment error: {exc}")

    return {
        "duration_minutes": round(duration_minutes, 1),
        "time_based": time_based,
        "mdm_based": mdm,
    }


class SuggestRequest(BaseModel):
    word: str
    context: str


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
