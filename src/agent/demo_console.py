"""Local web console for recording the demo: watch the agents work, live.

    python -m agent.demo_console            # http://127.0.0.1:8787

The page joins a LiveKit room in the browser and shows the conversation as it
happens: the camera, both audio streams, live transcripts, the agent's state and
a timeline of what the agent does underneath, from the events the agents publish
on the ``interra.events`` data topic (tool calls with arguments and timings,
cancelled and stale results, suppressed duplicate writes, held turns, and the
camera frame attached to each turn).

Two modes:

* Benchmark: pick a released FDB-v3 recording. The console joins the room as a
  hidden, listen-only viewer (the benchmark agent links to the first visible
  participant, so it cannot pick the viewer), then runs the official
  ``livekit_inference.py`` recorder to play the human recording into the room.
  Start the agent with ``INTERRA_UI_EVENTS=1 python scripts/fdb_v3.py agent``.
* Camera: dispatches ``interra-camera-troubleshooter`` into a new room and joins
  with camera and microphone. Start ``python -m agent.extension_livekit start``.

The API keys stay in this process. The browser only receives a two-hour room
token. The server listens on 127.0.0.1 only.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
import uuid
import wave

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / "demo_console_static"
CAMERA_AGENT = "interra-camera-troubleshooter"
REQUIRED = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
_RECORDING_NAME = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def v3_root() -> Path:
    return Path(os.environ.get("INTERRA_FDB_V3_ROOT", ROOT / ".runtime/Full-Duplex-Bench/v3"))


def data_root() -> Path:
    return Path(os.environ.get("INTERRA_FDB_DATA_ROOT", v3_root() / "fdb_v3_data_released"))


def trace_path() -> Path:
    return Path(os.environ.get("INTERRA_FDB_TRACE_DIR", ROOT / "artifacts/fdb_v3")) / "livekit-agent.jsonl"


def missing_credentials() -> list[str]:
    return [name for name in REQUIRED if not os.environ.get(name)]


def room_token(room: str, identity: str, *, hidden: bool) -> str:
    """A two-hour token for one room. A hidden viewer only listens and is invisible to agents."""
    from livekit import api

    grants = api.VideoGrants(
        room_join=True, room=room, can_subscribe=True,
        can_publish=not hidden, can_publish_data=not hidden, hidden=hidden,
    )
    return (
        api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity(identity).with_name(identity).with_ttl(timedelta(hours=2))
        .with_grants(grants).to_jwt()
    )


async def dispatch_camera_agent(room: str) -> None:
    from livekit import api

    async with api.LiveKitAPI() as client:
        await client.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(agent_name=CAMERA_AGENT, room=room))


def scenario_id(folder_name: str) -> str:
    """Folder names are ``<scenario id>_<speaker id>``, e.g. ``travel_07_5ff07b5e...``."""
    return folder_name.rsplit("_", 1)[0]


def wav_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / float(handle.getframerate())
    except (OSError, wave.Error, ZeroDivisionError):
        return None


def list_recordings() -> list[dict[str, Any]]:
    """Released recordings with display metadata only; expected answers are never sent."""
    notes: dict[str, dict[str, Any]] = {}
    labels = v3_root() / "benchmark_data_v2.json"
    if labels.is_file():
        notes = {item["id"]: item for item in json.loads(labels.read_text(encoding="utf-8"))["scenarios"]}
    rows = []
    for wav in sorted(data_root().glob("*/input.wav")):
        note = notes.get(scenario_id(wav.parent.name), {})
        rows.append({
            "name": wav.parent.name,
            "scenario": scenario_id(wav.parent.name),
            "title": note.get("title", ""),
            "domain": note.get("domain", ""),
            "difficulty": note.get("difficulty", ""),
            "features": note.get("disfluency_features", []),
            "rollback": bool(note.get("state_rollback_test")),
            "tools_expected": note.get("num_expected_calls"),
            "seconds": wav_seconds(wav),
        })
    rows.sort(key=lambda row: (not ("SELF_CORRECTION" in row["features"] or row["rollback"]), row["name"]))
    return rows


def tool_calls_for(room: str) -> list[dict[str, Any]]:
    path = trace_path()
    if not path.is_file():
        return []
    calls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            if event.get("room") == room and event.get("kind") == "tool_call":
                calls.append({**event["call"], "result": event.get("result")})
    return calls


class Playbacks:
    """The recorder subprocesses this console started, one per room, all owned."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}

    def status(self, room: str) -> dict[str, Any] | None:
        run = self._runs.get(room)
        if run is None:
            return None
        process = run["process"]
        state = "playing" if process.returncode is None else ("done" if process.returncode == 0 else "failed")
        return {"room": room, "recording": run["recording"], "state": state, "returncode": process.returncode,
                "seconds": run["seconds"], "output": str(run["output"]), "log_tail": run["log"][-12:]}

    async def start(self, room: str, recording: str) -> dict[str, Any]:
        if room in self._runs and self._runs[room]["process"].returncode is None:
            raise ValueError("A recording is already playing in this room")
        wav = data_root() / recording / "input.wav"
        if not _RECORDING_NAME.match(recording) or not wav.is_file():
            raise FileNotFoundError(recording)
        output = ROOT / "artifacts/demo" / f"{recording}-{room}-agent.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(v3_root() / "livekit_inference.py"), "-i", str(wav), "-o", str(output),
            "--room", room, cwd=str(v3_root()), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        run = {"process": process, "recording": recording, "output": output, "seconds": wav_seconds(wav), "log": []}
        run["reader"] = asyncio.create_task(self._collect(process, run["log"]))
        self._runs[room] = run
        return self.status(room) or {}

    async def _collect(self, process: asyncio.subprocess.Process, log: list[str]) -> None:
        assert process.stdout is not None
        async for line in process.stdout:
            log.append(line.decode("utf-8", "replace").rstrip())
            del log[:-200]
        await process.wait()

    async def aclose(self) -> None:
        for run in self._runs.values():
            if run["process"].returncode is None:
                run["process"].terminate()
            await asyncio.gather(run["process"].wait(), run["reader"], return_exceptions=True)


def create_app() -> Any:
    from aiohttp import web

    playbacks = Playbacks()

    async def index(_: web.Request) -> web.StreamResponse:
        return web.FileResponse(STATIC / "index.html")

    async def config(_: web.Request) -> web.Response:
        return web.json_response({
            "missing_credentials": missing_credentials(),
            "livekit_url": os.environ.get("LIVEKIT_URL", ""),
            "models": {
                "stt": os.environ.get("INTERRA_FDB_STT_MODEL", "deepgram/nova-3"),
                "llm": os.environ.get("INTERRA_FDB_LLM_MODEL", "openai/gpt-4.1-mini"),
                "tts": os.environ.get("INTERRA_FDB_TTS_MODEL", "cartesia/sonic-3"),
            },
            "recordings": list_recordings(),
            "data_root": str(data_root()),
        })

    async def session(request: web.Request) -> web.Response:
        if missing := missing_credentials():
            return web.json_response({"error": "Set " + ", ".join(missing)}, status=400)
        body = await request.json()
        mode = body.get("mode")
        if mode == "camera":
            room = f"interra-camera-{uuid.uuid4().hex[:8]}"
            await dispatch_camera_agent(room)
            token = room_token(room, "demo-user", hidden=False)
        elif mode == "benchmark":
            room = f"interra-demo-{uuid.uuid4().hex[:8]}"
            token = room_token(room, "demo-viewer", hidden=True)
        else:
            return web.json_response({"error": "mode must be camera or benchmark"}, status=400)
        return web.json_response({"mode": mode, "room": room, "url": os.environ["LIVEKIT_URL"], "token": token})

    async def play(request: web.Request) -> web.Response:
        body = await request.json()
        room, recording = str(body.get("room", "")), str(body.get("recording", ""))
        if not room.startswith("interra-demo-"):
            return web.json_response({"error": "unknown room"}, status=400)
        try:
            return web.json_response(await playbacks.start(room, recording))
        except FileNotFoundError:
            return web.json_response({"error": f"no released recording named {recording!r}"}, status=404)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=409)

    async def status(request: web.Request) -> web.Response:
        room = request.query.get("room", "")
        state = playbacks.status(room)
        if state is None:
            return web.json_response({"error": "unknown room"}, status=404)
        return web.json_response({**state, "tool_calls": tool_calls_for(room)})

    async def close_playbacks(_: web.Application) -> None:
        await playbacks.aclose()

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/config", config)
    app.router.add_post("/api/session", session)
    app.router.add_post("/api/benchmark/play", play)
    app.router.add_get("/api/benchmark/status", status)
    app.router.add_static("/static", STATIC)
    app.on_cleanup.append(close_playbacks)
    return app


def main(argv: list[str] | None = None) -> None:
    from aiohttp import web

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    if missing := missing_credentials():
        print("Warning: set " + ", ".join(missing) + " before starting a session.", flush=True)
    print(f"Interra demo console: http://127.0.0.1:{args.port}", flush=True)
    web.run_app(create_app(), host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
