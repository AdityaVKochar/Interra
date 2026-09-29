# Interra

Interra is an interruptible LiveKit voice agent for Samsung PRISM Theme 05. The
current submission target is **Full-Duplex-Bench v3 (FDB-v3)**: 100 recorded
conversations, 79 scenarios, 12 mock tools, disfluent speech, multi-step tool
chains, and latency scoring.

The updated participant guide supersedes the earlier queue-based development
kit. That runtime remains in this repository as tested coordination research,
but the scored entry point is now `agent.fdb_livekit`.

## Current architecture

```text
recorded or live speech
        |
        v
LiveKit room and Silero VAD
        |
        v
ElevenLabs Scribe v2 Realtime STT
        |
        v
Ollama Qwen 3 tool-calling LLM
        |
        +----> 12 official FDB-v3 mock tools
        |              |
        |              v
        +------ grounded tool results
        |
        v
ElevenLabs low-latency TTS
```

The agent keeps Scribe's `no_verbatim` option disabled so false starts,
hesitations, and self-corrections remain visible to the planner. Tool execution
runs outside the event loop, every call is recorded with the benchmark's room
identifier and timestamps, and spoken responses are kept short so LiveKit can
interrupt them.

## Requirements

- Python 3.11. The official benchmark recommends 3.10; the repository supports
  3.11 and will be clean-tested before release.
- A free LiveKit Cloud project.
- An ElevenLabs API key for Scribe v2 Realtime and TTS.
- Ollama with `qwen3:8b` by default. Override the model with
  `INTERRA_FDB_LLM_MODEL`.
- `ffmpeg` available on `PATH`.
- The official Full-Duplex-Bench repository and released v3 audio data.

Never commit credentials. Copy `.env.fdb.example` to a local ignored file and
fill the values there, or export them in the shell.

## Installation

```bash
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[fdb]"
```

PowerShell uses `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

Clone the benchmark at the pinned revision:

```bash
python scripts/fdb_v3.py bootstrap
```

To download the official released audio through its published Google Drive ID:

```bash
python scripts/fdb_v3.py bootstrap --download-data
```

The benchmark and data are placed under `.runtime/`, which is excluded from Git
and Docker packaging. Set `INTERRA_FDB_V3_ROOT` and `INTERRA_FDB_DATA_ROOT` if
you keep them elsewhere.

## Run FDB-v3

Start Ollama and prepare the model before timing:

```bash
ollama pull qwen3:8b
ollama serve
```

Check all required services and paths:

```bash
python scripts/fdb_v3.py check
```

Run the agent and benchmark in one command, then generate the exact-match and
latency reports:

```bash
python scripts/fdb_v3.py all --force
```

For self-reported semantic argument and response scoring, set `OPENAI_API_KEY`
and add `--use-llm`. The organizers' pinned judge and official re-run remain the
scored result.

Individual commands are also available:

```bash
python scripts/fdb_v3.py agent
python scripts/fdb_v3.py benchmark --force
python scripts/fdb_v3.py evaluate
```

Reports and Interra's agent trace are written to `artifacts/fdb_v3/`. The runner
also preserves the official `/tmp/agent_tool_calls.log` telemetry contract.

## ElevenLabs

ElevenLabs credits are useful for this benchmark. The integration uses:

- `scribe_v2_realtime` for streaming recognition;
- `eleven_turbo_v2_5` for low-latency speech generation;
- `ELEVEN_API_KEY` as the only ElevenLabs secret name.

ElevenLabs does not provide the multi-step reasoning layer in this architecture;
Ollama handles tool selection and argument generation. The API key name must be
listed in the submission form, while its value must remain outside the repository.

## Extension use case

The retained Interra runtime already supports asynchronous PNG observations,
source-bound CLIP embeddings, correction-aware state, stale-result rejection,
and tool cancellation. The planned FDB-v3 extension is camera-assisted device
troubleshooting. It must be connected to the LiveKit wrapper and shown working
end to end in the demo before submission; the older scripted replay is supporting
evidence rather than the required extension demo.

## Tests

The deterministic runtime suite remains useful for interruption and side-effect
safety:

```bash
python -m unittest discover -s tests -v
```

The current suite does not substitute for an FDB-v3 run. Submission readiness
requires the official inference and evaluation reports from all released samples.

## Legacy queue runtime

The previous kit is retained under `vendor/samsung_theme05`, and its adapter is
still available as `interra_submission:ParticipantAgent`. It is no longer the
submission contract described by the updated participant guide. Its tests,
traces, and safety mechanisms remain useful implementation evidence and a source
for the camera-assisted extension.

See [FDB-v3 migration](docs/FDB_V3.md), [current status](docs/STATUS.md), and
[definition of done](docs/10_DEFINITION_OF_DONE.md).
