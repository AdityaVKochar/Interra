"""Samsung Theme 05 boundary. Never reads scenarios or evaluator annotations."""
import asyncio
import copy
import json
import math
import os
from pathlib import Path
from uuid import uuid4

from .clock import RealClock
from .models import Event
from .providers.ollama import OllamaProvider
from .providers.audio_http import HTTPAudioProvider
from .providers.vision_http import HTTPVisionProvider
from .runtime import SessionRuntime
from .kit_media import KitMediaLoader


def argument_schema(fields):
    """Convert Samsung's required booleans, including nested objects/arrays."""
    if not isinstance(fields, dict):
        raise ValueError("argument definitions must be a map")
    properties, required = {}, []
    for name, field in fields.items():
        if not isinstance(field, dict) or type(field.get("required", False)) is not bool:
            raise ValueError("invalid argument definition")
        if field.get("required"):
            required.append(name)
        schema = {k: copy.deepcopy(v) for k, v in field.items() if k != "required"}
        if schema.get("type") == "object":
            schema.update(argument_schema(schema.get("properties", {})))
        elif schema.get("type") == "array":
            item = schema.get("items", {})
            if isinstance(item, str):
                item = {"type": item}
            schema["items"] = argument_schema({"item": item})["properties"]["item"]
        if schema.get("type") not in {"string", "number", "boolean", "array", "object"}:
            raise ValueError("unsupported argument type")
        properties[name] = schema
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


class SamsungProtocol:
    def __init__(self, session_id):
        self.session_id = session_id
        self.sequence = 0
        self.audio_refs = []

    def decode(self, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("payload"), dict):
            raise ValueError("invalid event envelope")
        timestamp = raw.get("timestamp_ms")
        if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("invalid timestamp_ms")
        kind, p = raw.get("event_type"), raw["payload"]
        if kind == "scenario_end":
            return None  # The harness still delivers tool results during its tail window.
        if kind == "tool_manifest":
            if p.get("schema_version", "1.0") != "1.0" or not isinstance(p.get("tools"), dict):
                raise ValueError("invalid tool manifest")
            specs = []
            for name, tool in p["tools"].items():
                effect = {"read_only": "READ_ONLY", "state_modifying": "STATE_MODIFYING"}.get(tool.get("kind"))
                if effect is None:
                    raise ValueError("tool must declare its effect")
                specs.append(dict(name=name, description=tool.get("description", ""),
                    effect_type=effect, argument_schema=argument_schema(tool.get("args", {})),
                    max_retries=1 if effect == "READ_ONLY" else 0,
                    metadata={k: copy.deepcopy(tool[k]) for k in ("delay_range_ms", "default_result") if k in tool}))
            kind, payload = "TOOL_MANIFEST", {"tools": specs}
        elif kind == "user_speech_chunk":
            self.audio_refs.clear()
            kind, payload = "TEXT_CHUNK", {"text": p["text"], "end_of_turn": p["end_of_turn"]}
        elif kind == "interruption":
            self.audio_refs.clear()
            kind, payload = "INTERRUPTION", {"reason": "user barge-in", "text": p.get("text", "")}
        elif kind == "tool_result":
            if p.get("status") not in {"success", "error"}:
                raise ValueError("unknown result status")
            result = p["result"]
            kind, payload = "TOOL_RESULT", {"call_id": p["call_id"], "ok": p["status"] == "success",
                "result": result, "error": str(result.get("error", "tool failed")) if p["status"] == "error" else None}
        elif kind == "user_audio_chunk":
            if not isinstance(p.get("audio_ref"), str) or type(p.get("end_of_turn")) is not bool:
                raise ValueError("invalid audio chunk")
            self.audio_refs.append(p["audio_ref"])
            if len(self.audio_refs) > 64:
                self.audio_refs.clear()
                raise ValueError("too many audio chunks")
            kind, payload = "AUDIO_CLIP", {"mime_type": "audio/wav",
                "data_ref": "kit:" + json.dumps(self.audio_refs), "end_of_turn": p["end_of_turn"]}
            if p["end_of_turn"]:
                self.audio_refs.clear()
        elif kind == "video_frame":
            kind, payload = "VIDEO_FRAME", {"mime_type": "image/png", "frame_id": p["frame_id"],
                                           "data_ref": "kit:" + json.dumps([p["image_ref"]])}
            if "device_hint" in p:
                payload["device_hint"] = p["device_hint"]
        else:
            raise ValueError("unknown event type")
        self.sequence += 1
        return Event(event_id=f"{self.session_id}:input:{self.sequence}", session_id=self.session_id,
                     timestamp=float(timestamp) / 1000, type=kind, payload=payload)

    @staticmethod
    def encode(action):
        p = copy.deepcopy(action.payload)
        snapshot = p.pop("state_snapshot", None)
        kinds = {"SPEAK": "filler_speech", "CLARIFY": "clarification_request",
                 "TOOL_CALL": "tool_call", "CANCEL_TOOL_CALL": "cancel_tool", "FINAL": "final_response"}
        if action.type == "TOOL_CALL":
            p = {"call_id": p["call_id"], "api_name": p["tool_name"], "args": p["arguments"]}
        elif action.type == "CLARIFY":
            p = {"text": p["question"]}
        result = {"action": kinds[action.type], "payload": p}
        if snapshot is not None:
            result["state_snapshot"] = snapshot
        return result


class UnconfiguredProvider:
    async def plan(self, context):
        return {"clarification": "A reasoning model is not configured. Please configure INTERRA_MODEL before evaluation."}


class SessionClock(RealClock):
    def __init__(self):
        self.origin = None

    def now(self):
        now = super().now()
        if self.origin is None:
            self.origin = now
        return now - self.origin


class ParticipantAgent:
    """Official two-queue entrypoint; setup owns clients, run owns every task."""
    def __init__(self, in_queue, out_queue, *, provider=None, audio_provider=None,
                 vision_provider=None, media_root=None, clock=None):
        self.in_q, self.out_q = in_queue, out_queue
        self.provider, self.audio_provider, self.vision_provider = provider, audio_provider, vision_provider
        self.media_root = media_root
        self.clock = clock or SessionClock()
        self.runtime = None
        self.owned_clients = []

    async def setup(self):
        if self.runtime is not None:
            return
        try:
            await self.configure()
        except BaseException:
            for client in reversed(self.owned_clients):
                await client.aclose()
            self.owned_clients.clear()
            raise

    async def configure(self):
        local = os.environ.get('INTERRA_PROFILE') == 'local'
        if self.provider is None:
            model = os.environ.get("INTERRA_MODEL", 'qwen3-vl:2b' if local else '')
            self.provider = OllamaProvider(model, os.environ.get("INTERRA_OLLAMA_URL", "http://localhost:11434")) if model else UnconfiguredProvider()
            if model:
                self.owned_clients.append(self.provider)
        for attr, variable, cls in (("audio_provider", "INTERRA_AUDIO_URL", HTTPAudioProvider),
                                    ("vision_provider", "INTERRA_VISION_URL", HTTPVisionProvider)):
            if getattr(self, attr) is None and os.environ.get(variable):
                client = cls(os.environ[variable])
                setattr(self, attr, client)
                self.owned_clients.append(client)
        if local:
            from .providers.local_audio import LocalAudioProvider
            from .providers.local_vision import LocalVisionProvider
            model_root = Path(os.environ.get('INTERRA_MODEL_ROOT', '.models')).resolve()
            if self.audio_provider is None:
                self.audio_provider = LocalAudioProvider(os.environ.get('INTERRA_ASR_MODEL_PATH', str(model_root / 'whisper-base')))
                self.owned_clients.append(self.audio_provider)
            if self.vision_provider is None:
                vision_llm = self.provider
                if not isinstance(vision_llm, OllamaProvider):
                    vision_llm = OllamaProvider(os.environ.get('INTERRA_MODEL', 'qwen3-vl:2b'),
                        os.environ.get('INTERRA_OLLAMA_URL', 'http://localhost:11434'))
                    self.owned_clients.append(vision_llm)
                self.vision_provider = LocalVisionProvider(vision_llm, model_root / 'fastembed')
                self.owned_clients.append(self.vision_provider)
        for client in self.owned_clients:
            if hasattr(client, 'setup'):
                await client.setup()
        session_id = uuid4().hex
        self.protocol = SamsungProtocol(session_id)
        root = self.media_root or os.environ.get("INTERRA_MEDIA_ROOT") or Path.cwd()
        self.runtime = SessionRuntime(session_id, self.provider, self.clock,
            audio_provider=self.audio_provider, vision_provider=self.vision_provider,
            media_loader=KitMediaLoader(root), retain_frame_context=True, planner_repairs=1)

    async def run(self):
        await self.setup()
        self.clock.now()
        r = self.runtime

        async def receive():
            while True:
                raw = await self.in_q.get()
                try:
                    try:
                        event = self.protocol.decode(raw)
                        if event is None:
                            r.trace.record("SCENARIO_INPUT_ENDED")
                        else:
                            await r.input.put(event)
                    except (ValueError, TypeError, KeyError, AttributeError) as exc:
                        r.trace.record("INPUT_REJECTED", error=str(exc))
                finally:
                    self.in_q.task_done()

        async def send():
            while True:
                action = await r.output.get()
                try:
                    await self.out_q.put(self.protocol.encode(action))
                finally:
                    r.output.task_done()

        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(r.run())
                group.create_task(receive())
                group.create_task(send())
        finally:
            trace_dir = os.environ.get('INTERRA_TRACE_DIR')
            if trace_dir:
                r.trace.save(Path(trace_dir) / f'{r.session_id}.jsonl')
            for client in reversed(self.owned_clients):
                await client.aclose()
            self.owned_clients.clear()
