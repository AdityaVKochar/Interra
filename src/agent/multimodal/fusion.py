"""Owned perception tasks and source-epoch acceptance gate."""
import asyncio
from dataclasses import dataclass
from .audio import understand_audio
from .vision import understand_image


@dataclass
class PerceptionResult:
    source_id: str
    source_timestamp: float
    epoch: int
    modality: str
    value: object = None
    error: str | None = None


class PerceptionManager:
    def __init__(self, runtime, audio_provider=None, vision_provider=None):
        self.runtime = runtime
        self.audio_provider = audio_provider
        self.vision_provider = vision_provider
        self.tasks = {}
        self.latest = {}
        self.accepted = {}

    def invalidate(self):
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()
        self.latest.clear()
        self.accepted.clear()

    def start(self, event):
        r = self.runtime
        modality = "audio" if event.type == "AUDIO_CLIP" else "vision"
        provider = self.audio_provider if modality == "audio" else self.vision_provider
        understand = understand_audio if modality == "audio" else understand_image
        if provider is None:
            r.trace.record("PERCEPTION_FAILED", source_id=event.event_id, error=f"{modality} provider not configured")
            r.emit("CLARIFY", question=f"{modality.capitalize()} understanding is not configured. Please send the request as text.")
            return
        epoch = r.epoch
        previous_id = self.latest.get(modality)
        previous_task = self.tasks.pop(previous_id, None)
        if previous_task is not None:
            previous_task.cancel()
        self.accepted.pop(modality, None)
        self.latest[modality] = event.event_id
        r.trace.record("PERCEPTION_STARTED", source_id=event.event_id, source_timestamp=event.timestamp, epoch=epoch, modality=modality)
        async def work():
            try:
                value = await understand(provider, event.payload["data_ref"])
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
            r.emit("CLARIFY", question=f"I could not understand that {result.modality} input. Could you describe it in text?")
            return
        observation = result.value
        r.trace.record("OBSERVATION_ACCEPTED", source_id=result.source_id, source_timestamp=result.source_timestamp,
                       epoch=result.epoch, modality=result.modality, observation=observation.model_dump())
        if observation.ambiguous:
            r.emit("CLARIFY", question=observation.question or f"Could you clarify the {result.modality} input?")
            return
        self.accepted[result.modality] = {
            "source_event_id": result.source_id,
            "source_timestamp": result.source_timestamp,
            "epoch": result.epoch,
            "observation": observation.model_dump(),
        }
        observations = {
            modality: provenance["observation"]
            for modality, provenance in self.accepted.items()
        }
        text_parts = []
        if "audio" in observations:
            text_parts.append(observations["audio"]["transcript"])
        if "vision" in observations:
            text_parts.append(observations["vision"]["summary"])
        r.trace.record(
            "FUSION_CONTEXT_UPDATED",
            modalities=sorted(observations),
            sources={
                modality: provenance["source_event_id"]
                for modality, provenance in self.accepted.items()
            },
        )
        r.last_input = {
            "text": " ".join(part for part in text_parts if part),
            "observation": observation.model_dump(),
            "observations": observations,
            "observation_provenance": {
                modality: {
                    key: value
                    for key, value in provenance.items()
                    if key != "observation"
                }
                for modality, provenance in self.accepted.items()
            },
            "source_event_id": result.source_id,
            "source_timestamp": result.source_timestamp,
            "modality": result.modality,
        }
        r.start_plan()
