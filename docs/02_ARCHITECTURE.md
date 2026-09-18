# 02 — Architecture

## High-level design

```text
┌──────────────────────────────────────────────────────────┐
│ INPUT QUEUE                                               │
│ text chunks | WAV | PNG | interrupt | tool result | manifest
└───────────────────────┬──────────────────────────────────┘
                        ↓
                Event Normalizer
                        ↓
                Session Runtime
                        │
        ┌───────────────┼───────────────────┐
        ↓               ↓                   ↓
   Fast Path       State Manager       Trace Recorder
        │               │                   │
        │               ↓                   │
        │          Slow-Path Planner         │
        │               │                   │
        │               ↓                   │
        │          Tool Scheduler            │
        │               │                   │
        │         ┌─────┴─────┐             │
        │         ↓           ↓             │
        │    Cancellation   Safety Ledger    │
        │         │           │             │
        └─────────┴─────┬─────┴─────────────┘
                        ↓
                  Action Emitter
                        ↓
┌──────────────────────────────────────────────────────────┐
│ OUTPUT QUEUE                                              │
│ speak | clarify | tool_call | cancel | final             │
└──────────────────────────────────────────────────────────┘
```

## Architectural rule

The runtime owns control flow.

The LLM/provider never directly:

- mutates session state,
- dispatches a real tool,
- marks a task complete,
- cancels a task,
- accepts a stale result,
- retries a write.

It produces **validated proposals** consumed by deterministic orchestration code.

---

## Components

### 1. `EventNormalizer`

Responsibility:

- map evaluator/provider input into internal typed events,
- assign/validate IDs,
- preserve timestamps,
- validate payloads,
- reject malformed events safely.

No reasoning.

### 2. `SessionRuntime`

One runtime per evaluation session.

Owns:

- input event consumption,
- state manager,
- task registry,
- planner lifecycle,
- output action queue,
- trace recorder.

Must not share mutable session state with another session.

### 3. `FloorManager` / Fast Path

Purpose:

- produce a truthful substantive acknowledgment quickly,
- ask immediate clarification when required,
- avoid silence during slower reasoning.

Inputs:

- latest event,
- current state,
- current active work.

Outputs:

- optional `SpeakAction`,
- optional immediate `ClarifyAction`.

Important:

- Fast path must not announce unverified completion.
- Avoid filler spam.
- Do not wait for slow multimodal/tool processing if a safe acknowledgment can be emitted.

### 4. `StateManager`

Owns the canonical session state.

State updates must be:

- explicit,
- versioned,
- auditable.

Provides:

- current state snapshot,
- state patch application,
- changed-key set,
- state version increment,
- state compatibility checks.

### 5. `Planner`

Slow-path intelligence.

Given:

- current state,
- current event/turn,
- available tool manifests,
- multimodal observations,
- relevant prior trace/context,

returns a validated `PlanProposal`, for example:

```json
{
  "intent": "search_flights",
  "slot_patch": {
    "destination": "Mumbai",
    "time_of_day": "evening"
  },
  "clarification": null,
  "tool_requests": [
    {
      "tool_name": "search_flights",
      "arguments": {
        "destination": "Mumbai",
        "time_of_day": "evening"
      }
    }
  ],
  "final_response": null
}
```

The exact schema may evolve, but it must remain typed and validated.

### 6. `ToolRegistry`

Parses dynamic manifests.

Must not assume fixed tool names.

Stores normalized specs such as:

- tool name,
- description,
- argument schema,
- read-only vs state-modifying,
- evaluator-specific metadata.

### 7. `ToolScheduler`

Owns the lifecycle of tool calls.

Each call receives:

- unique `call_id`,
- tool name,
- validated arguments,
- creation timestamp,
- originating state version,
- relevant state dependencies,
- effect classification,
- status.

Possible statuses should distinguish at least:

```text
CREATED
DISPATCHED
CANCEL_REQUESTED
CANCELLED
COMPLETED
FAILED
TIMED_OUT
STALE
```

If the official protocol uses different statuses, map internally.

### 8. `CancellationManager`

When state changes:

1. identify in-flight calls invalidated by that change,
2. emit cancellation action promptly,
3. mark calls so late results cannot affect the current plan.

Cancellation correctness must not depend on whether the remote tool acknowledges cancellation before returning.

### 9. `SafetyLedger`

Protect state-changing calls.

Tracks logical side effects independently of call retries.

The key concept:

- `call_id` identifies one transport/execution attempt.
- `operation_key` identifies one logical state-changing operation.

A retry must not create a second real-world action accidentally.

Default engineering policy:

- read-only calls may retry according to controlled policy,
- state-modifying calls do not auto-retry unless the manifest/evaluator explicitly provides safe idempotency semantics.

### 10. `TraceRecorder`

Record every important transition:

- input received,
- state before/after,
- planner proposal,
- call scheduled,
- call canceled,
- result received,
- stale result discarded,
- action emitted,
- error/timeout,
- final state.

The trace is required for debugging and aligns with Samsung's trace-based evaluation.

### 11. `MultimodalAdapters`

Audio and vision adapters convert raw modalities into typed observations/semantic updates.

They must not bypass the state manager.

### 12. `ProtocolAdapter`

Maps internal events/actions to the official evaluator schema.

This isolation is critical because the evaluation kit may prescribe exact field names.

---

## Concurrency model

Prefer one logical session event loop.

Long-running operations become managed async tasks.

Rules:

- every spawned task is registered;
- every task is awaited, canceled, or finalized;
- `CancelledError` is propagated/handled correctly;
- no orphan tasks;
- state mutations occur through serialized state-manager operations;
- output emission is ordered by timestamp/sequence where the official harness requires it.

Do not use shared-memory concurrency unless necessary.

`asyncio` is sufficient for the intended runtime.

---

## Clock model

Create a `Clock` abstraction:

```python
class Clock(Protocol):
    def now(self) -> float: ...
    async def sleep(self, seconds: float) -> None: ...
```

Implement:

- `RealClock` for local/manual demo,
- `VirtualClockAdapter` for evaluator/tests.

Core code should never directly depend on uncontrolled wall-clock behavior for correctness.

---

## Provider boundaries

Define provider interfaces, for example:

```python
class ReasoningProvider(Protocol):
    async def plan(...) -> PlanProposal: ...

class AudioUnderstandingProvider(Protocol):
    async def understand_wav(...) -> AudioObservation: ...

class VisionUnderstandingProvider(Protocol):
    async def understand_png(...) -> VisualObservation: ...
```

Benefits:

- easy mocking,
- easier provider swap,
- deterministic tests,
- no evaluator dependence on cloud availability.

---

## Dependency direction

Recommended rule:

```text
protocol adapter
      ↓
domain models
      ↓
runtime/coordinator
      ↓
planner/tools/multimodal adapters
      ↓
external providers
```

Domain/runtime must not import demo UI code.

---

## Performance principle

Do not block the input event loop waiting for:

- model inference,
- audio understanding,
- vision understanding,
- tool result.

Schedule these operations asynchronously and keep consuming relevant input/interrupt events.
