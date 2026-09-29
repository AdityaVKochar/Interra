# Demo guide

The final video must be a three-to-five-minute recording of real system behavior.
The historical deterministic replay can explain cancellation internals, but it
cannot replace the required benchmark and extension demonstrations.

## Required sequence

1. Show the active LiveKit agent and identify the STT, LLM, and TTS providers.
2. Run one FDB-v3 recording containing an interruption or self-correction.
3. Show the resulting tool calls and explain how the corrected value reached them.
4. Run camera-assisted device troubleshooting end to end.
5. Interrupt or correct the extension while perception or reasoning is active.
6. Show the final FDB-v3 report values and state one measured limitation.

## Commands

Check the environment before recording:

```bash
python scripts/fdb_v3.py check
```

Start the agent independently when rehearsing:

```bash
python scripts/fdb_v3.py agent
```

Run and evaluate the released benchmark:

```bash
python scripts/fdb_v3.py all --force --use-llm
```

The scripted coordination replay remains available for engineering review:

```bash
python -m agent.demo
```

Its `STALE_RESULT_DISCARDED` event proves a deterministic safety property only;
label it clearly if any excerpt appears in the final video.

## Recording outline

- 0:00–0:35: problem, benchmark, and architecture.
- 0:35–2:05: real FDB-v3 interruption or correction and tool telemetry.
- 2:05–3:35: camera-assisted extension with a live correction.
- 3:35–4:25: benchmark scores and latency.
- 4:25–5:00: limitations and next work.

Use an unedited single take where practical. Do not claim the historical
queue-kit score as an FDB-v3 result and do not show API keys on screen.
