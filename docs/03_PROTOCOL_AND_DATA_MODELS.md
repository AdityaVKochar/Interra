# 03 — Protocol and Data Models

The official evaluation kit should define the final external JSON schema. Until then, use stable internal types and isolate evaluator-specific serialization.

## IDs

Use explicit identifiers:

- `session_id`
- `event_id`
- `action_id`
- `call_id`
- `operation_key` for logical state-changing operations

IDs must never be inferred from array position.

## Timestamps

Every event/action should carry a timestamp from the injected clock or evaluator event.

Never replace evaluator timestamps with local arrival time when the source timestamp exists.

---

## Internal input event envelope

Suggested internal representation:

```json
{
  "event_id": "evt_001",
  "session_id": "session_01",
  "timestamp": 1.250,
  "type": "TEXT_CHUNK",
  "payload": {}
}
```

### `TEXT_CHUNK`

```json
{
  "text": "Actually make it Mumbai",
  "end_of_turn": true
}
```

Text may arrive incrementally.

Do not assume every chunk is a complete user turn.

### `AUDIO_CLIP`

```json
{
  "mime_type": "audio/wav",
  "data_ref": "..."
}
```

The actual kit may provide bytes/path/base64. Adapt in `ProtocolAdapter`.

### `VIDEO_FRAME`

```json
{
  "mime_type": "image/png",
  "data_ref": "...",
  "frame_id": "frame_12"
}
```

### `INTERRUPTION`

```json
{
  "reason": "user_barge_in"
}
```

Do not assume interruption alone contains semantic correction; it may only indicate that current spoken/planned work is superseded or should yield the floor.

### `TOOL_RESULT`

```json
{
  "call_id": "call_17",
  "ok": true,
  "result": {},
  "error": null
}
```

A successful result is not automatically admissible. Check lifecycle/state compatibility first.

### `TOOL_MANIFEST`

Keep raw manifest plus normalized tool specs.

---

## Internal output action envelope

Suggested:

```json
{
  "action_id": "act_002",
  "session_id": "session_01",
  "timestamp": 1.300,
  "type": "SPEAK",
  "payload": {}
}
```

### `SPEAK`

Use for short, truthful floor-management output.

```json
{
  "text": "Switching the search to Mumbai."
}
```

### `CLARIFY`

```json
{
  "question": "Which destination did you mean?"
}
```

Clarification should be specific.

### `TOOL_CALL`

```json
{
  "call_id": "call_18",
  "tool_name": "search_flights",
  "arguments": {
    "destination": "Mumbai"
  }
}
```

### `CANCEL_TOOL_CALL`

```json
{
  "call_id": "call_17"
}
```

### `FINAL`

The official guide requires a structured state snapshot containing intent and slot values.

Internal example:

```json
{
  "text": "I found the evening options to Mumbai.",
  "state_snapshot": {
    "intent": "search_flights",
    "slots": {
      "destination": "Mumbai",
      "time_of_day": "evening"
    }
  }
}
```

Do not expose internal-only fields unless permitted by the official schema.

---

## Canonical internal session state

Suggested:

```python
@dataclass(frozen=True)
class SessionState:
    session_id: str
    version: int
    intent: str | None
    slots: Mapping[str, Any]
    pending_clarification: str | None
    observations: tuple[Observation, ...]
```

Keep active tool calls in the scheduler/registry, not embedded as mutable objects inside the immutable state snapshot.

## State patches

Represent planner changes explicitly:

```json
{
  "intent": "search_flights",
  "set_slots": {
    "destination": "Mumbai"
  },
  "remove_slots": []
}
```

The state manager should return:

```text
new_state
changed_keys
intent_changed
```

This information drives invalidation.

---

## Tool call record

Suggested internal record:

```python
@dataclass
class ToolCallRecord:
    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    effect_type: EffectType
    created_at: float
    originating_state_version: int
    dependency_keys: frozenset[str]
    operation_key: str | None
    status: ToolCallStatus
```

`dependency_keys` should identify the state whose change makes the call obsolete.

Example:

```text
search_flights(destination="Delhi", date="tomorrow")
dependencies = {"destination", "date"}
```

Changing `address` should not necessarily invalidate that call.

---

## Observation models

### Audio observation

```json
{
  "transcript": "Actually Mumbai, evening only",
  "intent_hint": null,
  "slot_hints": {
    "destination": "Mumbai",
    "time_of_day": "evening"
  },
  "ambiguous": false
}
```

### Visual observation

```json
{
  "summary": "The device screen shows a charging warning.",
  "facts": [
    {
      "key": "visible_warning",
      "value": "charging"
    }
  ],
  "ambiguous": false
}
```

Do not treat model-generated confidence numbers as proof of truth. Prefer explicit ambiguity/evidence fields and clarification when necessary.

---

## Planner proposal

Keep planner output constrained.

Suggested:

```json
{
  "state_patch": {
    "intent": "search_flights",
    "set_slots": {
      "destination": "Mumbai"
    },
    "remove_slots": []
  },
  "clarification": null,
  "tool_requests": [
    {
      "tool_name": "search_flights",
      "arguments": {
        "destination": "Mumbai"
      }
    }
  ],
  "response_mode": "CONTINUE"
}
```

Possible response modes:

```text
CONTINUE
CLARIFY
FINAL
```

Do not allow model text like `"call this tool twice just in case"` to bypass scheduler policy.

---

## Schema validation behavior

For every provider response:

1. parse,
2. validate schema,
3. validate referenced tools exist,
4. validate tool arguments,
5. validate no forbidden side effect,
6. only then apply/schedule.

On invalid output:

- retry parsing/reasoning only within a bounded policy,
- otherwise emit a safe clarification/failure,
- never execute partially parsed tool arguments.

---

## Protocol compatibility rule

When the official evaluation kit arrives:

- add an adapter for its exact input/output schema,
- preserve these internal domain models when possible,
- do not rewrite the core runtime around evaluator field names.
