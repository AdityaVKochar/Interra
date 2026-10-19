"""One local page for the judge recording.

Voice and camera are two rooms on one screen. The page shows the live
transcript, the worker trace as logs, and the gate's latest decision. A scored
run from 4 October 2026 stays beside the live take so a dropped connection does
not erase the evidence; its own trace can be replayed with original timestamps.

The page itself lives in ``agent/web``. This module serves it, mints LiveKit
tokens, streams the worker trace for one room, and serves the recorded run.

Start the voice worker with INTERRA_FDB_AGENT_NAME=interra-benchmark, the
camera worker in a second terminal, then this page:

    python -m agent.demo_page
"""

from __future__ import annotations

import argparse
import datetime
import functools
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

# Imported here, on the main thread: LiveKit plugins refuse to register from
# the request threads that would otherwise import this module first.
from agent.fdb_livekit import FdbConfig

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)

PORT = 8780
VOICE_AGENT = "interra-benchmark"
CAMERA_AGENT = "interra-camera-troubleshooter"
WEB_ROOT = Path(__file__).resolve().with_name("web")
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/orb.js": ("orb.js", "text/javascript; charset=utf-8"),
    "/logo.svg": ("logo.svg", "image/svg+xml"),
    "/favicon.svg": ("logo.svg", "image/svg+xml"),
}
ROOM_NAME = re.compile(r"^demo-(voice|camera)-[a-z0-9]{6,16}$")
LIVEKIT_NAMES = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")

# The recording shown beside the live take: housing_11, a bedroom and price
# self-correction from the 4 October 2026 run, with its official strict result.
SCORED_RUN = ROOT / "docs" / "results" / "kaggle-20261004"
SCORED_TRACE = SCORED_RUN / "livekit-agent.jsonl"
SCORED_REPORT = SCORED_RUN / "interra_elevenlabs_pass_rate_report.json"
SCORED_ROOM = "eval-31fcf764"
SCORED_SCENARIO = "housing_11"


def _trace_path() -> Path:
    """The workers write here; INTERRA_FDB_TRACE_DIR moves it for both."""
    folder = Path(os.environ.get("INTERRA_FDB_TRACE_DIR", "artifacts/fdb_v3"))
    if not folder.is_absolute():
        folder = ROOT / folder
    return folder / "livekit-agent.jsonl"


TRACE_PATH = _trace_path()


def _shown_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def page_html() -> str:
    return (WEB_ROOT / "index.html").read_text(encoding="utf-8")


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


def config_payload() -> dict[str, Any]:
    """Names and settings the page shows. No secret leaves this process."""
    url = os.environ.get("LIVEKIT_URL", "")
    payload: dict[str, Any] = {
        "voice_agent": VOICE_AGENT,
        "camera_agent": CAMERA_AGENT,
        "livekit_configured": all(os.environ.get(name) for name in LIVEKIT_NAMES),
        "livekit_host": urlparse(url).hostname or "",
        "trace": _shown_path(TRACE_PATH),
    }
    try:
        config = FdbConfig.from_env()
    except ValueError as exc:
        payload["config_error"] = str(exc)
        return payload
    payload.update(
        models={
            "stt": config.stt_model,
            "llm": config.llm_model,
            "llm_provider": config.llm_provider,
            "ollama_model": config.ollama_model,
            "tts": config.tts_model,
        },
        temperature=config.llm_temperature,
        commit_quiet_seconds=config.commit_quiet_seconds,
        unfinished_turn_hold_seconds=config.unfinished_turn_hold_seconds,
    )
    return payload


def _read_records(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


@functools.lru_cache(maxsize=1)
def scored_replay() -> dict[str, Any]:
    """The recorded room's own trace and the official strict result for it.

    Nothing here is re-run or re-scored. The result is the pinned evaluator's
    entry for this scenario, or ``None`` when the report does not hold exactly one.
    """
    records = [record for record in _read_records(SCORED_TRACE) if record.get("room") == SCORED_ROOM]
    report = json.loads(SCORED_REPORT.read_text(encoding="utf-8"))
    matches = [
        entry for entry in report.get("scenario_results", [])
        if entry.get("scenario_id") == SCORED_SCENARIO
    ]
    return {
        "room": SCORED_ROOM,
        "scenario": SCORED_SCENARIO,
        "source": _shown_path(SCORED_TRACE),
        "report": _shown_path(SCORED_REPORT),
        "records": records,
        "result": matches[0] if len(matches) == 1 else None,
    }


def read_trace_since(path: Path, room: str, start: int) -> tuple[list[dict[str, Any]], int]:
    """Read one room's complete trace lines after a byte offset. An unfinished line stays for later."""
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
            if isinstance(record, dict) and record.get("room") == room:
                found.append(record)


def resume_offset(last_event_id: str | None, size: int) -> int:
    """Where a reconnecting stream continues: after the last delivered batch, or at the end."""
    if last_event_id and last_event_id.isdigit() and int(last_event_id) <= size:
        return int(last_event_id)
    return size


def _event(record: dict[str, Any], event_id: int | None = None) -> bytes:
    head = b"id: " + str(event_id).encode("ascii") + b"\n" if event_id is not None else b""
    return head + b"data: " + json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ASSETS:
            self._asset(*ASSETS[parsed.path])
        elif parsed.path == "/token":
            self._token(parse_qs(parsed.query))
        elif parsed.path == "/config":
            self._json(config_payload())
        elif parsed.path == "/replay":
            try:
                self._json(scored_replay())
            except (OSError, ValueError) as exc:
                self._text(500, "the recorded run could not be read: " + str(exc))
        elif parsed.path == "/events":
            self._events(parse_qs(parsed.query))
        else:
            self.send_response(404)
            self.end_headers()

    def _asset(self, name: str, content_type: str) -> None:
        body = (WEB_ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _text(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _token(self, query: dict[str, list[str]]) -> None:
        mode = (query.get("mode") or [""])[0]
        room = (query.get("room") or [""])[0]
        try:
            issued = mint_token(mode, room)
        except (ValueError, RuntimeError) as exc:
            self._text(400, str(exc))
            return
        self._json({"url": os.environ["LIVEKIT_URL"], "token": issued})

    def _events(self, query: dict[str, list[str]]) -> None:
        room = (query.get("room") or [""])[0]
        if not ROOM_NAME.match(room):
            self.send_response(400)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        exists = TRACE_PATH.is_file()
        resumed = self.headers.get("Last-Event-ID")
        offset = resume_offset(resumed, TRACE_PATH.stat().st_size if exists else 0)
        hello = {"trace": _shown_path(TRACE_PATH), "exists": exists, "resumed": bool(resumed)}
        quiet_since = time.monotonic()
        try:
            self.wfile.write(b"retry: 1500\nevent: hello\ndata: " + json.dumps(hello).encode("utf-8") + b"\n\n")
            self.wfile.flush()
            while True:
                if TRACE_PATH.is_file() and TRACE_PATH.stat().st_size < offset:
                    offset = 0  # the trace was replaced; read the new file from the start
                records, offset = read_trace_since(TRACE_PATH, room, offset)
                if records:
                    # The last event of a batch carries the byte offset, so a
                    # reconnect resumes after it instead of skipping records.
                    chunks = [_event(record) for record in records[:-1]]
                    chunks.append(_event(records[-1], offset))
                    self.wfile.write(b"".join(chunks))
                    self.wfile.flush()
                    quiet_since = time.monotonic()
                elif time.monotonic() - quiet_since > 2.0:
                    self.wfile.write(b": keep\n\n")
                    self.wfile.flush()
                    quiet_since = time.monotonic()
                time.sleep(0.2)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

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
    parser = argparse.ArgumentParser(description="Serve the Interra judge page.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    missing = [name for name in LIVEKIT_NAMES if not os.environ.get(name)]
    print(f"http://{args.host}:{args.port}/", flush=True)
    if missing:
        print("LiveKit is not configured (" + ", ".join(missing) + "); the recorded replay still works.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
