# Kaggle hosted run review — 2026-09-30

Notebook: `maitrishah29/interra-fdb-v3-http-tts-smoke`.
Latest run: COMPLETE. Models: LiveKit Inference Deepgram Nova-3,
GPT-4.1 mini, Cartesia Sonic-3. SDK: LiveKit Agents 1.8.3.
Official benchmark pin: `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`.

## Measured results

| Metric | Result |
| --- | --- |
| Strict pass | 31/100 |
| Wrong tools | 50 |
| Wrong arguments | 19 |
| Turn-taken recordings | 58/100 |
| Silent recordings | 42 |
| Completed inference attempts | 93 |
| Inference failures | 7 |
| STT rate-limited rooms | 35; all silent |
| Tool selection, turn-taken samples | 88.5% |
| Argument accuracy, turn-taken samples | 58.6% |
| Tool selection, all samples | 51.3% |
| Argument accuracy, all samples | 34.0% |
| Early interruptions, turn-taken samples | 6/58 |
| Average response latency, excluding interruptions | 4.545 seconds |
| Full batch duration | 93.61 minutes |

Sources downloaded to `artifacts/kaggle-inference-latest/`:

- `Interra/artifacts/fdb_v3/interra_elevenlabs_pass_rate_report.json`
- `Interra/artifacts/fdb_v3/interra_elevenlabs_evaluation_report.json`
- `Interra/artifacts/fdb_v3/livekit-agent.jsonl`
- The 100 `result_interra_elevenlabs.json` files under the released data folder.

Notebook logs and embedded source are in `artifacts/kaggle-latest-source/`.
Repeated Kaggle stdout/stderr records were deduplicated before counting errors.
The optional semantic judge was disabled; no normalized overall hackathon
score or post-fix improvement is claimed.

## Causes and implemented fixes

1. Sessions stayed open after participant disconnect without an explicit
   session close or job shutdown. STT 429 errors affected 35 recordings.
   Added a participant-bound lifecycle with a bounded drain, explicit close,
   job shutdown, event-handler removal, and awaited cancellation of owned tasks.
   The leak is proven in the old source; the exact share of quota failures it
   caused remains an inference until the corrected hosted run completes.
2. OpenAI plugin imports blocked the job event loop for hundreds of milliseconds.
   Warm Silero and benchmark code before accepting a job; import the optional
   plugin only for the fallback model profile.
3. Apartment search omitted requested pet constraints. Forward the optional
   pet filter through the official backend's supported keyword arguments.
4. Search-filter values had a string-only schema. Expose string/number/boolean
   values and restore explicit numeric and boolean types.
5. Spoken identifier spelling remained spaced words in tool arguments. Join
   explicitly spelled single letters and digits; preserve literal identifiers
   with punctuation and avoid guessing misheard letters.

Some failures still need model-level improvement: misheard identifiers, lost
address words, incorrect currency direction, extra tool calls, and incomplete
chains. General transcription instructions now reinforce ordinary written
numbers/identifiers, faithful product wording, and typed values. No expected
answers are inserted into the prompt or runtime.

## Verification and rerun

126 local tests passed on Python 3.11, including 12 new lifecycle/argument
regressions. Lifecycle tests assert cleanup traces and no orphaned waiters.
Checked supported APIs in the exact LiveKit Agents 1.8.3 wheel from PyPI.
Local mocks do not prove hosted speech quality or quota recovery.

Import `artifacts/kaggle-fixed/interra_setup.ipynb` in the existing Kaggle
notebook using File → Import Notebook. Keep T4 and Internet enabled and attach
`LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` through Kaggle Secrets.
Use Save Version → Save & Run All. The packaged notebook embeds the updated
runtime and has the full benchmark enabled.

After the speech gate, verify each room produces a `session_cleanup` trace.
Compare strict pass, silent recordings, inference failures, and STT 429 rooms
against the table above. If 429s remain despite clean sessions, check the
LiveKit project's inference quota and other active consumers. Avoid running
multiple notebooks against the same project concurrently.

The current browser integration reports `unsupported Codex auth method:
apikey`, so importing and starting this version could not be performed from
this session. Kaggle CLI status/log/report reads succeeded.
