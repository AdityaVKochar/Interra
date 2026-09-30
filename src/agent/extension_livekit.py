"""Camera-assisted device troubleshooting in a separate LiveKit voice session.

The benchmark agent exposes only the official tools. This extension samples the
current participant's camera frame and attaches it to the next completed voice
turn. Each session owns and closes its video reader tasks.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from agent.fdb_livekit import FdbConfig, livekit_llm_model, livekit_speech_models


EXTENSION_INSTRUCTIONS = """
You help a person troubleshoot a device they show on camera.
Use the current image and the person's words together. Describe only details
you can actually see. Ask for a closer view when labels or controls are unclear.
Offer one safe, concrete check at a time. If the person corrects the device or
symptom, use the correction and the latest frame instead of stale observations.
If no camera frame is available, ask the person to turn on the camera.
Never claim that a repair or remote action has been completed when it has not.
""".strip()


class LatestFrameSource:
    """Own one active video stream and keep only its latest unconsumed frame."""

    def __init__(self) -> None:
        self._stream: Any | None = None
        self._latest: Any | None = None
        self._reader_task: asyncio.Task[Any] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = False

    def attach(self, stream: Any) -> None:
        if self._closed:
            raise RuntimeError("Frame source is closed")
        previous_stream = self._stream
        self._stream = stream
        self._latest = None
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
        if previous_stream is not None:
            self._own(asyncio.create_task(previous_stream.aclose()))
        self._reader_task = asyncio.create_task(self._read(stream))
        self._own(self._reader_task)

    def take(self) -> Any | None:
        frame, self._latest = self._latest, None
        return frame

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        stream, self._stream = self._stream, None
        self._latest = None
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
        if stream is not None:
            await stream.aclose()
        if self._tasks:
            results = await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                    raise result

    def _own(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task)

    async def _read(self, stream: Any) -> None:
        try:
            async for event in stream:
                if self._stream is not stream or self._closed:
                    return
                # A newer frame replaces one captured before a correction.
                self._latest = event.frame
        except asyncio.CancelledError:
            raise


async def entrypoint(ctx: Any) -> None:
    missing = [
        name for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError("Missing LiveKit configuration: " + ", ".join(missing))

    from livekit import rtc
    from livekit.agents import Agent, AgentSession, inference, llm, room_io
    from livekit.plugins import silero

    config = FdbConfig.from_env()
    frames = LatestFrameSource()
    ctx.add_shutdown_callback(frames.close)

    class CameraTroubleshooter(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=EXTENSION_INSTRUCTIONS)
            self._on_track: Any | None = None

        async def on_enter(self) -> None:
            for participant in ctx.room.remote_participants.values():
                for publication in participant.track_publications.values():
                    track = publication.track
                    if track is not None and track.kind == rtc.TrackKind.KIND_VIDEO:
                        frames.attach(rtc.VideoStream(track))
                        break

            def on_track_subscribed(
                track: rtc.Track,
                publication: rtc.RemoteTrackPublication,
                participant: rtc.RemoteParticipant,
            ) -> None:
                if track.kind == rtc.TrackKind.KIND_VIDEO:
                    frames.attach(rtc.VideoStream(track))

            self._on_track = on_track_subscribed
            ctx.room.on("track_subscribed", on_track_subscribed)

        async def on_user_turn_completed(
            self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
        ) -> None:
            frame = frames.take()
            if frame is not None:
                content = new_message.content
                if not isinstance(content, list):
                    content = [content]
                    new_message.content = content
                content.append(llm.ImageContent(image=frame))

        async def on_exit(self) -> None:
            if self._on_track is not None:
                ctx.room.off("track_subscribed", self._on_track)
                self._on_track = None
            await frames.close()

    speech_stt, speech_tts = livekit_speech_models(inference, config)
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=speech_stt,
        llm=livekit_llm_model(inference, config),
        tts=speech_tts,
    )
    await session.start(
        room=ctx.room,
        agent=CameraTroubleshooter(),
        room_options=room_io.RoomOptions(close_on_disconnect=True),
    )


def main() -> None:
    from livekit import agents
    from livekit.agents import AgentServer

    server = AgentServer()
    server.rtc_session(agent_name="interra-camera-troubleshooter")(entrypoint)
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
