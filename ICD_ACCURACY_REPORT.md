# ICD-10 accuracy implementation results

Date: October 24, 2026. Working branch: `icd-accuracy-improvements`.
Baseline: `5af8d8a32e35069ce7df4c3d0481c48974a2923e`.

The enhanced selector with the new CLS/description index improved the checked
examples while preserving every baseline success. This establishes a measured
software regression improvement on this corpus, not guaranteed accuracy on
unseen clinical encounters.

## Paired results

There are **38 distinct synthetic cases**. The 18 core cases ran twice; each of
the other 20 cases ran once, giving **56 runs per variant**. Repetitions are not
additional independent clinical examples.

| Cases | Preserved baseline | Enhanced selector, old vectors | Enhanced selector, new CLS index |
| --- | ---: | ---: | ---: |
| Core: 18 cases, two repetitions | 22/36 | 34/36 | 36/36 |
| Additional conditions: 10 cases | 5/10 | 10/10 | 10/10 |
| Additional contexts: 10 cases | 6/10 | 9/10 | 10/10 |
| Total passing runs | **33/56** | **53/56** | **56/56** |

Each comparison uses identical transcript/concept input hashes. A pass requires
all required codes, no disallowed extra codes, valid contiguous transcript
evidence, and no transport/parsing error. Explicitly permitted optional history
or encounter codes are excluded from false positives; none were selected in
these final runs.

| Variant | Correct required codes | Disallowed extra codes | Missing required codes |
| --- | ---: | ---: | ---: |
| Preserved baseline | 27 | 20 | 11 |
| Enhanced selector, old vectors | 35 | 0 | 3 |
| Enhanced selector, new CLS index | 38 | 0 | 0 |

The new CLS variant retained all **33 baseline successes**, improved **23 failed
runs**, and had **zero paired regressions**. All variants retrieved every
required code somewhere in their candidate set; average reciprocal rank improved
from **0.6096** to **0.9474**. This shows a ranking gain, not a candidate-recall gain
on this particular corpus.

The old-vector experimental variant had **one actual regression**, despite its
aggregate gain: it missed `Z85.3` in `context_personal_history`, which the baseline
selected correctly. It also missed the screening code in two core repetitions.
For that reason, computers without the new CLS index automatically keep the
preserved selector. Enhanced selection with old vectors requires explicit opt-in.

## The cached acne recording

The comparison reused **1,033 actual cached WhisperX word entries** and the
cached concepts for the user's mock appointment. It did not transcribe the audio
again, call AssemblyAI, or reconstruct evidence from generated concepts.

| Variant | L70.0 present with grounded evidence |
| --- | ---: |
| Preserved baseline | 0/2 |
| Enhanced selector, old vectors | 2/2 |
| Enhanced selector, new CLS index | 2/2 |

Both baseline runs selected the code internally but rejected its evidence quote
as absent from the transcript. The enhanced pipeline selected transcript IDs and
returned actual words/indices. Additional codes in cached-recording checks are
unadjudicated; this is a required-code check, not an estimate of full-encounter
precision. The cached source is WhisperX output, rather than the UI's merged
transcript.

A separate check of the actual FastAPI `/suggest-codes` route, using default
`auto` selection and embeddings on **CUDA**, returned HTTP 200, `L70.0`, and
grounded evidence. ICD retrieval and Ollama inference were real; unchanged E/M
generation was mocked for that check.

## Verification and reproducibility

- **87 automated tests passed**, covering ICD behavior, evaluation integrity,
  transcription handling, feedback persistence, and synchronization.
- The preserved selector matches the baseline function's syntax tree after
  renaming; both original retrieval methods also match their baseline versions.
  The original indexes remain available and are protected against overwriting
  by the new builder, including with `--force`.
- Validation-only fixes were checked again against recorded generations.
  **All 112 enhanced requests matched the full recorded request exactly**,
  including prompt, model, output schema, and generation options. This replay
  revalidates postprocessing; it is not additional inference or new examples.
- No dependency upgrades, model weight changes, feedback-code changes, or
  transcription/concept-extraction changes were made for this implementation.

The local evaluation used Ollama **0.17.1**, `llama3:latest`, digest
`365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1`.
Both selectors used temperature 0; the enhanced selector also used seed 42.
Embedding comparisons ran on CPU to keep the local generation workload separate;
the production-route check additionally verified CUDA operation.

The new index contains 98,505 entries, 768-dimensional normalized vectors, CLS
pooling, description-only input, and maximum sequence length 128. Metadata pins
SapBERT revision `090663c3ae57bf35ffe4d0d468a2a88d03051a4d` and records the
installed `simple_icd_10_cm` 1.5.0 April 2026 source hashes. Category entries can
exist in the index, but enhanced selection filters incomplete codes.

Detailed local artifacts are ignored by Git:

- `outputs/icd_accuracy/core-final.json`
- `outputs/icd_accuracy/holdout-final.json`
- `outputs/icd_accuracy/context-final.json`
- `outputs/icd_accuracy/replayed-final.json` (final validation and paired results)
- `outputs/icd_accuracy/cached-final.json`
- `outputs/icd_accuracy/api-smoke.json`

Setup, repeatable commands, the regression gate, diagnostics, and rollback are
documented in [ICD_ACCURACY.md](ICD_ACCURACY.md).

## Limits of these results

The labels are synthetic and inspectable, not clinician-adjudicated ground
truth. Many positives use exact diagnosis wording and supplied concepts. Some
cases drove fixes during development; the additional cases are not a blind
clinical validation set, despite the historical `holdout` command/file name.

The new-index comparison changes both pooling and indexed text. Its measured
gain cannot be attributed to CLS pooling alone. These tests isolate retrieval,
selection, and validation; they do not establish improved speech recognition,
concept extraction, clinical reasoning, or complete billing-rule compliance.

The evidence budget and assertion checks remain bounded heuristics. Unseen
phrasing, synonyms, conflicting speakers, long encounters, and runtime/model
changes can still cause omissions or incorrect suggestions. Larger reviewed
clinical examples are needed to estimate general precision and recall. The
appropriate ICD-10-CM release must also be checked for the encounter date; this
work preserves and records the installed April 2026 code data.
