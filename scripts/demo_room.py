"""Set up LiveKit rooms for recording the Theme 05 demo video.

Three commands, each run while the matching worker is running in another
terminal (run one worker at a time: the benchmark worker joins every room):

``list``       Released FDB-v3 recordings with self-corrections or rollbacks,
               to pick one for the video.
``benchmark``  Stream one released recording into a fresh room with the official
               ``livekit_inference.py`` recorder, after printing a hidden
               watch-only link, then print the tool calls the agent made there.
               Worker: ``python scripts/fdb_v3.py agent``.
``camera``     Dispatch the camera troubleshooter into a fresh room and print a
               link that joins it with camera and microphone.
               Worker: ``python -m agent.extension_livekit start``.

Links open https://meet.livekit.io with a short-lived room token. Credentials are
read from ``LIVEKIT_URL``, ``LIVEKIT_API_KEY`` and ``LIVEKIT_API_SECRET``; the
token is printed only to this terminal and never written to disk.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode
import uuid

ROOT = Path(__file__).resolve().parents[1]
CAMERA_AGENT = "interra-camera-troubleshooter"
MEET = "https://meet.livekit.io/custom"
REQUIRED = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")


def v3_root() -> Path:
    return Path(os.environ.get("INTERRA_FDB_V3_ROOT", ROOT / ".runtime/Full-Duplex-Bench/v3"))


def data_root() -> Path:
    return Path(os.environ.get("INTERRA_FDB_DATA_ROOT", v3_root() / "fdb_v3_data_released"))


def credentials() -> tuple[str, str, str]:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise SystemExit("Set these in the environment first: " + ", ".join(missing))
    return tuple(os.environ[name] for name in REQUIRED)  # type: ignore[return-value]


def join_link(room: str, identity: str, *, hidden: bool) -> str:
    """A Meet link for this room. A hidden viewer can listen but is invisible to agents."""
    from livekit import api

    url, key, secret = credentials()
    grants = api.VideoGrants(
        room_join=True, room=room, can_subscribe=True,
        can_publish=not hidden, can_publish_data=not hidden, hidden=hidden,
    )
    token = (
        api.AccessToken(key, secret).with_identity(identity).with_name(identity)
        .with_ttl(timedelta(hours=2)).with_grants(grants).to_jwt()
    )
    return f"{MEET}?{urlencode({'liveKitUrl': url, 'token': token})}"


async def dispatch(agent_name: str, room: str) -> None:
    from livekit import api

    credentials()
    async with api.LiveKitAPI() as client:
        await client.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=agent_name, room=room)
        )


def recordings() -> list[tuple[str, Path]]:
    folders = sorted(path.parent for path in data_root().glob("*/input.wav"))
    return [(folder.name, folder) for folder in folders]


def scenario_notes() -> dict[str, dict]:
    path = v3_root() / "benchmark_data_v2.json"
    if not path.is_file():
        return {}
    return {item["id"]: item for item in json.loads(path.read_text(encoding="utf-8"))["scenarios"]}


def scenario_id(folder_name: str) -> str:
    """Folder names are ``<scenario id>_<speaker id>``, e.g. ``travel_07_5ff07b5e...``."""
    return folder_name.rsplit("_", 1)[0]


def command_list(_: argparse.Namespace) -> None:
    notes = scenario_notes()
    found = recordings()
    if not found:
        raise SystemExit(f"No released recordings under {data_root()}; run "
                         "`python scripts/fdb_v3.py bootstrap --download-data` first.")
    for name, _folder in found:
        note = notes.get(scenario_id(name), {})
        features = note.get("disfluency_features", [])
        if note.get("state_rollback_test") or "SELF_CORRECTION" in features:
            print(f"{name}  [{note.get('difficulty', '?')}] {note.get('title', '')}  "
                  f"features={','.join(features) or '-'}")


def tool_calls_for(room: str) -> list[dict]:
    trace = Path(os.environ.get("INTERRA_FDB_TRACE_DIR", ROOT / "artifacts/fdb_v3")) / "livekit-agent.jsonl"
    if not trace.is_file():
        return []
    calls = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            if event.get("room") == room and event.get("kind") == "tool_call":
                calls.append(event["call"])
    return calls


def command_benchmark(args: argparse.Namespace) -> None:
    folder = Path(args.recording)
    if not folder.is_dir():
        folder = data_root() / args.recording
    wav = folder / "input.wav"
    if not wav.is_file():
        raise SystemExit(f"No input.wav in {folder}; pick a name from `python scripts/demo_room.py list`.")
    room = args.room or f"interra-demo-{uuid.uuid4().hex[:8]}"
    output = ROOT / "artifacts/demo" / f"{folder.name}-agent.wav"
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Recording: {folder.name}\nRoom:      {room}\n")
    print("Open this watch-only link to hear the recording and the agent live:")
    print(join_link(room, "demo-viewer", hidden=True))
    input("\nPress Enter to start streaming the recording into the room... ")
    subprocess.run(
        [sys.executable, str(v3_root() / "livekit_inference.py"), "-i", str(wav), "-o", str(output), "--room", room],
        cwd=v3_root(), check=True,
    )
    print(f"\nAgent audio: {output}")
    calls = tool_calls_for(room)
    print(f"Tool calls the agent made in {room}:" if calls else
          "No tool calls found in the trace for this room (is the worker writing to artifacts/fdb_v3?).")
    for call in calls:
        print(f"  {call['function']}({json.dumps(call.get('args', {}))})")


def command_camera(args: argparse.Namespace) -> None:
    room = args.room or f"interra-camera-{uuid.uuid4().hex[:8]}"
    asyncio.run(dispatch(CAMERA_AGENT, room))
    print(f"Dispatched {CAMERA_AGENT} to room {room}.")
    print("Open this link, allow camera and microphone, and talk to the agent:")
    print(join_link(room, args.identity, hidden=False))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="Recordings with self-corrections or rollbacks")
    bench = sub.add_parser("benchmark", help="Stream one released recording into a watched room")
    bench.add_argument("recording", help="Recording folder name (from `list`) or path")
    bench.add_argument("--room")
    camera = sub.add_parser("camera", help="Dispatch the camera troubleshooter and print a join link")
    camera.add_argument("--room")
    camera.add_argument("--identity", default="demo-user")
    args = parser.parse_args(argv)
    {"list": command_list, "benchmark": command_benchmark, "camera": command_camera}[args.command](args)


if __name__ == "__main__":
    main()
