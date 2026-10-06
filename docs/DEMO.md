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

Everything runs on your own computer: a terminal, and Chrome or Edge with a
camera and microphone. Cloud sandboxes without UDP/WebRTC cannot carry LiveKit
media. Record the browser window (and a terminal if you like) in one take.

### One-time setup

```bash
git clone https://github.com/Maitri-shah29/Interra.git && cd Interra
python3.11 -m venv .venv && .venv/bin/pip install -e ".[voice]" "gdown>=5,<6"
.venv/bin/python scripts/fdb_v3.py bootstrap --download-data   # pinned FDB-v3 checkout + released audio
export LIVEKIT_URL=wss://<project>.livekit.cloud LIVEKIT_API_KEY=... LIVEKIT_API_SECRET=...
```

Prerequisites: Python 3.11, `git` and `ffmpeg` on `PATH`. Use a LiveKit project
with Inference credit; never show the keys on screen. On Windows PowerShell use
`.venv\Scripts\python` and `$env:LIVEKIT_URL="..."`.

### The live console

```bash
.venv/bin/python -m agent.demo_console        # open http://127.0.0.1:8787
```

The console joins the LiveKit room in the browser and shows, live:

- the camera preview and audio levels for the person and the agent;
- streaming transcripts of both sides, with interrupted agent replies marked;
- the agent's state (listening, thinking, speaking) and the response latency;
- a timeline of what happens underneath, published by the agents themselves:
  official tool calls with arguments and results, held mid-sentence turns,
  duplicate calls returned from cache, lookups cancelled by an interruption,
  stale results discarded after a correction, ticket writes, suppressed duplicate
  writes, and a thumbnail of the exact camera frame sent with each turn;
- the support-ticket desk.

The keys stay in the console process; the browser only gets a two-hour token
for one room.

### Part 1: a real benchmark interruption (about 1.5 minutes)

Terminal A, the benchmark agent with console events on:

```bash
INTERRA_UI_EVENTS=1 .venv/bin/python scripts/fdb_v3.py agent
```

(PowerShell: `$env:INTERRA_UI_EVENTS="1"` first.) Scored runs leave this unset.

In the console, choose **Benchmark recording**, pick a recording marked ★ (it
contains a self-correction or a state rollback), and press **Join room and play
recording**. The console joins as a hidden listener, and the official
`livekit_inference.py` recorder plays the real human recording into the room.
Narrate while it plays:

- the person's words stream in on the left of the conversation;
- if they pause mid-sentence, **Turn held** appears instead of an early answer;
- after the correction, the **Tool** card shows the corrected value in the
  arguments, then the agent's spoken reply;
- when the recording ends, **Trace: tool calls for this room** shows the calls
  exactly as the benchmark scores them.

Stop terminal A (Ctrl+C) before Part 2; the benchmark agent joins every room.

### Part 2: camera troubleshooting extension (about 2 minutes)

Terminal A, the extension agent:

```bash
.venv/bin/python -m agent.extension_livekit start
```

In the console, choose **Camera troubleshooting** and press **Start camera
session**; allow camera and microphone. The troubleshooter has three tools: a
guide lookup (a local guide library with a simulated two-second lookup, so it can
be interrupted), and opening and cancelling support tickets, which are written to
`artifacts/support-tickets.jsonl`. Suggested script, pointing the camera at real
devices:

1. Show your router: "My internet's down, the router's internet light is off."
   Point at the **Camera frame sent** card (the thumbnail is what the model saw)
   and the **look_up_fix** card.
2. While it is still looking up, interrupt: "Wait, sorry, it's not the router,
   it's this power strip," and turn the camera to the strip. Show the
   **Correction**, **Lookup cancelled** or **Stale result discarded** card: the
   router answer is never spoken. A new lookup runs for the power strip.
3. Follow one check it suggests, then say: "Can you open a ticket for a
   technician?" The **Ticket opened** card and the ticket desk appear.
4. Ask again: "Open the ticket please." **Duplicate write blocked**: the desk
   keeps one ticket.
5. "Actually cancel that ticket, the switch was just off." **Ticket cancelled**.
6. Hold up a small label and ask what it says; it asks for a closer view
   instead of guessing.

### Health check before recording

```bash
.venv/bin/python scripts/fdb_v3.py check
```

`scripts/demo_room.py` offers the same benchmark and camera sessions from the
terminal with a plain LiveKit Meet link, if the console is not needed.

The scripted coordination replay remains available for engineering review
(`python -m agent.demo`). Its `STALE_RESULT_DISCARDED` event proves a
deterministic safety property only; label it clearly if any excerpt appears in
the final video.

## Recording outline (3 to 5 minutes, one take)

- 0:00–0:30: problem and architecture; the console header shows the live STT,
  LLM and TTS models.
- 0:30–2:00: Part 1, a released FDB-v3 recording with a self-correction, the
  held turn, the corrected tool arguments and the trace.
- 2:00–4:00: Part 2, camera troubleshooting with an interruption, a stale
  result discarded, a ticket opened, a duplicate blocked and a cancellation.
- 4:00–4:40: benchmark results (70/100 strict pass, 100/100 turn-take) and one
  limitation.

Do not claim the historical queue-kit score as an FDB-v3 result and do not show
API keys on screen.
