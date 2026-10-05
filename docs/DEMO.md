# Demo guide

Demo video: [Interra demo](https://cursor.com/artifacts/v/art-65efdeb4-9b6f-4416-839a-875b82833f5a)

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

## How to run it for the recording

Run everything on your own computer (a browser with camera and microphone, and
a terminal). Cloud sandboxes without UDP/WebRTC cannot carry LiveKit media.

### One-time setup

```bash
git clone https://github.com/Maitri-shah29/Interra.git && cd Interra
python3.11 -m venv .venv && .venv/bin/pip install -e ".[voice]" "gdown>=5,<6"
.venv/bin/python scripts/fdb_v3.py bootstrap --download-data   # pinned FDB-v3 checkout + released audio
export LIVEKIT_URL=wss://<project>.livekit.cloud LIVEKIT_API_KEY=... LIVEKIT_API_SECRET=...
```

Prerequisites: Python 3.11, `git` and `ffmpeg` on `PATH`. Use a LiveKit project
with Inference credit; never show the keys on screen.
On Windows PowerShell use `.venv\Scripts\python` and `$env:LIVEKIT_URL="..."`.

### Part 1: a real benchmark interruption (about 1.5 minutes)

Pick a released recording with a self-correction:

```bash
.venv/bin/python scripts/demo_room.py list
```

Terminal A, the benchmark agent (it joins every new room):

```bash
.venv/bin/python scripts/fdb_v3.py agent
```

Terminal B, stream that recording into a fresh room:

```bash
.venv/bin/python scripts/demo_room.py benchmark <recording-folder-from-list>
```

Open the printed link in the browser. It is a hidden, listen-only viewer, so
the agent ignores it. Press Enter in terminal B: the official
`livekit_inference.py` recorder plays the human recording into the room and
you hear the person correct themselves and the agent answer. Terminal B then
prints the tool calls the agent made in that room; show that the corrected
value reached the arguments. The agent's audio is saved under `artifacts/demo/`.

Stop terminal A (Ctrl+C) before Part 2; otherwise the benchmark agent also
joins the camera room.

### Part 2: the camera troubleshooting extension (about 1.5 minutes)

Terminal A, the extension worker:

```bash
.venv/bin/python -m agent.extension_livekit start
```

Terminal B, create a room and dispatch the troubleshooter into it:

```bash
.venv/bin/python scripts/demo_room.py camera
```

Open the printed link, allow camera and microphone, and point the camera at a
device (a router, a printer, a phone charger). Suggested script:

1. "My router's internet light is off. What should I check?" — the agent uses
   the current frame and suggests one check.
2. Interrupt it mid-answer with a correction: "Wait, sorry, it's not the
   router, it's this power strip" and move the camera to the power strip. It
   should drop the router advice and use the new frame.
3. Ask about a label it cannot read so it asks for a closer view.

Each spoken turn carries only the latest camera frame; older images are
removed from the conversation, and the agent never claims a repair is done.

### Health check before recording

```bash
.venv/bin/python scripts/fdb_v3.py check
```

The scripted coordination replay remains available for engineering review
(`python -m agent.demo`). Its `STALE_RESULT_DISCARDED` event proves a
deterministic safety property only; label it clearly if any excerpt appears in
the final video.

## Recording outline

- 0:00–0:35: problem, benchmark, and architecture.
- 0:35–2:05: real FDB-v3 interruption or correction and tool telemetry.
- 2:05–3:35: camera-assisted extension with a live correction.
- 3:35–4:25: benchmark scores and latency.
- 4:25–5:00: limitations and next work.

Use an unedited single take where practical. Do not claim the historical
queue-kit score as an FDB-v3 result and do not show API keys on screen.
