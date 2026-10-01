# Kaggle run — 2026-10-01

- Kernel: `adityavardhankochar/interra-fdb-v3-benchmark`, version 3.
- Source revision: local checkout based on `d328dc8597154fbefb6a0e06b02ed75da6c35d28`, with the working-tree lifecycle/retry changes embedded.
- Models: LiveKit Inference Deepgram Nova-3, GPT-4.1 mini, Cartesia Sonic-3.
- Benchmark: pinned Full-Duplex-Bench v3 commit `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`; 100 recordings.
- Official strict passes: 43/100 (43.0%); turn-take: 90/100; no response: 10.
- Average response latency: 4.175 s (excluding interruptions); 11 early interruptions.
- Turn-taken tool selection/argument accuracy: 85.7%/56.3%; all-recording accuracy: 77.2%/50.7%.
- Trace: 147 tool calls, all completed; 101 cleanup events and 101 completed cooldowns.
- Compared with the previous best on Git main (31/100 strict pass, 58/100 turn-take, 4.545 s): strict passes +12, turn-takes +32, latency −0.370 s. Turn-taken tool-selection accuracy is 2.8 percentage points lower and argument accuracy 2.3 points lower.

## Limits

LiveKit logs show LLM credit-quota errors during this run. No STT 429 appears in the agent trace. The optional organizer LLM judge was disabled, so no normalized overall hackathon score is reported. This is one full run, not the three-run repeatability check in the project handoff. The Kaggle output endpoint returned 15 of 100 per-recording result JSONs; the aggregate evaluator reports cover all 100 recordings. `tool-calls.jsonl` is derived from `livekit-agent.jsonl`, whose tool-call events include arguments and results.

The attached artifacts contain no audio, provider credentials, or generated model weights.
