"""Owned perception tasks and source-epoch acceptance gate."""
import asyncio
import copy
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


@dataclass
class PerceptionDeadline:
    source_id: str
    source_timestamp: float
    epoch: int
    modality: str


class PerceptionManager:
    def __init__(self, runtime, audio_provider=None, vision_provider=None):
        self.runtime = runtime
        self.audio_provider = audio_provider
        self.vision_provider = vision_provider
        self.tasks = {}
        self.latest = {}
        self.accepted = {}
        self.unresolved_modalities = set()
        self.timers = {}
        self.audio_turn_open = False
        self.frame_context = {}

    @property
    def unresolved(self):
        return bool(self.unresolved_modalities)

    def invalidate(self, preserve_vision=False):
        if preserve_vision:
            vision_id = self.latest.get("vision")
            for source_id in list(self.tasks):
                if source_id != vision_id:
                    self.tasks.pop(source_id).cancel()
                    timer = self.timers.pop(source_id, None)
                    if timer:
                        timer.cancel()
            self.latest.pop("audio", None)
            self.accepted.pop("audio", None)
            self.unresolved_modalities.discard("audio")
            self.audio_turn_open = False
            return
        for task in [*self.tasks.values(), *self.timers.values()]:
            task.cancel()
        self.tasks.clear()
        self.timers.clear()
        self.latest.clear()
        self.accepted.clear()
        self.unresolved_modalities.clear()
        self.audio_turn_open = False
        self.frame_context = {}

    def start(self, event):
        r = self.runtime
        modality = "audio" if event.type == "AUDIO_CLIP" else "vision"
        if modality == "audio":
            self.audio_turn_open = not event.payload.get("end_of_turn", True)
            if self.audio_turn_open:
                self.unresolved_modalities.add(modality)
                r.trace.record("AUDIO_ACCUMULATING", source_id=event.event_id)
                return  # The official adapter sends accumulated refs at end of turn.
        else:
            self.frame_context = {k: event.payload[k] for k in ("frame_id", "device_hint") if k in event.payload}
        self.unresolved_modalities.add(modality)
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
        previous_timer = self.timers.pop(previous_id, None)
        if previous_timer:
            previous_timer.cancel()
        self.accepted.pop(modality, None)
        self.latest[modality] = event.event_id
        r.trace.record("PERCEPTION_STARTED", source_id=event.event_id, source_timestamp=event.timestamp, epoch=epoch, modality=modality)
        async def work():
            try:
                data_ref = event.payload["data_ref"]
                if r.media_loader:
                    data_ref = await r.media_loader(event)
                value = await understand(provider, data_ref)
                r.input.put_nowait(PerceptionResult(event.event_id, event.timestamp, epoch, modality, value))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                r.input.put_nowait(PerceptionResult(event.event_id, event.timestamp, epoch, modality, error=str(exc)))
        self.tasks[event.event_id] = r.spawn(work())
        deadline = r.clock.now() + r.perception_timeout
        async def timeout():
            remaining = deadline - r.clock.now()
            if remaining > 0:
                await r.clock.sleep(remaining)
            r.input.put_nowait(PerceptionDeadline(event.event_id, event.timestamp, epoch, modality))
        self.timers[event.event_id] = r.spawn(timeout())

    def timeout(self, deadline):
        task = self.tasks.get(deadline.source_id)
        if task is None or (deadline.epoch != self.runtime.epoch and not (
                deadline.modality == "vision" and self.runtime.retain_frame_context)):
            return
        task.cancel()
        self.runtime.trace.record("PERCEPTION_TIMED_OUT", source_id=deadline.source_id)
        self.complete(PerceptionResult(deadline.source_id, deadline.source_timestamp, deadline.epoch,
                                       deadline.modality, error="perception deadline exceeded"))

    def complete(self, result):
        r = self.runtime
        task = self.tasks.pop(result.source_id, None)
        timer = self.timers.pop(result.source_id, None)
        if timer:
            timer.cancel()
        retained_frame = result.modality == "vision" and r.retain_frame_context
        if (result.epoch != r.epoch and not retained_frame) or self.latest.get(result.modality) != result.source_id:
            r.trace.record("STALE_PERCEPTION_DISCARDED", source_id=result.source_id, epoch=result.epoch)
            return
        if task is None:
            r.trace.record("DUPLICATE_PERCEPTION_DISCARDED", source_id=result.source_id)
            return
        if result.error is not None:
            r.trace.record("PERCEPTION_FAILED", source_id=result.source_id, error=result.error)
            r.emit("CLARIFY", question=f"I could not understand that {result.modality} input. Could you describe it in text?")
            return
        observation = result.value
        r.trace.record("OBSERVATION_ACCEPTED", source_id=result.source_id, source_timestamp=result.source_timestamp,
                       epoch=result.epoch, modality=result.modality, observation=observation.model_dump())
        if observation.ambiguous:
            r.clarification_context = {"uncertain_observation": observation.model_dump(),
                "source_event_id": result.source_id, "modality": result.modality}
            r.emit("CLARIFY", question=observation.question or f"Could you clarify the {result.modality} input?")
            return
        if result.modality != "audio" or not self.audio_turn_open:
            self.unresolved_modalities.discard(result.modality)
        self.accepted[result.modality] = {
            "source_event_id": result.source_id,
            "source_timestamp": result.source_timestamp,
            "epoch": result.epoch,
            "observation": observation.model_dump(),
        }
        self.refresh_context(result)
        if r.chunks or self.audio_turn_open:
            r.trace.record("FUSION_WAITING_FOR_TEXT", source_id=result.source_id)
        elif retained_frame and not r.text_input and "audio" not in self.accepted:
            r.trace.record("FRAME_CONTEXT_RETAINED", source_id=result.source_id)
        else:
            r.start_plan()

    def refresh_context(self, result=None):
        r = self.runtime
        if not self.accepted:
            r.last_input = dict(r.text_input)
            return
        observations = {
            modality: copy.deepcopy(provenance["observation"])
            for modality, provenance in self.accepted.items()
        }
        embeddings = []
        for modality, observation in observations.items():
            vector = observation.pop('image_embedding', None)
            if vector:
                embeddings.append({'source_id': self.accepted[modality]['source_event_id'],
                                   'dimensions': len(vector), 'model': observation.get('embedding_model')})
        text_parts = [r.text_input.get("text", "")]
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
            "text_input": dict(r.text_input),
            "observation": observations[result.modality] if result else next(reversed(observations.values())),
            "observations": observations,
            "available_embeddings": embeddings,
            "observation_provenance": {
                modality: {
                    key: value
                    for key, value in provenance.items()
                    if key != "observation"
                }
                for modality, provenance in self.accepted.items()
            },
        }
        if "vision" in observations:
            r.last_input["frame_context"] = dict(self.frame_context)
        if result:
            r.last_input.update(source_event_id=result.source_id, source_timestamp=result.source_timestamp,
                                modality=result.modality)
