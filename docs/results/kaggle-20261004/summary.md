# Kaggle run — 2026-10-04

- Kernel: `adityavardhankochar/interra-fdb-v3-benchmark`, started from the Kaggle
  editor with Save & Run All at 16:07 UTC, completed 17:57 UTC (108.6 min).
  Source: the notebook pushed from `a770259` (version 4 of the CLI push).
- Models: LiveKit Inference Deepgram Nova-3, GPT-4.1 mini (temperature 0),
  Cartesia Sonic-3. LiveKit project `p_36yq3rs165t` (free tier).
- Benchmark: pinned Full-Duplex-Bench v3 commit
  `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`; 100 recordings; organizer LLM
  judge off (exact-match arguments).
- Official strict passes: **53/100** (43/100 on 2026-10-01).
  Turn-take: 71/100; no response: 29.
- Turn-taken tool selection/argument accuracy: 92.5%/78.9% (85.7%/56.3% before).
  All-recording accuracy: 65.7%/56.0%.
- Average response latency: 4.528 s (excluding interruptions); 3 early
  interruptions (11 before).
- Recorder crashes: 7, all retried once and completed (`recorder-retries.json`).
- Trace: 110 tool calls, all completed; 1 duplicate call returned from cache;
  21 turns held mid-sentence; 108 session cleanups and cooldowns.
- `python -m agent.fdb_offline rescore --run docs/results/kaggle-20261004`
  reproduces 53/100 exactly.

## LLM credits ran out at minute 81

At 81.2 min the project's Inference allowance was exhausted: GPT-4.1 mini
returned 429 `inference_quota_exceeded` (`MaxGatewayCredits`), and Deepgram STT
returned 429 from one minute later (448 STT errors in 28 rooms). Every recording
from that point got no response: all 20 travel recordings, the last two housing
recordings, and the 7 recorder retries, which run at the end. Travel's 0.0 domain
score is this outage, not a travel regression.

| Subset | 2026-10-01 live | 2026-10-01 rescored | LLM replay (`d8b494b`) | 2026-10-04 live |
| --- | --- | --- | --- | --- |
| 71 recordings run before the outage | 35 | 37 | 55 | **53** |
| 29 recordings after the outage | 8 | 19 | 22 | 0 |

The replay predicted the 71 live results within 2 passes, so with enough credits
the whole run projects to about 73–75/100. That is an estimate, not a score.

The offline replays in this session used the same free-tier project
before the run (about 280 replayed conversations), which drew from the same
credit allowance.

## Files

`kaggle-kernel-logs.json` (the project URL is redacted), `livekit-agent.jsonl`,
`tool-calls.jsonl` (tool-call events from the trace), the two official
evaluator reports, `recorder-retries.json`, `interra-setup-report.json`,
`interra-fdb-results.zip` (per-recording results and reports, no audio),
`rescore.json` and `kernel-metadata.json`. No audio, credentials or model
weights are included.
