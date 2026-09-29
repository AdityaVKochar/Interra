# Local model setup and evaluation

The local profile uses Qwen3-VL 2B through Ollama for planning and vision, multilingual
Whisper base through faster-whisper (CPU int8), and CLIP ViT-B/32 through FastEmbed
(512 dimensions). No hosted inference or private decision server is used.

## Windows setup

Use Python 3.11 and ffmpeg. From the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e '.[local]'
.venv/Scripts/python scripts/install_ollama_cpu.py
./scripts/local.ps1 Start
./scripts/local.ps1 Download
./scripts/local.ps1 Probe
./scripts/local.ps1 Evaluate
```

The optional CPU installer fetches only the CPU members of the official Ollama
0.34.3 Windows archive over HTTPS and checks each member's ZIP CRC. An existing
Ollama installation is also supported. Do not start a second server on port 11434.
Model files stay under `.models` and binaries under `.tools`; neither belongs in Git.
The download command records checkpoint revisions, actual model-file checksums,
and the Ollama model digest. Python dependency versions are in `requirements-local.lock`.

Close unnecessary applications before model testing on an 8 GB machine. Fast
acknowledgments are local and do not wait for inference, but successful completion
still requires all reasoning and tools to fit the scenario's actual timing windows.
`probe` reports setup and single-request timings; its readiness flag is not a score.

## Configuration

| Variable | Local default | Purpose |
| --- | --- | --- |
| `INTERRA_PROFILE` | explicitly set to `local` by scripts | Enable real local providers |
| `INTERRA_MODEL` | `qwen3-vl:2b` in local profile | Shared planner/vision model |
| `INTERRA_OLLAMA_URL` | `http://localhost:11434` | Local inference service |
| `INTERRA_MODEL_ROOT` | `.models` | Perception weight cache |
| `INTERRA_ASR_MODEL_PATH` | `.models/whisper-base` | Pre-downloaded Whisper checkpoint |
| `INTERRA_MEDIA_ROOT` | supplied kit root | Only delivered MP3/WAV/PNG references |
| `INTERRA_TRACE_DIR` | set by local script | Optional per-session runtime JSONL traces |
| `INTERRA_AUDIO_URL`, `INTERRA_VISION_URL` | unset | Existing explicit HTTP adapters, if selected |

Injected providers take precedence. Explicit HTTP perception URLs override the local
perception adapter. Without the local profile or an explicit reasoning model, the
entrypoint retains its clearly labeled safe unconfigured fallback.

## Ownership, uncertainty, and evidence

Ollama requests use async HTTP and a shared per-session concurrency lock. Native ASR
and embedding generators run in bounded worker threads. Canceling native inference
discards its result; it cannot terminate C/C++ code safely, so shutdown joins running
work. The runtime continues consuming events and invalidates old source epochs.
Model weights may be shared across sessions; transcripts, frames, vectors, state,
clients, and clarification context are session scoped.

Generation uses a 4,096-token context and at most 512 output tokens, with thinking
disabled. The adapter removes duplicate observations and computed vectors from planner
context, retaining schemas, current observations, call statuses and results. Oversized
JSON context fails explicitly rather than truncating those fields. Its 10,000-byte guard
is not an exact tokenizer measurement; unusual inputs may still exceed the model window.
Dynamic tool names are constrained by the manifest in both the generation schema and runtime.

Ollama 0.34.3 with the downloaded Qwen3-VL tag sometimes routes a complete JSON answer
into `message.thinking` with empty `message.content`, even when thinking is disabled.
The adapter accepts that field only if the entire value is a JSON object matching the
requested schema, and only after checking for output truncation. It never extracts a
fragment from free-form reasoning. The runtime still validates the proposal and tool
arguments. The behavior has a related [upstream report](https://github.com/ollama/ollama/issues/14798).

Whisper marks empty transcripts, low-probability words (<0.55), or low mean log
probability (<-1.0) uncertain. These are conservative engineering defaults, not calibrated
confidence claims. Uncertain observations never directly populate confirmed slots.
An explicit subsequent answer may resolve an outstanding clarification.

Vision computes embeddings independently of generated JSON. Planner context contains
an embedding source reference, never the vector. `ToolRequest.embedding_refs` maps
a tool argument to that source; runtime resolution requires a current accepted frame.
New frames invalidate dependent calls. Description caching is per provider/session.

## Evaluation and replay

```powershell
$env:INTERRA_PROFILE = 'local'
$env:INTERRA_MEDIA_ROOT = (Resolve-Path vendor/samsung_theme05).Path
$env:INTERRA_TRACE_DIR = (Join-Path (Get-Location) 'artifacts/local-traces')
.venv/Scripts/python scripts/run_samsung.py
.venv/Scripts/python vendor/samsung_theme05/eval_submission.py . --reps 3 --time-scale 1 --out artifacts/samsung-local-evaluation.json
.venv/Scripts/python -m agent.demo --replay artifacts/samsung-public-traces.json --scenario pub_02
```

Use the scenario identifier printed in the trace report; `--replay` lists available
identifiers when selection is missing. Local JSONL replay also displays state changes,
stale rejection, and trace-derived latency. The default demo uses scripted reasoning
and the actual runtime with a virtual clock; it is not live-model performance evidence.

## Docker

```sh
docker compose build agent
docker compose up -d ollama
# Wait until the Ollama server is listening before the explicit download.
docker compose run --rm agent python -m agent.local_setup download --endpoint http://ollama:11434
docker compose run --rm agent python -m agent.local_setup probe --endpoint http://ollama:11434 --model-root /models --audio audio/pub_05_turn1.mp3 --image frames/pub_07_f017.png
docker compose run --rm agent python vendor/samsung_theme05/eval_submission.py . --reps 3 --time-scale 1 --out artifacts/samsung-local-evaluation.json
```

The original Dockerfile remains the small deterministic test/demo image. The separate
local image and Compose file provide reproducible inference service startup and weight
volumes. The evaluator kit remains unmodified.
