# ICD-10 selection and regression checks

The enhanced pipeline keeps the existing transcription, concept extraction,
feedback collection, and UI response format. It changes candidate retrieval and
ICD selection; it does not retrain Llama 3 or automatically learn from feedback.

## Changes

- SapBERT uses the final-layer CLS representation and diagnosis descriptions as
  input. Build and query share explicit pooling, length, model revision, and
  dimension metadata. A new index lives in `indexes_sapbert_cls/`; the original
  MiniLM and SapBERT indexes remain available.
- Candidates are ranked separately for each concept before merging. Explicit
  diagnosis description matches and matches to the installed ICD inclusion terms
  receive candidate priority. A candidate still
  needs model selection and supporting transcript evidence. Incomplete category
  codes are filtered out.
- The model chooses a transcript span ID. Python copies that span's actual words
  and indices instead of asking the model to reproduce a quotation. A repair
  can recover an already selected code only when
  its explicit positive diagnosis name or matching ICD inclusion name occurs
  in the spoken transcript. A question alone does not confirm a diagnosis.
- Evidence windows are selected from the whole transcript rather than its first
  4,000 characters. The prompt has a bounded evidence budget, so very long
  recordings still require evaluation.
- Structured output restricts codes and span IDs. The baseline already used
  temperature 0; the enhanced selector also fixes seed 42 to reduce variability.
  Observable selection/rejection decisions are logged;
  private model reasoning is not exposed.
- Context checks cover common negation, family/personal history, hypothetical
  diagnoses, routine medication use, investigation orders, and unsupported
  injury/pregnancy suggestions. These are software safeguards, not a complete
  implementation of coding guidelines.

The representation follows [SapBERT's model instructions](https://huggingface.co/cambridgeltl/SapBERT-from-PubMedBERT-fulltext).
JSON schemas use [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Build once on each computer

Keep Ollama running with `llama3`. From the project root in PowerShell:

```powershell
.\venv\Scripts\python.exe build_icd_index_sapbert.py --device cuda
```

Use `--device cpu` on a computer without CUDA. If the model is already cached,
add `--local-files-only` to prevent a download. The builder protects both original
`indexes/` and `indexes_sapbert/` directories. It records the installed code data's version and
source hashes; building does not download a newer ICD-10-CM release.

Generated indexes are ignored by Git. Your friend must build the new index on
their computer after pulling the source changes. The default `auto` mode uses
enhanced selection with a CLS index and preserves the old selector with the old
vectors when the new index is absent. This avoids silently changing behavior
on a computer that has not completed the new setup.

Restart the backend after building or changing modes:

```powershell
.\start_backend.ps1
```

The backend prints the selected index when it first handles a coding request.
The frontend and feedback terminals use the same commands in
[FEEDBACK_SETUP.md](FEEDBACK_SETUP.md).

## Repeat the checks

These checks use frozen synthetic transcripts and fixed concepts, with local
Ollama inference. They do not call speech or paid transcription APIs or write
to the actual feedback file.

Comparisons require the original `indexes/` and `indexes_sapbert/` artifacts as
well as the new `indexes_sapbert_cls/`. Keep the original artifacts for rollback.
On a fresh installation, build the MiniLM index with
`.\venv\Scripts\python.exe build_icd_index.py` before starting the enhanced app.

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\test_stage3_fixtures.ps1 -Repeats 2
.\test_stage3_fixtures.ps1 -Holdout -Repeats 2
.\venv\Scripts\python.exe -X utf8 evaluate_icd_accuracy.py --context --variants legacy enhanced_mean enhanced_cls --fail-on-regression enhanced_cls --output outputs/icd_accuracy/context.json
```

The evaluation compares the preserved selector at commit
`5af8d8a32e35069ce7df4c3d0481c48974a2923e` against enhanced selection with the
original SapBERT index and the new CLS/description index. It records identical
input hashes, candidates, raw model replies, validation decisions, and exact
transcript grounding in ignored `outputs/icd_accuracy/` reports.

The PowerShell checks fail if the enhanced CLS variant loses a case that the
baseline passed on the same input/repetition. Reports list paired improvements
and regressions separately; an aggregate gain must not hide a lost success.

After a change confined to validation, recorded outputs can be checked again
without loading models or making inference requests:

```powershell
.\venv\Scripts\python.exe replay_icd_validation.py --inputs outputs/icd_accuracy/comparison.json --output outputs/icd_accuracy/replayed.json
```

Replay verifies the frozen input and full recorded request, including the prompt,
model, schema, and options. A changed request requires fresh inference. Replay
tests validation only; it cannot establish an improvement in model selection.

To recheck the cached acne recording on this computer without retranscribing:

```powershell
.\venv\Scripts\python.exe -X utf8 evaluate_cached_icd.py --base 746fca318a984bfba18ebc6c49edbf5b_mp3 --expected-code L70.0 --repeats 2
```

That private recording is not in Git. Cached checks measure whether required
codes appear and evidence matches the actual cached ASR words. Additional codes
remain unadjudicated; this check does not claim the entire encounter is coded
correctly.

## Diagnostics

Normal logs show selected codes and rejection reasons. For full local request,
candidate, span, and raw-response diagnostics, set this before starting the backend:

```powershell
$env:ICD_DIAGNOSTICS = '1'
.\start_backend.ps1
```

Files go to ignored `outputs/icd_diagnostics/`. They can contain transcript
content. Keep them private along with recordings, credentials, and feedback logs.

## Restore the preserved behavior

Stop the backend with Ctrl+C, then start it in the same terminal with:

```powershell
$env:ICD_SELECTOR_MODE = 'legacy'
$env:ICD_RETRIEVAL_MODE = 'legacy'
$env:ICD_SAPBERT_INDEX_DIR = 'indexes_sapbert'
.\start_backend.ps1
```

To return to the enhanced defaults, stop the backend, then run:

```powershell
Remove-Item Env:ICD_SELECTOR_MODE -ErrorAction SilentlyContinue
Remove-Item Env:ICD_RETRIEVAL_MODE -ErrorAction SilentlyContinue
Remove-Item Env:ICD_SAPBERT_INDEX_DIR -ErrorAction SilentlyContinue
.\start_backend.ps1
```

All three settings are process environment variables, not frontend `.env`
settings. Restart to discard the loaded retriever singleton. For a comparison
using enhanced selection with old vectors, explicitly set
`$env:ICD_SELECTOR_MODE = 'enhanced'` and
`$env:ICD_SAPBERT_INDEX_DIR = 'indexes_sapbert'`. This experimental combination
is evaluated separately; it is not selected automatically.

## Evidence and limits

See [ICD_ACCURACY_REPORT.md](ICD_ACCURACY_REPORT.md) for measured results.
Synthetic regression gains do not guarantee accuracy on unseen clinical
encounters. These checks isolate retrieval and selection; ASR errors, missed
concepts, clinical context, coding conventions, and model/runtime changes still
need review. The new index currently records April 2026 data from the installed
`simple_icd_10_cm` package. Confirm the appropriate release for the encounter
date using the [CMS ICD-10-CM releases](https://www.cms.gov/medicare/coding-billing/icd-10-codes)
before using suggestions for billing.
