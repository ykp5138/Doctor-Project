from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
from pydantic import BaseModel
import os
import sys
import subprocess
import uuid
import traceback
import json
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


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> Dict[str, Any]:
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
        words, summary = merge_for_api(whisper_out, assembly_out)

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
