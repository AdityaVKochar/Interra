"""Internal JSON protocol; SamsungProtocol owns the official queue boundary."""
import json
from typing import Protocol
from jsonschema import Draft202012Validator
from .models import Action, Event


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


S = {"type": "string", "minLength": 1}
D = {"type": "object"}
B = {"type": "boolean"}
EVENT_PAYLOADS = {
    "TEXT_CHUNK": obj({"text": {"type": "string"}, "end_of_turn": B}),
    "INTERRUPTION": obj({"reason": S, "text": {"type": "string"}}, ["reason"]),
    "TOOL_MANIFEST": obj({"tools": {"type": "array", "items": D}}),
    "TOOL_RESULT": obj({"call_id": S, "ok": B, "result": {},
                         "error": {"type": ["string", "null"]}}, ["call_id", "ok", "result"]),
    "CANCEL_ACK": obj({"call_id": S}),
    "AUDIO_CLIP": obj({"mime_type": {"const": "audio/wav"}, "data_ref": S,
                       "end_of_turn": B}, ["mime_type", "data_ref"]),
    "VIDEO_FRAME": obj({"mime_type": {"const": "image/png"}, "data_ref": S, "frame_id": S,
                        "device_hint": S}, ["mime_type", "data_ref", "frame_id"]),
}
ACTION_PAYLOADS = {
    "SPEAK": obj({"text": S}), "CLARIFY": obj({"question": S}),
    "TOOL_CALL": obj({"call_id": S, "tool_name": S, "arguments": D, "operation_key": S},
                     ["call_id", "tool_name", "arguments"]),
    "CANCEL_TOOL_CALL": obj({"call_id": S}),
    "FINAL": obj({"text": S, "state_snapshot": obj({
        "intent": {"type": ["string", "null"]}, "slots": D})}),
}
for schema in ACTION_PAYLOADS.values():
    schema["properties"]["state_snapshot"] = obj({"intent": {"type": ["string", "null"]}, "slots": D})
EVENT_VALIDATORS = {
    kind: Draft202012Validator(schema)
    for kind, schema in EVENT_PAYLOADS.items()
}
ACTION_VALIDATORS = {
    kind: Draft202012Validator(schema)
    for kind, schema in ACTION_PAYLOADS.items()
}


class ProtocolAdapter(Protocol):
    def decode(self, value: str | dict) -> Event: ...
    def encode(self, action: Action) -> str: ...


class LocalProtocol:
    def decode(self, value: str | dict) -> Event:
        event = Event.model_validate_json(value) if isinstance(value, str) else Event.model_validate(value)
        EVENT_VALIDATORS[event.type].validate(event.payload)
        return event.model_copy(deep=True)

    def encode(self, action: Action) -> str:
        ACTION_VALIDATORS[action.type].validate(action.payload)
        return json.dumps(action.model_dump(mode="json"), allow_nan=False, sort_keys=True)
