"""One local page for the judge recording.

Voice and camera are two rooms on one screen. The largest line is the gate's
latest decision. A scored run from 4 October 2026 stays beside the live take
so a dropped connection does not erase the evidence.

Start the voice worker with INTERRA_FDB_AGENT_NAME=interra-benchmark, the
camera worker in a second terminal, then this page:

    python -m agent.demo_page
"""

from __future__ import annotations

import datetime
import json
import os
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)

PORT = 8780
VOICE_AGENT = "interra-benchmark"
CAMERA_AGENT = "interra-camera-troubleshooter"
TRACE_PATH = ROOT / "artifacts" / "fdb_v3" / "livekit-agent.jsonl"
ROOM_NAME = re.compile(r"^demo-(voice|camera)-[a-z0-9]{6,16}$")
SHOWN = {
    "transcript",
    "turn_held",
    "turn_released",
    "tool_call",
    "tool_call_dropped",
    "tool_call_deduplicated",
    "conversation_item",
    "user_state",
}

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interra — judge page</title>
<style>
:root {
  --ink: #1c1915;
  --muted: #5c564c;
  --paper: #f3efe6;
  --card: #fffdf8;
  --line: #e4dccf;
  --heard: #1d4e89;
  --held: #8a5a00;
  --dropped: #8f1d1d;
  --executed: #0d6b3d;
  --reused: #3d3a6b;
  --said: #1c1915;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Segoe UI", Candara, sans-serif;
}
header, main { width: min(1180px, calc(100% - 2rem)); margin: 0 auto; }
header { padding: 1.25rem 0 0.5rem; }
.word { font-size: 0.82rem; letter-spacing: 0.16em; font-weight: 700; }
h1 {
  font-family: Georgia, "Iowan Old Style", serif;
  font-weight: 500;
  font-size: clamp(1.8rem, 3vw, 2.6rem);
  line-height: 1.15;
  margin: 0.35rem 0 0.6rem;
}
.models, .scores { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.35rem 0; }
.models span, .scores span, .chip {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: 999px;
  padding: 0.28rem 0.7rem;
  font-size: 0.92rem;
}
.rule { max-width: 46rem; color: var(--muted); line-height: 1.45; }
main {
  display: grid;
  grid-template-columns: minmax(280px, 0.9fr) minmax(320px, 1.1fr);
  gap: 1rem;
  padding-bottom: 2rem;
}
section {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 1rem 1rem 1.1rem;
}
.stage h2, .decisions h2, .scored h2 { margin: 0 0 0.7rem; font-size: 1rem; }
.modes, .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
button {
  font: inherit;
  border-radius: 999px;
  border: 1px solid var(--ink);
  background: transparent;
  padding: 0.45rem 0.9rem;
  cursor: pointer;
}
button[aria-pressed="true"], button.primary { background: var(--ink); color: white; }
button:disabled { opacity: 0.45; cursor: default; }
#status, #prompt, .legend { line-height: 1.45; }
#prompt {
  font-family: Georgia, serif;
  font-size: 1.25rem;
  margin: 0.8rem 0;
}
video {
  width: 100%;
  max-height: 320px;
  background: #111;
  border-radius: 12px;
  display: none;
}
body[data-mode="camera"] video { display: block; }
#meter { height: 14px; background: #efeae2; border-radius: 999px; overflow: hidden; margin: 0.4rem 0 0.8rem; }
#level { height: 100%; width: 0; background: #0d6b3d; }
#agent-audio audio { width: 100%; margin-top: 0.4rem; }
.now {
  min-height: 7.5rem;
  border-left: 8px solid var(--muted);
  padding: 0.2rem 0 0.2rem 0.9rem;
  margin-bottom: 0.8rem;
}
.now b { display: block; font-size: 0.78rem; letter-spacing: 0.12em; text-transform: uppercase; }
.now p {
  font-family: Georgia, serif;
  font-size: clamp(1.35rem, 2.4vw, 1.9rem);
  line-height: 1.25;
  margin: 0.25rem 0 0;
}
.now[data-kind="Heard"] { border-color: var(--heard); }
.now[data-kind="Held"] { border-color: var(--held); }
.now[data-kind="Dropped"] { border-color: var(--dropped); }
.now[data-kind="Executed"] { border-color: var(--executed); }
.now[data-kind="Reused"] { border-color: var(--reused); }
.now[data-kind="Said"] { border-color: var(--said); }
ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.45rem; }
li {
  display: grid;
  grid-template-columns: 6.2rem 1fr;
  gap: 0.6rem;
  padding-bottom: 0.45rem;
  border-bottom: 1px solid var(--line);
}
li b { font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase; }
.Heard b { color: var(--heard); }
.Held b { color: var(--held); }
.Dropped b { color: var(--dropped); }
.Executed b { color: var(--executed); }
.Reused b { color: var(--reused); }
.Said b { color: var(--said); }
.scored { grid-column: 1 / -1; }
.scored ol { max-width: 52rem; }
details { margin-top: 0.8rem; color: var(--muted); }
code { font-family: Consolas, monospace; font-size: 0.88rem; }
.legend { display: none; margin: 0.6rem 0; }
body[data-mode="camera"] .legend { display: block; }
@media (max-width: 860px) {
  main { grid-template-columns: 1fr; }
}
</style>
</head>
<body data-mode="voice">
<header>
  <div class="word">INTERRA · THEME 05</div>
  <h1>The gate decides. This page only shows the decision.</h1>
  <p class="rule">You speak. The model may plan a tool. The gate holds that call until you have been quiet. If you continue, the call is dropped before it is logged. If you finish, it runs once.</p>
  <div class="models">
    <span>Deepgram Nova-3</span>
    <span>GPT-4.1 mini · temperature 0</span>
    <span>Cartesia Sonic-3</span>
    <span>Quiet window 0.6 s</span>
  </div>
  <div class="scores">
    <span>70/100 strict</span>
    <span>100/100 turn-take</span>
    <span>4.452 s average</span>
    <span>Organizer LLM judge off</span>
    <span>29 of 100 re-recorded after the Inference credit outage</span>
  </div>
</header>
<main>
  <section class="stage">
    <h2>Live</h2>
    <div class="modes">
      <button id="mode-voice" type="button" aria-pressed="true">Voice correction</button>
      <button id="mode-camera" type="button" aria-pressed="false">Camera correction</button>
    </div>
    <p id="status">Choose a mode, then start. Use headphones so the agent does not hear itself.</p>
    <p id="prompt">Find flights to Las Vegas on August fifth. Oh, wait. Make it August eighth.</p>
    <div class="legend">
      <b>E1</b> door or lid not closed.
      <b>E2</b> drain blocked.
      <b>E3</b> water not reaching the machine.
      These are Interra’s demo labels, not a manufacturer manual. Hold the code on paper up to the webcam.
    </div>
    <video id="preview" autoplay playsinline muted></video>
    <div id="meter" aria-hidden="true"><div id="level"></div></div>
    <div class="actions">
      <button id="start" class="primary" type="button">Start</button>
      <button id="leave" type="button">Leave</button>
    </div>
    <p id="agent-audio"></p>
  </section>
  <section class="decisions">
    <h2>This session</h2>
    <div class="now" id="now" data-kind="">
      <b id="now-kind">Waiting</b>
      <p id="now-text">Nothing has been decided yet.</p>
    </div>
    <ol id="log"></ol>
  </section>
  <section class="scored">
    <h2>Scored run · 4 October 2026 · housing self-correction</h2>
    <p class="rule">This is the recorded run, kept here so a live failure does not replace it. Exact match with the organizer LLM judge off. It is not an organizer-normalized score.</p>
    <ol id="scored"></ol>
    <details>
      <summary>Start both workers, then leave them running</summary>
      <p>Voice worker, from the repo folder:</p>
      <p><code>$env:INTERRA_FDB_AGENT_NAME = "interra-benchmark"</code><br>
      <code>.\.venv\Scripts\python.exe -m agent.fdb_livekit dev</code></p>
      <p>Camera worker, in a second window. Its name is interra-camera-troubleshooter. Do not set the voice name there:</p>
      <p><code>.\.venv\Scripts\python.exe -m agent.extension_livekit dev</code></p>
      <p>This page: <code>.\.venv\Scripts\python.exe -m agent.demo_page</code></p>
    </details>
  </section>
</main>
<script type="module">
import { Room, RoomEvent, Track } from "https://cdn.jsdelivr.net/npm/livekit-client@2.15.8/+esm";

const PROMPTS = {
  voice: "Find flights to Las Vegas on August fifth. Oh, wait. Make it August eighth.",
  camera: "What does this code mean? Then: Book a check for Friday. Oh, wait. Make it Saturday. Then ask: Did it go through?"
};
const SCORED = [
  ["Heard", "One bedroom, then “actually, no. Wait,” then two bedrooms and sixteen hundred."],
  ["Executed", "search_apartments · city “my city” · bedrooms 2 · max price 1600"],
  ["Said", "A two-bedroom was found. The city was heard as “my city”; that word was not invented afterwards."]
];

const status = document.getElementById("status");
const prompt = document.getElementById("prompt");
const now = document.getElementById("now");
const nowKind = document.getElementById("now-kind");
const nowText = document.getElementById("now-text");
const log = document.getElementById("log");
const preview = document.getElementById("preview");
const level = document.getElementById("level");
const agentAudio = document.getElementById("agent-audio");
const start = document.getElementById("start");
const leave = document.getElementById("leave");

let mode = "voice";
let room = null;
let events = null;
let pendingHeard = "";

function say(text) { status.textContent = text; }

function setNow(kind, text) {
  now.dataset.kind = kind;
  nowKind.textContent = kind;
  nowText.textContent = text || "";
}

function push(kind, text) {
  const item = document.createElement("li");
  item.className = kind;
  const label = document.createElement("b");
  label.textContent = kind;
  const body = document.createElement("span");
  body.textContent = text || "";
  item.append(label, body);
  log.prepend(item);
}

function flushHeard() {
  if (!pendingHeard) return;
  push("Heard", pendingHeard);
  pendingHeard = "";
}

function formatCall(call) {
  const args = (call && call.args) || {};
  const bits = Object.entries(args).map(([key, value]) => key + " " + value);
  const name = (call && call.function) || "tool";
  return bits.length ? name + " · " + bits.join(" · ") : name;
}

function onRecord(record) {
  const kind = record.kind;
  if (kind === "transcript") {
    pendingHeard = record.transcript || pendingHeard;
    setNow("Heard", pendingHeard);
    return;
  }
  if (kind === "user_state") return;
  flushHeard();
  if (kind === "turn_held") {
    const text = record.transcript || "The call is waiting.";
    push("Held", text);
    setNow("Held", "Holding the call until you finish. " + text);
  } else if (kind === "tool_call_dropped") {
    const text = formatCall(record.call);
    push("Dropped", text);
    setNow("Dropped", "Dropped " + text + ". You kept speaking, so this call was not logged.");
  } else if (kind === "tool_call") {
    const text = formatCall(record.call);
    push("Executed", text);
    setNow("Executed", "Executed " + text + ".");
  } else if (kind === "tool_call_deduplicated") {
    const text = formatCall(record.call);
    push("Reused", text);
    setNow("Reused", "Reused " + text + ". It was not run again.");
  } else if (kind === "conversation_item" && record.role === "assistant" && record.text) {
    push("Said", record.text);
    setNow("Said", record.text);
  }
}

function watchMicrophone(mediaStream) {
  const context = new AudioContext();
  const source = context.createMediaStreamSource(mediaStream);
  const analyser = context.createAnalyser();
  analyser.fftSize = 256;
  source.connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);
  const draw = () => {
    analyser.getByteTimeDomainData(samples);
    let peak = 0;
    for (const value of samples) peak = Math.max(peak, Math.abs(value - 128));
    level.style.width = Math.min(100, peak * 2) + "%";
    requestAnimationFrame(draw);
  };
  draw();
}

function setMode(next) {
  mode = next;
  document.body.dataset.mode = next;
  prompt.textContent = PROMPTS[next];
  document.getElementById("mode-voice").setAttribute("aria-pressed", String(next === "voice"));
  document.getElementById("mode-camera").setAttribute("aria-pressed", String(next === "camera"));
}

async function stopSession(enable) {
  if (events) { events.close(); events = null; }
  if (room) {
    const current = room;
    room = null;
    await current.disconnect();
  }
  if (enable) start.disabled = false;
}

document.getElementById("mode-voice").addEventListener("click", async () => {
  await stopSession(true);
  setMode("voice");
  say("Voice mode. The benchmark worker must be running under the name interra-benchmark.");
});
document.getElementById("mode-camera").addEventListener("click", async () => {
  await stopSession(true);
  setMode("camera");
  say("Camera mode. The camera worker must be running. Hold E1 up to the webcam.");
});
leave.addEventListener("click", () => stopSession(true).then(() => say("Left the room.")));

start.addEventListener("click", async () => {
  start.disabled = true;
  await stopSession(false);
  log.replaceChildren();
  pendingHeard = "";
  setNow("Waiting", "Connecting.");
  const roomName = "demo-" + mode + "-" + Math.random().toString(36).slice(2, 10);
  try {
    events = new EventSource("/events?room=" + encodeURIComponent(roomName));
    events.onmessage = (message) => onRecord(JSON.parse(message.data));
    const response = await fetch("/token?mode=" + mode + "&room=" + encodeURIComponent(roomName));
    if (!response.ok) throw new Error("could not open a room");
    const { url, token } = await response.json();
    const live = new Room();
    room = live;
    live.on(RoomEvent.TrackSubscribed, async (track) => {
      if (track.kind !== Track.Kind.Audio) return;
      const element = track.attach();
      element.autoplay = true;
      element.controls = true;
      element.volume = 1;
      agentAudio.replaceChildren(element);
      try { await live.startAudio(); await element.play(); } catch (error) {
        say("Sound is blocked: " + (error && error.message ? error.message : error));
      }
    });
    live.on(RoomEvent.Disconnected, () => {
      if (room === live) say("The room closed.");
    });
    await live.connect(url, token);
    await live.startAudio();
    await live.localParticipant.setMicrophoneEnabled(true);
    if (mode === "camera") await live.localParticipant.setCameraEnabled(true);
    const camera = live.localParticipant.getTrackPublication(Track.Source.Camera);
    const microphone = live.localParticipant.getTrackPublication(Track.Source.Microphone);
    if (camera && camera.track) camera.track.attach(preview);
    if (microphone && microphone.track && microphone.track.mediaStream) {
      watchMicrophone(microphone.track.mediaStream);
    }
    say(mode === "camera"
      ? "Connected. The green bar must move while you talk. Hold E1 in the picture, then say the line."
      : "Connected. The green bar must move while you talk. Say the line, pause after fifth, then correct it.");
    setNow("Waiting", "The agent is in the room. Speak, then stop.");
  } catch (error) {
    start.disabled = false;
    say("Did not start: " + (error && error.message ? error.message : error));
  }
});

setMode("voice");
for (const [kind, text] of SCORED) {
  const item = document.createElement("li");
  item.className = kind;
  const label = document.createElement("b");
  label.textContent = kind;
  const body = document.createElement("span");
  body.textContent = text;
  item.append(label, body);
  document.getElementById("scored").append(item);
}
</script>
</body>
</html>
"""


def page_html() -> str:
    return PAGE


def mint_token(mode: str, room: str) -> str:
    if mode not in {"voice", "camera"} or not ROOM_NAME.match(room) or not room.startswith("demo-" + mode + "-"):
        raise ValueError("mode and room do not match")
    url = os.environ.get("LIVEKIT_URL", "")
    key = os.environ.get("LIVEKIT_API_KEY", "")
    secret = os.environ.get("LIVEKIT_API_SECRET", "")
    if not (url and key and secret):
        raise RuntimeError("missing LiveKit configuration")
    agent = VOICE_AGENT if mode == "voice" else CAMERA_AGENT
    grants = VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True)
    dispatch = RoomConfiguration(agents=[RoomAgentDispatch(agent_name=agent)])
    return (
        AccessToken(key, secret)
        .with_identity(mode + "-" + uuid.uuid4().hex[:8])
        .with_name("Interra judge")
        .with_grants(grants)
        .with_room_config(dispatch)
        .with_ttl(datetime.timedelta(hours=1))
        .to_jwt()
    )


def read_trace_since(path: Path, room: str, start: int) -> tuple[list[dict[str, Any]], int]:
    """Read complete trace lines after a byte offset. An unfinished line stays for later."""
    if not path.is_file():
        return [], start
    found: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        handle.seek(start)
        while True:
            position = handle.tell()
            line = handle.readline()
            if not line or not line.endswith("\n"):
                return found, position
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                continue
            if record.get("room") == room and record.get("kind") in SHOWN:
                found.append(record)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/token":
            query = parse_qs(parsed.query)
            mode = (query.get("mode") or [""])[0]
            room = (query.get("room") or [""])[0]
            try:
                issued = mint_token(mode, room)
            except (ValueError, RuntimeError) as exc:
                message = str(exc).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(message)
                return
            payload = json.dumps({"url": os.environ["LIVEKIT_URL"], "token": issued}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        if parsed.path == "/events":
            query = parse_qs(parsed.query)
            room = (query.get("room") or [""])[0]
            if not ROOM_NAME.match(room):
                self.send_response(400)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            offset = TRACE_PATH.stat().st_size if TRACE_PATH.is_file() else 0
            try:
                while True:
                    records, offset = read_trace_since(TRACE_PATH, room, offset)
                    for record in records:
                        self.wfile.write(b"data: " + json.dumps(record).encode("utf-8") + b"\n\n")
                    self.wfile.write(b": keep\n\n")
                    self.wfile.flush()
                    time.sleep(0.4)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        request = str(args[0]) if args else ""
        if request.startswith("GET /token"):
            print("GET /token")
            return
        if request.startswith("GET /events"):
            print("GET /events")
            return
        super().log_message(fmt, *args)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"http://127.0.0.1:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
