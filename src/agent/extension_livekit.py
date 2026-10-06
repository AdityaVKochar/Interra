"""Camera-assisted device troubleshooting in a separate LiveKit voice session.

The benchmark agent exposes only the official tools. This extension is a second
agent outside the benchmark domains: the person shows a device on camera, and
the agent looks up safe checks, and can open or cancel a support ticket.

Coordination rules, each visible in the live console (``agent.demo_console``):

* Only the linked participant's camera is used, and each spoken turn carries
  only the newest frame; older images are removed from the model history.
* Every completed turn and every correction spoken while a tool runs advances a
  request version. A lookup that finishes for an older version is discarded and
  never answers the obsolete request; a lookup cancelled by an interruption is
  reported as cancelled and the cancellation propagates.
* Ticket writes cannot be interrupted once started, are skipped if the turn was
  already interrupted, and never run twice: the desk returns the open ticket
  for a repeated request.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import asdict
import json
import os
from pathlib import Path
import time
from typing import Any, Callable
import uuid

from agent.fdb_livekit import FdbConfig, livekit_llm_model, livekit_speech_models
from agent.troubleshooting import TicketDesk, TurnGuard, lookup_guide

try:  # resolved by the function-tool schema builder; optional for unit tests
    from livekit.agents import RunContext
except ImportError:  # pragma: no cover
    RunContext = Any  # type: ignore[assignment,misc]


EXTENSION_INSTRUCTIONS = """
You help a person troubleshoot a device they show on camera, by voice.
Use the current image and the person's words together. The latest frame is the
only image you have; describe only details you can actually see in it, such as
which lights are on, their colours, labels and cables. Ask for a closer view
when labels or controls are unclear.

Tools:
- look_up_fix(device, symptom): call it once you know the device and the
  problem, before giving steps. Give the person one check at a time, in order,
  and wait for their answer before the next one.
- open_support_ticket(device, problem, summary): only when the person asks for
  help from a technician or agrees to it, or when the guide says to escalate.
- cancel_support_ticket(ticket_id, reason): when the person says a ticket is
  wrong or no longer needed.

If the person corrects the device or the problem, even mid-sentence, drop the
earlier plan and use their latest words and the latest frame. If a tool result
says it was discarded, look up again with the latest details. If the person
names a different device than an open ticket, cancel that ticket before opening
a new one. Never claim a repair or a remote action happened unless a tool result
says so. If anything is hot, smoking, sparking or smells burnt, tell them to stop
and unplug it if safe. If no camera frame is available, ask the person to turn
on the camera.
""".strip()


class LatestFrameSource:
    """Own one active video stream and keep only its latest unconsumed frame."""

    def __init__(self) -> None:
        self._stream: Any | None = None
        self._latest: Any | None = None
        self._latest_at: float | None = None
        self._reader_task: asyncio.Task[Any] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = False
        self._close_task: asyncio.Task[Any] | None = None
        self._errors: list[BaseException] = []
        self.frames_seen = 0
        self.frames_replaced = 0

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

    def take_with_age(self) -> tuple[Any | None, float | None]:
        """The latest frame and its age in seconds, consuming it."""
        captured = self._latest_at
        frame = self.take()
        return frame, (time.monotonic() - captured) if frame is not None and captured is not None else None

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
                if self._latest is not None:
                    self.frames_replaced += 1
                self._latest = event.frame
                self._latest_at = time.monotonic()
                self.frames_seen += 1
        except asyncio.CancelledError:
            raise


def clear_previous_images(turn_ctx: Any, image_type: type) -> int:
    """Keep conversational text while removing visual evidence from older turns."""
    removed = 0
    for message in turn_ctx.items:
        if isinstance(getattr(message, "content", None), list):
            kept = [item for item in message.content if not isinstance(item, image_type)]
            removed += len(message.content) - len(kept)
            message.content = kept
    return removed


def camera_matches(participant: Any, publication: Any, identity: str, camera_source: Any) -> bool:
    return participant.identity == identity and publication.source == camera_source


def frame_thumbnail(frame: Any, width: int = 192, height: int = 144) -> str | None:
    """A small base64 JPEG of the frame sent to the model, for the console."""
    try:
        from livekit.agents.utils import images

        data = images.encode(frame, images.EncodeOptions(
            format="JPEG", quality=60,
            resize_options=images.ResizeOptions(width=width, height=height, strategy="scale_aspect_fit"),
        ))
    except Exception:
        return None
    return base64.b64encode(data).decode("ascii")


def _call_id() -> str:
    return "call_" + uuid.uuid4().hex[:8]


class TroubleshootingTools:
    """The extension's tool behaviour, independent of the LiveKit tool wrapper."""

    def __init__(
        self, desk: TicketDesk, guard: TurnGuard, publish: Callable[..., None], *,
        lookup_seconds: float = 2.0, sleep: Callable[[float], Any] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.desk = desk
        self.guard = guard
        self.publish = publish
        self.lookup_seconds = lookup_seconds
        self._sleep = sleep
        self._clock = clock

    def _elapsed_ms(self, started: float) -> int:
        return int((self._clock() - started) * 1000)

    async def look_up_fix(self, device: str, symptom: str) -> str:
        call_id, version, started = _call_id(), self.guard.version, self._clock()
        args = {"device": device, "symptom": symptom}
        self.publish("tool_started", call_id=call_id, function="look_up_fix", args=args,
                     read_only=True, request_version=version, simulated_latency_s=self.lookup_seconds)
        try:
            # Stands in for a remote guide service, so the lookup takes time and
            # the person can interrupt it.
            await self._sleep(self.lookup_seconds)
            result = lookup_guide(device, symptom)
        except asyncio.CancelledError:
            self.publish("tool_cancelled", call_id=call_id, function="look_up_fix", args=args,
                         elapsed_ms=self._elapsed_ms(started), reason="interrupted by the person")
            raise
        if not self.guard.is_current(version):
            self.publish("stale_result_discarded", call_id=call_id, function="look_up_fix", args=args,
                         request_version=version, current_version=self.guard.version,
                         elapsed_ms=self._elapsed_ms(started), result=result)
            return json.dumps({"status": "discarded", "reason": (
                "The person changed the request while this lookup ran. "
                "Use their latest words and look up again if needed.")})
        self.publish("tool_finished", call_id=call_id, function="look_up_fix", args=args, status="ok",
                     elapsed_ms=self._elapsed_ms(started), result=result)
        return json.dumps({"status": "ok", **result})

    async def open_support_ticket(self, device: str, problem: str, summary: str) -> str:
        call_id, started = _call_id(), self._clock()
        args = {"device": device, "problem": problem, "summary": summary}
        self.publish("tool_started", call_id=call_id, function="open_support_ticket", args=args,
                     read_only=False, request_version=self.guard.version)
        ticket, created = await asyncio.to_thread(self.desk.open, device, problem, summary)
        self.publish("ticket_opened" if created else "duplicate_write_suppressed",
                     call_id=call_id, function="open_support_ticket", ticket=asdict(ticket))
        self.publish("tool_finished", call_id=call_id, function="open_support_ticket", args=args,
                     status="created" if created else "already_open", elapsed_ms=self._elapsed_ms(started),
                     result={"ticket_id": ticket.ticket_id, "status": ticket.status})
        return json.dumps({"status": "created" if created else "already_open", "ticket_id": ticket.ticket_id,
                           "device": ticket.device, "problem": ticket.problem})

    async def cancel_support_ticket(self, ticket_id: str, reason: str) -> str:
        call_id, started = _call_id(), self._clock()
        args = {"ticket_id": ticket_id, "reason": reason}
        self.publish("tool_started", call_id=call_id, function="cancel_support_ticket", args=args,
                     read_only=False, request_version=self.guard.version)
        ticket, changed = await asyncio.to_thread(self.desk.cancel, ticket_id, reason)
        if ticket is None:
            status = "not_found"
        else:
            status = "cancelled" if changed else "already_cancelled"
            self.publish("ticket_cancelled" if changed else "duplicate_write_suppressed",
                         call_id=call_id, function="cancel_support_ticket", ticket=asdict(ticket))
        self.publish("tool_finished", call_id=call_id, function="cancel_support_ticket", args=args,
                     status=status, elapsed_ms=self._elapsed_ms(started))
        return json.dumps({"status": status, "ticket_id": ticket_id})

    def write_skipped(self, function: str, args: dict[str, Any]) -> str:
        self.publish("write_skipped", function=function, args=args,
                     reason="the turn was already interrupted, so the write did not start")
        return json.dumps({"status": "skipped", "reason": "The person interrupted before this change started."})


async def entrypoint(ctx: Any) -> None:
    missing = [
        name for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError("Missing LiveKit configuration: " + ", ".join(missing))

    from livekit import rtc
    from livekit.agents import Agent, AgentSession, function_tool, inference, llm, room_io
    from livekit.plugins import silero

    from agent.ui_events import RoomEventPublisher

    config = FdbConfig.from_env()
    frames = LatestFrameSource()
    ctx.add_shutdown_callback(frames.close)
    console = RoomEventPublisher(ctx.room)
    ctx.add_shutdown_callback(console.aclose)
    guard = TurnGuard()
    desk = TicketDesk(Path(os.environ.get("INTERRA_TICKET_JOURNAL", "artifacts/support-tickets.jsonl")))
    tools = TroubleshootingTools(
        desk, guard, console.publish,
        lookup_seconds=float(os.environ.get("INTERRA_EXT_LOOKUP_SECONDS", "2.0")),
    )
    await ctx.connect()
    console.start()
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
                        console.publish("camera_linked", participant=identity, track=publication.sid)
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
                    console.publish("camera_linked", participant=identity, track=publication.sid)

            def on_track_unsubscribed(track: Any, publication: Any, participant: Any) -> None:
                if participant.identity == identity and publication.sid == self._track_sid:
                    self._track_sid = None
                    frames.detach()
                    console.publish("camera_unlinked", participant=identity, reason="camera turned off")

            self._on_track = on_track_subscribed
            ctx.room.on("track_subscribed", on_track_subscribed)
            self._on_untrack = on_track_unsubscribed
            ctx.room.on("track_unsubscribed", on_track_unsubscribed)

        async def on_user_turn_completed(
            self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
        ) -> None:
            version = guard.advance("turn completed")
            removed = clear_previous_images(turn_ctx, llm.ImageContent)
            frame, age = frames.take_with_age()
            if frame is not None:
                content = new_message.content
                if not isinstance(content, list):
                    content = [content]
                    new_message.content = content
                content.append(llm.ImageContent(image=frame))
                console.publish(
                    "frame_attached", request_version=version, width=frame.width, height=frame.height,
                    age_ms=int((age or 0) * 1000), frames_seen=frames.frames_seen,
                    frames_replaced=frames.frames_replaced, old_images_removed=removed,
                    thumbnail=await asyncio.to_thread(frame_thumbnail, frame),
                )
            else:
                new_message.content.append("[No current camera frame is available. Ask for the camera or a clearer view.]")
                console.publish("no_frame", request_version=version, old_images_removed=removed)

        async def on_exit(self) -> None:
            if self._on_track is not None:
                ctx.room.off("track_subscribed", self._on_track)
                self._on_track = None
            if self._on_untrack is not None:
                ctx.room.off("track_unsubscribed", self._on_untrack)
                self._on_untrack = None
            await frames.close()

        @function_tool(description="Look up ordered, safe checks for a device and the problem the person describes.")
        async def look_up_fix(self, device: str, symptom: str) -> str:
            """
            Args:
                device: The device as the person names it or as it appears on camera, e.g. "router".
                symptom: What is wrong, in the person's words plus what the camera shows.
            """
            return await tools.look_up_fix(device, symptom)

        @function_tool(description="Open a support ticket for a technician. Only when the person asks or agrees.")
        async def open_support_ticket(self, context: RunContext, device: str, problem: str, summary: str) -> str:
            """
            Args:
                device: The device the ticket is for.
                problem: The problem in a few words.
                summary: One sentence with what was tried and what the camera showed.
            """
            args = {"device": device, "problem": problem, "summary": summary}
            try:
                context.disallow_interruptions()
            except RuntimeError:
                return tools.write_skipped("open_support_ticket", args)
            return await tools.open_support_ticket(device, problem, summary)

        @function_tool(description="Cancel a support ticket that the person says is wrong or no longer needed.")
        async def cancel_support_ticket(self, context: RunContext, ticket_id: str, reason: str) -> str:
            """
            Args:
                ticket_id: The ticket id returned by open_support_ticket, e.g. "T-3F2A1C".
                reason: Why it is cancelled, in a few words.
            """
            args = {"ticket_id": ticket_id, "reason": reason}
            try:
                context.disallow_interruptions()
            except RuntimeError:
                return tools.write_skipped("cancel_support_ticket", args)
            return await tools.cancel_support_ticket(ticket_id, reason)

    speech_stt, speech_tts = livekit_speech_models(inference, config)
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=speech_stt,
        llm=livekit_llm_model(inference, config),
        tts=speech_tts,
        max_tool_steps=4,
    )
    tool_running: dict[str, bool] = {"value": False}

    @session.on("agent_state_changed")
    def on_agent_state(event: Any) -> None:
        tool_running["value"] = str(event.new_state) == "thinking"
        console.publish("agent_state", state=str(event.new_state))

    @session.on("user_state_changed")
    def on_user_state(event: Any) -> None:
        state = str(event.new_state)
        console.publish("user_state", state=state)
        if state == "speaking" and str(session.agent_state) in {"thinking", "speaking"}:
            console.publish("interruption", agent_state=str(session.agent_state))

    @session.on("user_input_transcribed")
    def on_transcript(event: Any) -> None:
        console.publish("transcript", transcript=event.transcript, is_final=event.is_final)
        # Words spoken while a tool runs are a correction: results for the old
        # request must not answer it.
        if event.is_final and event.transcript.strip() and tool_running["value"]:
            version = guard.advance("correction while a tool was running")
            console.publish("request_superseded", request_version=version, transcript=event.transcript)

    @session.on("conversation_item_added")
    def on_item(event: Any) -> None:
        item = event.item
        console.publish("conversation_item", role=str(getattr(item, "role", "")),
                        text=getattr(item, "text_content", None) or "",
                        interrupted=bool(getattr(item, "interrupted", False)))

    @session.on("error")
    def on_error(event: Any) -> None:
        console.publish("session_error", error=str(getattr(event, "error", event)))

    console.publish("session_started", agent="camera", participant=identity, stt=config.stt_model,
                    llm=f"{config.llm_provider}:{config.llm_model}", tts=config.tts_model,
                    lookup_seconds=tools.lookup_seconds)
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
