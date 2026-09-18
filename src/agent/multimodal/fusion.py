"""Owned perception tasks and source-epoch acceptance gate."""
import asyncio
from dataclasses import dataclass
from .audio import understand_audio


@dataclass
class PerceptionResult:
    source_id: str
    source_timestamp: float
    epoch: int
    modality: str
    value: object = None
    error: str | None = None


class PerceptionManager:
    def __init__(self, runtime, audio_provider=None):
        self.runtime = runtime
        self.audio_provider = audio_provider
        self.tasks = {}
        self.latest = {}

    def invalidate(self):
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()
        self.latest.clear()

    def start(self, event):
        r = self.runtime
        modality = "audio"
        provider = self.audio_provider
        if provider is None:
            r.trace.record("PERCEPTION_FAILED", source_id=event.event_id, error="audio provider not configured")
            r.emit("CLARIFY", question="Audio understanding is not configured. Please send the request as text.")
            return
        epoch = r.epoch
        self.latest[modality] = event.event_id
        r.trace.record("PERCEPTION_STARTED", source_id=event.event_id, source_timestamp=event.timestamp, epoch=epoch, modality=modality)
        async def work():
            try:
                value = await understand_audio(provider, event.payload["data_ref"])
                r.input.put_nowait(PerceptionResult(event.event_id, event.timestamp, epoch, modality, value))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                r.input.put_nowait(PerceptionResult(event.event_id, event.timestamp, epoch, modality, error=str(exc)))
        self.tasks[event.event_id] = r.spawn(work())

    def complete(self, result):
        r = self.runtime
        self.tasks.pop(result.source_id, None)
        if result.epoch != r.epoch or self.latest.get(result.modality) != result.source_id:
            r.trace.record("STALE_PERCEPTION_DISCARDED", source_id=result.source_id, epoch=result.epoch)
            return
        if result.error is not None:
            r.trace.record("PERCEPTION_FAILED", source_id=result.source_id, error=result.error)
            r.emit("CLARIFY", question="I could not understand that audio. Could you repeat it or send text?")
            return
        observation = result.value
        r.trace.record("OBSERVATION_ACCEPTED", source_id=result.source_id, source_timestamp=result.source_timestamp,
                       epoch=result.epoch, modality=result.modality, observation=observation.model_dump())
        if observation.ambiguous:
            r.emit("CLARIFY", question=observation.question or "What did you want to change in the audio?")
            return
        r.last_input = {"text": observation.transcript, "source_event_id": result.source_id,
                        "source_timestamp": result.source_timestamp, "modality": result.modality}
        r.start_plan()
