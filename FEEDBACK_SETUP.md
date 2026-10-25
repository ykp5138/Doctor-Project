# Central feedback collection

For the friend's Mac commands and configuration, use
[FRIEND_SETUP.md](FRIEND_SETUP.md). The Windows owner uses the four terminals below.

If the site says **"Could not reach the API"**, first start Terminal 1 and check
`http://127.0.0.1:8000/health`. It must return `{"ok":true}`. The feedback viewer
(`watch_feedback.ps1`) only displays the file; it does not start the backend.
If the backend exits during startup, its terminal output identifies the error.

The cloud collector stores feedback in a persistent database while the owner's
computer is off. Each app can keep transcription local and send only checkmark/X
feedback to the collector. Configured apps do not create a local feedback copy
or fall back to local storage when the cloud is unavailable.

The last successfully saved choice is the current result for each code within
one recording. Checkmark then X then X leaves that code marked incorrect; no
click cancels a choice. The same code in another recording stays independent.

Collector origin:

```text
https://doctor-feedback-collector-patel.handyfrost65.chatgpt.site
```

The collector's source is managed in a separate Sites repository, checked out
under `cloud-feedback/`. It has a feedback endpoint and an owner-authenticated
export. Transcription and recordings are not hosted there.

## Test feedback on your computer (four terminals)

Open each PowerShell terminal in your `Doctor-Project2` project folder. Only
Terminal 2 changes into the `frontend` subfolder. The launch scripts select the
project's virtual environment automatically; manual venv activation is optional.

Before testing:

- Keep Ollama running with `llama3` available. If it is not running, start
  `ollama serve` in an additional terminal, or start the Ollama desktop service.
- `frontend/.env.local` must contain the collector URL and submission credential.
- The owner's root `.env.feedback.local` must contain the same collector URL,
  the owner export credential, and the destination `FEEDBACK_DIR`.
- Runtime settings come from the `.local` files. Editing either `.example` file
  does not change the running application.
- Keep `feedback.jsonl` unedited during the test. Use Terminal 4 to see the
  saved file rather than relying on a possibly unsaved editor tab.

If the app is already showing a suggestion and has loaded the latest UI update,
leave Terminals 1 and 2 running and reuse that suggestion. After updating the
sync code, stop Terminals 3 and 4 with Ctrl+C and restart them using the commands
below. For a clean start, stop old backend/frontend instances with Ctrl+C first.

### Terminal 1: backend

From the project folder:

```powershell
.\start_backend.ps1
```

Wait for `Application startup complete`. Leave this terminal running.
`http://127.0.0.1:8000/health` should return `{"ok":true}`.

### Terminal 2: frontend

Start this terminal in the project folder, then run:

```powershell
cd frontend
npm run dev
```

Open the Local address printed by Vite. Keep this terminal running. Restart Vite
after changing `frontend/.env.local` so the proxy uses the new settings.

### Terminal 3: cloud download into your local file

From the project folder:

```powershell
.\start_feedback_sync.ps1
```

This checks the cloud every ten seconds. `Saved 0 new cloud feedback record(s)`
is normal when nothing new is waiting. A positive number counts received
updates; changing a label does not necessarily increase the number of rows in
the current file. Keep this terminal running.

### Terminal 4: current feedback viewer

From the project folder:

```powershell
.\watch_feedback.ps1
```

The viewer shows code, current `Correct`/`Incorrect` choice, and recording ID.
It updates when the file changes. If the file does not exist yet, it waits for
the first downloaded feedback. Use this polling viewer instead of the old
`Get-Content -Wait` command, which can block file replacement on Windows.

### Click through the test

1. Reuse a currently displayed suggestion, or upload a test recording that has
   produced ICD suggestions before. If uploading, enter a test patient name,
   press Transcribe, and wait for the suggestions to finish loading.
2. Expand the code row using its arrow to reveal the evidence and checkmark/X
   buttons.
3. Click the checkmark once. Wait for the small `✓ recorded` popup at the bottom.
   Within approximately 10-20 seconds, Terminal 4 should show `Correct` for that
   recording/code.
4. Click X once and wait for `X recorded`. Terminal 4 should change that same
   row to `Incorrect`; it should not remove the choice or count votes.
5. Click X again. The result remains `Incorrect`, with one current row for that
   recording/code. A repeated X does not cancel feedback.
6. Click the checkmark again to confirm the choice can change back to `Correct`.
   Finish with the label you actually want to keep for this test recording.

Each new transcription upload receives a different recording ID, even if it is
the same audio file. It is therefore normal to see separate rows for the same
code from different uploads. Latest-choice behavior applies within one recording.

The canonical file is `C:\DoctorProjectData\feedback\feedback.jsonl`, unless
`FEEDBACK_DIR` overrides it. Earlier choices belong to the backup/history files
described below, not to the current-label view.

### Confirm cloud catch-up and duplicate prevention

1. Press Ctrl+C in Terminal 3 only. Keep the app and Terminal 4 running.
2. Click a different feedback choice and wait for its `recorded` popup. This
   confirms the cloud accepted it while your local downloader was stopped.
3. Terminal 4 should not change yet. Restart Terminal 3:

   ```powershell
   .\start_feedback_sync.ps1
   ```

4. The waiting cloud choice should replace the older local choice.
5. Stop and restart Terminal 3 again without making another click. It should
   report zero new records and leave the current file unchanged.

This tests stopped downloading. To verify the full PC-off scenario, use the
friend test below while the owner's computer is shut down.

## Friend test (submission only)

The friend needs the updated source files and their usual working transcription
environment, including their own root `.env` for normal model/API settings.
Git does not distribute private `.env.local` files.

1. The owner privately provides the URL and submission credential from
   `frontend/.env.local`. The friend creates or updates their own
   `frontend/.env.local` using those two settings, as shown in the configuration
   section below. Do not overwrite other local settings if that file exists.
2. The friend starts their own backend and frontend and keeps Ollama running.
   On Mac, use the commands in [FRIEND_SETUP.md](FRIEND_SETUP.md); the `.ps1`
   commands above are for Windows. Their clone folder can have a different
   absolute path; start commands from that project's root.
3. They upload their test recording, wait for a code suggestion, expand it, and
   click checkmark/X. The popup must say `recorded`, not `Feedback not saved`.
4. The owner runs Terminals 3 and 4 on the owner's computer. Within about 10-20
   seconds, the friend's recording/code choice should appear in the owner's
   current file. Later clicks on that same recording/code replace its label.
5. For the PC-off test, the owner shuts down their computer while the friend
   submits feedback. When the owner turns it back on, they run Terminals 3 and
   4. Feedback collected while it was off should download then. The owner's
   transcription backend and frontend are not needed just to download feedback.

The friend does not run the owner's sync/viewer terminals and does not receive
the root `.env.feedback.local` or `FEEDBACK_EXPORT_TOKEN`. Their configured app
sends feedback to the cloud rather than creating a local feedback copy.

### If a test fails

- **`Feedback not saved`:** inspect the friend's/owner's frontend terminal and
  browser Network response for `/api/feedback`. Confirm the URL and submission
  token in `frontend/.env.local`, then restart Vite.
- **Popup succeeds but your file stays unchanged:** confirm Terminal 3 is
  running without errors, uses the owner's export settings, and Terminal 4
  watches the same directory as `FEEDBACK_DIR`. Allow the next polling cycle.
- **Permission/file-lock error in Terminal 3:** stop the old `Get-Content -Wait`
  viewer or other program holding the file, then restart sync and use
  `.\watch_feedback.ps1`.
- **No suggestions:** the feedback buttons need an existing code suggestion.
  That is an ICD pipeline issue; backend `[icd-spans]` or `[icd-rag]` logs identify selection and
  evidence failures separately from feedback saves.
- **Different rows for the same code:** compare their recording IDs. Different
  uploads are separate cases, even when their filenames or audio match.

## Configure each app deployment

Copy `frontend/.env.example` to `frontend/.env.local` and set:

```dotenv
FEEDBACK_API_URL=https://doctor-feedback-collector-patel.handyfrost65.chatgpt.site
FEEDBACK_API_TOKEN=THE_COLLECTOR_WRITE_CREDENTIAL
```

The owner's app is configured locally after deployment. To configure a friend's
copy, provide the collector write credential from that local file through a
private channel. Never provide the separate export credential. Restart Vite
after changing its settings.

Both settings are required for remote mode. Invalid remote settings stop startup;
a cloud outage reports a failed save without creating a local feedback copy.
Copies without remote settings retain the original local feedback behavior, so
pushing code alone does not configure other computers.

These variables belong to the server-side Vite proxy. They have no `VITE_`
prefix, and the token is injected by the proxy rather than shipped in browser
JavaScript. People using a hosted app through their browsers need no individual
configuration: configure that hosting server once for all its users. A static
`dist/` deployment needs an equivalent server-side `/api/feedback` proxy; static
files alone cannot inject the secret or proxy requests.

## Keep the local JSONL copy up to date

The owner's `.env.feedback.local` contains the cloud origin, an owner-only
`FEEDBACK_EXPORT_TOKEN`, and `FEEDBACK_DIR=C:\DoctorProjectData\feedback`.
The local settings files are ignored by Git. Keep the export credential on the
owner's computer; the write credential cannot read feedback.

Download new feedback once:

```powershell
.\venv\Scripts\python.exe sync_feedback.py
```

Or watch for new feedback every ten seconds while this PC is on:

```powershell
.\start_feedback_sync.ps1
```

The downloader reconciles `C:\DoctorProjectData\feedback\feedback.jsonl` to one
current choice per recording/code. A new choice replaces the older choice in
this file. Other recordings and legacy entries without recording IDs are kept
independent. Downloaded records retain cloud cursor metadata so repeated or
interrupted syncs do not undo a newer choice.

Before the first rewrite, existing contents are backed up as
`feedback.before-latest-choice.jsonl` in the same directory. Received changes
are also retained in `feedback_history.jsonl`; the cloud keeps its event history.
The primary `feedback.jsonl` is the current-label dataset, not a vote count.

Cloud collection continues when this PC or the downloader is off. The physical
local file receives the missed records on the next sync. Keep the downloader
running for updates within its polling interval while the PC is on.

To view current choices without editing or locking the file, stop the old
`Get-Content -Wait` watcher with Ctrl+C and run this from the project folder:

```powershell
.\watch_feedback.ps1
```

The selected button stays highlighted. A small bottom popup displays
"✓ recorded" or "X recorded" after the collector confirms the write. Rapid
clicks are saved in order for each code, and old responses cannot replace the
latest confirmation. Existing local feedback files on other computers are not
deleted or uploaded automatically.

## Local receiver alternative

`feedback_server.py` and `start_feedback_server.ps1` remain available for a
separate deployment with a persistent filesystem. The receiver requires
`FEEDBACK_API_TOKEN` and writes to its own `FEEDBACK_DIR`. Hosting that receiver
on the owner's PC requires that PC to stay on; it is not needed for the cloud
collector described above.
