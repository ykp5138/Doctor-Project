# Friend setup on Mac

Use this guide on the friend's Mac. The owner uses Windows and follows
[FEEDBACK_SETUP.md](FEEDBACK_SETUP.md). Both computers run the same application
code; the terminal commands and dependency installation depend on the platform.

This guide assumes the app already worked on the Mac. Keep that working virtual
environment and the existing transcription credentials. Updating the source does
not require reinstalling all Python packages.

## 1. Get the updated source

Start commands from the Mac's project folder, not from the owner's Windows path.
The examples assume the existing environment is named `venv`. If it is named
`.venv`, use `.venv/bin/python` instead of `venv/bin/python`.

After the owner confirms the update is pushed to `main`, stop any running backend
and frontend with Ctrl+C. In a Mac terminal in the existing project folder:

```sh
git status --short
```

If this lists local source changes, save them in a commit before updating. Then
run these commands one at a time:

```sh
git switch main
git pull --ff-only origin main
git log -1 --oneline
```

If switching or pulling fails, keep the error and resolve it before continuing.
The fast-forward update preserves the previous local commits. The ignored
virtual environment, credentials, recordings, and generated indexes remain
local; they are not supplied by the pull. The owner can compare the final commit
ID with their own to confirm both copies use the same source.

## 2. Configure feedback once

Keep the Mac's root `.env` configured with its working `HF_TOKEN` and
`ASSEMBLYAI_API_KEY` settings.

Create or update `frontend/.env.local` using `frontend/.env.example` as the
template. If `.env.local` already exists, edit its feedback settings without
overwriting other local settings. These Mac commands create it only if missing,
then open it in TextEdit:

```sh
test -f frontend/.env.local || cp frontend/.env.example frontend/.env.local
open -e frontend/.env.local
```

Set the following values, replacing the token placeholder with the actual
submission credential supplied privately by the owner, then save the file:

```dotenv
FEEDBACK_API_URL=https://doctor-feedback-collector-patel.handyfrost65.chatgpt.site
FEEDBACK_API_TOKEN=THE_WRITE_CREDENTIAL_PROVIDED_PRIVATELY_BY_THE_OWNER
```

The owner provides the submission/write credential from their
`frontend/.env.local`. The friend does not need the owner's
`.env.feedback.local` or `FEEDBACK_EXPORT_TOKEN`. These settings files are local
and are not distributed by Git. Restart Vite after changing them.

Both computers use this same collector URL and submission credential. That sends
the friend's choices to the same cloud dataset, which the owner downloads into
`C:\DoctorProjectData\feedback\feedback.jsonl` (or their configured `FEEDBACK_DIR`).
The friend does not need a copy of that feedback file. Configured cloud submissions
do not create a local feedback copy on the Mac.

## 3. Build the new ICD index once

From the Mac's project folder:

```sh
./venv/bin/python -X utf8 build_icd_index_sapbert.py --device cpu
```

Use CPU for this build on Mac, including Apple Silicon. The command creates
`indexes_sapbert_cls/` separately from the original indexes. It can download the
model on first use. Generated indexes are not transferred by Git.

The existing MiniLM index must also be present. If it is missing, build it:

```sh
./venv/bin/python -X utf8 build_icd_index.py
```

The owner already built the new index on their Windows computer; they do not
need to rebuild it to resolve an API connection error. Without a new CLS index,
the default mode preserves the previous selector with the original indexes.
See [ICD_ACCURACY.md](ICD_ACCURACY.md) for evaluation and rollback details.

## 4. Keep Ollama running

Open the Ollama application on the Mac and keep `llama3` available. To check:

```sh
ollama list
```

If `llama3` is missing:

```sh
ollama pull llama3
```

If Ollama is not running as an application/service, run `ollama serve` in an
additional terminal. An address-already-in-use message can mean the service is
already running; do not start a second copy.

## 5. Run the app in two Mac terminals

### Terminal 1: backend

From the Mac's project folder:

```sh
unset ICD_SELECTOR_MODE ICD_RETRIEVAL_MODE ICD_SAPBERT_INDEX_DIR
./venv/bin/python -X utf8 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

The `unset` command clears earlier coding-test overrides in this terminal so the
default mode selects the new CLS index built above.

Wait for `Application startup complete` and keep the terminal running. Open
`http://127.0.0.1:8000/health` on the Mac. It must return `{"ok":true}` before
testing transcription. `127.0.0.1` refers to the computer running the browser;
the Mac runs its own transcription backend.

### Terminal 2: frontend

Open another terminal in the project folder:

```sh
cd frontend
npm run dev
```

If frontend dependencies have never been installed in this checkout, run
`npm ci` once in `frontend/` before `npm run dev`.

Open the Local address printed by Vite. Keep both terminals open. The friend's
Mac uses these commands instead of the Windows `.ps1` launch scripts.

## 6. Test a submission

1. Upload the mock recording and wait for an ICD code suggestion.
2. In the backend terminal, confirm the new pipeline is active:

   ```text
   [icd-retrieval] SapBERT index: indexes_sapbert_cls
   [icd-spans] selected ...
   ```

   The index line appears on first use. If an original index is printed instead,
   confirm the new index build completed and restart the backend.
3. Expand a suggested code's row and click checkmark or X.
4. Wait for the small `recorded` popup. Later clicks replace the current choice
   for that code within the same recording.
5. On Windows, the owner opens two terminals in their project root and runs:

   ```powershell
   .\start_feedback_sync.ps1
   ```

   In the other terminal:

   ```powershell
   .\watch_feedback.ps1
   ```

   Within about 10-20 seconds, the viewer should show the friend's code and
   `Correct`/`Incorrect` label in the owner's file. Match the recording ID when
   comparing rows: separate uploads of the same audio receive different IDs.
6. Click the other feedback button on that same suggestion. After its popup and
   the next download cycle, the same recording/code row should change label.
   Clicking the same button again keeps that label.

The friend runs neither of those owner-only terminals. Feedback can be accepted
by the cloud while the owner's PC is off; the owner's physical file catches up
when they next run the downloader.

## If the site cannot reach the API

Check Terminal 1 and `http://127.0.0.1:8000/health` first. A running frontend or
feedback viewer does not start FastAPI. If the backend exits, its terminal
traceback identifies the startup failure. Leave that output visible for diagnosis.

If the popup says `Feedback not saved`, check the two feedback settings in
`frontend/.env.local` and restart the frontend. If the popup succeeds but the
owner's file does not update, check the owner's downloader terminal and allow
the next polling cycle. The owner's export credential is needed only by that
downloader; it is not a fix for a Mac submission failure.

## Which requirements file applies?

- `requirements.txt` is the general/Mac dependency list.
- `requirements_windows_cuda.txt` is intended for Windows with NVIDIA CUDA;
  the friend does not use it on Mac.
- These files install Python dependencies. They do not start the application or
  configure cloud feedback.

For the existing working Mac installation, use its current environment and the
run commands above. The old install comments are not a verified environment
lock: the Windows file also has conflicting Torch/WhisperX/Transformers pins.
A fresh environment should be resolved for its actual platform separately from
an environment that already works.
