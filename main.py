from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import tempfile
import os
import sys
import subprocess
import uuid
import traceback
from scripts.icd_suggester import ICDCodeSuggester

app = FastAPI()
try:
    icd_suggester = ICDCodeSuggester()
    print("✅ ICD Code Suggester initialized successfully")
except Exception as e:
    print(f"⚠️ ICD Code Suggester failed to initialize: {e}")
    icd_suggester = None


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


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Complete pipeline:
      1) save uploaded audio to temp
      2) run WhisperX script -> whisperX_confidences.json
      3) run AssemblyAI script -> assemblyAI_confidences.json
      4) merge with Kevin -> get words
      5) generate ICD code suggestions from transcript
      6) return both transcript AND codes
    """
    try:
        # Save uploaded audio
        suffix = os.path.splitext(file.filename or "")[1] or ".audio"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            audio_path = tmp.name

        # Create a unique temp directory for outputs to avoid collisions
        out_dir = os.path.join(tempfile.gettempdir(), f"doctor_project_{uuid.uuid4().hex}")
        os.makedirs(out_dir, exist_ok=True)

        whisper_out = os.path.join(out_dir, "whisperX_confidences.json")
        assembly_out = os.path.join(out_dir, "assemblyAI_confidences.json")

        # Use the current Python executable (your venv) so subprocess uses same environment
        py = sys.executable

        # Run WhisperX
        print("🎙️ Running WhisperX transcription...")
        subprocess.run(
            [py, os.path.join("scripts", "whisperX_transcriber.py"), audio_path, "--out", whisper_out],
            check=True
        )

        # Run AssemblyAI
        print("🎙️ Running AssemblyAI transcription...")
        subprocess.run(
            [py, os.path.join("scripts", "assemblyai_transcriber.py"), audio_path, "--out", assembly_out],
            check=True
        )

        # Merge using Kevin
        print("🧠 Merging transcriptions with Kevin...")
        from kevin import merge_for_api
        words = merge_for_api(whisper_out, assembly_out)

        # Generate ICD code suggestions
        icd_results = None
        if icd_suggester:
            try:
                print("💊 Generating ICD-10 code suggestions...")
                icd_results = icd_suggester.suggest_codes(words)
                print(f"✅ Generated {len(icd_results.get('suggested_codes', []))} code suggestions")
            except Exception as e:
                print(f"⚠️ ICD suggestion failed: {e}")
                icd_results = {
                    "error": str(e),
                    "suggested_codes": [],
                    "clinical_summary": "Failed to generate suggestions",
                    "missing_information": []
                }
        else:
            icd_results = {
                "error": "ICD suggester not initialized",
                "suggested_codes": [],
                "clinical_summary": "ICD suggester unavailable",
                "missing_information": []
            }

        # Clean up audio file
        try:
            os.remove(audio_path)
        except Exception:
            pass

        return {
            "words": words,
            "icd_suggestions": icd_results,
            "meta": {
                "filename": file.filename,
                "bytes": len(content),
                "out_dir": out_dir,
                "has_icd_codes": len(icd_results.get("suggested_codes", [])) > 0 if icd_results else False
            }
        }

    except subprocess.CalledProcessError as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Subprocess failed: {e}")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))