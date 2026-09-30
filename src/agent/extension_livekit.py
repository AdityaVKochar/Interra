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
        self._close_task: asyncio.Task[Any] | None = None
        self._errors: list[BaseException] = []

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
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    def detach(self) -> None:
        """Invalidate a camera immediately, including an unconsumed frame."""
        stream, self._stream = self._stream, None
        self._latest = None
        if self._reader_task is not None:
            self._reader_task.cancel()
        if stream is not None:
            self._own(asyncio.create_task(stream.aclose()))

    async def _close(self) -> None:
        self._closed = True
        self.detach()
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
        if self._errors:
            raise self._errors[0]

    def _own(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            self._errors.append(error)

    async def _read(self, stream: Any) -> None:
        try:
            async for event in stream:
                if self._stream is not stream or self._closed:
                    return
                # A newer frame replaces one captured before a correction.
                self._latest = event.frame
        except asyncio.CancelledError:
            raise


def clear_previous_images(turn_ctx: Any, image_type: type) -> None:
    """Keep conversational text while removing visual evidence from older turns."""
    for message in turn_ctx.items:
        if isinstance(getattr(message, "content", None), list):
            message.content = [item for item in message.content if not isinstance(item, image_type)]


def camera_matches(participant: Any, publication: Any, identity: str, camera_source: Any) -> bool:
    return participant.identity == identity and publication.source == camera_source


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
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    identity = participant.identity

    class CameraTroubleshooter(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=EXTENSION_INSTRUCTIONS)
            self._on_track: Any | None = None
            self._on_untrack: Any | None = None
            self._track_sid: str | None = None

        async def on_enter(self) -> None:
            for remote in ctx.room.remote_participants.values():
                for publication in remote.track_publications.values():
                    track = publication.track
                    if (track is not None and track.kind == rtc.TrackKind.KIND_VIDEO
                            and camera_matches(remote, publication, identity, rtc.TrackSource.SOURCE_CAMERA)):
                        self._track_sid = publication.sid
                        frames.attach(rtc.VideoStream(track))
                        break

            def on_track_subscribed(
                track: rtc.Track,
                publication: rtc.RemoteTrackPublication,
                participant: rtc.RemoteParticipant,
            ) -> None:
                if (track.kind == rtc.TrackKind.KIND_VIDEO
                        and camera_matches(participant, publication, identity, rtc.TrackSource.SOURCE_CAMERA)):
                    self._track_sid = publication.sid
                    frames.attach(rtc.VideoStream(track))

            def on_track_unsubscribed(track: Any, publication: Any, participant: Any) -> None:
                if participant.identity == identity and publication.sid == self._track_sid:
                    self._track_sid = None
                    frames.detach()

            self._on_track = on_track_subscribed
            ctx.room.on("track_subscribed", on_track_subscribed)
            self._on_untrack = on_track_unsubscribed
            ctx.room.on("track_unsubscribed", on_track_unsubscribed)

        async def on_user_turn_completed(
            self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
        ) -> None:
            clear_previous_images(turn_ctx, llm.ImageContent)
            frame = frames.take()
            if frame is not None:
                content = new_message.content
                if not isinstance(content, list):
                    content = [content]
                    new_message.content = content
                content.append(llm.ImageContent(image=frame))
            else:
                new_message.content.append("[No current camera frame is available. Ask for the camera or a clearer view.]")

        async def on_exit(self) -> None:
            if self._on_track is not None:
                ctx.room.off("track_subscribed", self._on_track)
                self._on_track = None
            if self._on_untrack is not None:
                ctx.room.off("track_unsubscribed", self._on_untrack)
                self._on_untrack = None
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
        room_options=room_io.RoomOptions(close_on_disconnect=True, participant_identity=identity),
    )


def main() -> None:
    from livekit import agents
    from livekit.agents import AgentServer

    server = AgentServer()
    server.rtc_session(agent_name="interra-camera-troubleshooter")(entrypoint)
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
