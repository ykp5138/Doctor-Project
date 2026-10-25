# Doctor Project

For the friend's Mac setup and shared-feedback submission, follow
[FRIEND_SETUP.md](FRIEND_SETUP.md). The Windows owner's four-terminal feedback
workflow is in [FEEDBACK_SETUP.md](FEEDBACK_SETUP.md).

The React/Vite frontend uploads a recording to FastAPI. The backend runs WhisperX,
AssemblyAI, transcript reconciliation, and Ollama summarization/concept extraction.
The result supports transcript corrections, grounded ICD-10 suggestions, E/M
suggestions, and clinician feedback on ICD-10 suggestions.

## Run on Windows

Use the existing project `venv` with the required dependencies installed. Keep
Ollama running with the `llama3` model available, and configure `HF_TOKEN` and
`ASSEMBLYAI_API_KEY` in the root `.env` file.

In a terminal in the project root:

```powershell
.\start_backend.ps1
```

This script uses `venv\Scripts\python.exe` directly and enables UTF-8 for Python
output, including the transcription subprocesses. Virtual environment activation
is optional when using this script. Check `http://127.0.0.1:8000/health` for
`{"ok":true}`. Keep this terminal open while using the site.

In a second terminal:

```powershell
cd frontend
npm run dev
```

Open the address printed by Vite. Its `/api` proxy forwards requests to
`http://127.0.0.1:8000`, including when Vite selects a port other than 5173.
Transcription can take several minutes; the proxy has no request timeout.

## ICD-10 feedback

For coding improvements, side-by-side index setup, evaluation results, diagnostics,
and a switch back to the preserved selector, see [ICD_ACCURACY.md](ICD_ACCURACY.md).

The checkmark and X buttons post correctness labels and their transcript context
to `/feedback`. The last saved choice for each recording/code is the current
result in `C:\DoctorProjectData\feedback\feedback.jsonl`. Clicking the same
button again keeps that choice. The initial file is backed up before rewriting,
and earlier choices remain in history. `FEEDBACK_DIR` can override the directory
when set in the backend process environment.

These records collect examples for future evaluation/fine tuning. They do not
automatically retrain the model.

To collect every user's feedback while this PC is off, see
[the feedback setup and testing guide](FEEDBACK_SETUP.md). It includes all four
owner terminals, button checks, and the friend's submission-only test. Other app
copies send feedback to the cloud collector, and the owner can sync new records into this computer's
existing JSONL file while keeping transcription processing local.

## Local regression checks

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m pip check
```

The API regression tests replace the speech/model pipeline and write feedback to
temporary storage. They test upload handling and feedback persistence without
external API calls or changes to the real feedback log. `pip check` separately
reports dependency conflicts in the installed environment.
