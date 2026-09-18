# 01 — Product Scope

## One-sentence project definition

Build a **provider-agnostic, event-driven, interruptible agent runtime** that can reason and use dynamic tools while accepting text/audio/visual inputs, staying responsive, recovering from interruptions, preserving correct session state, rejecting stale work, and preventing duplicate side effects.

## The actual product is the runtime

Do not center the project around a demo persona such as “travel assistant” or “phone helper.”

Those are scenario adapters.

The core product is:

```text
timestamped input stream
        ↓
event normalization
        ↓
fast-path floor manager
        ↓
state/intent update
        ↓
slow-path planning
        ↓
async tool scheduler
        ↓
cancellation + idempotency + stale-result filtering
        ↓
state reconciliation
        ↓
protocol-compliant actions
```

## Primary success criteria

1. Correct task execution.
2. Correct interruption recovery.
3. Low first-substantive-response latency.
4. No duplicate state-changing calls.
5. Valid protocol output.
6. Robustness to unseen tools.
7. Robustness across text, audio, and visual inputs.
8. Deterministic traceability.

## Product principles

### Preserve what is still valid

If the user changes one slot:

```text
from=Chennai
to=Delhi
date=tomorrow
```

then says:

```text
Actually Mumbai.
```

prefer:

```text
from=Chennai
to=Mumbai
date=tomorrow
```

Do not erase unrelated valid state.

### Cancel/invalidate obsolete work

A search for Delhi is no longer valid after the destination becomes Mumbai.

### Never trust arrival order

An earlier tool request may finish later than a newer request.

Correctness is determined by:

- identity,
- state version/dependencies,
- lifecycle status,

not arrival time.

### Separate semantic reasoning from execution safety

The model may decide:

```json
{"destination": "Mumbai"}
```

but deterministic code must decide:

- which calls became stale,
- what gets canceled,
- whether a tool result is still admissible,
- whether a state-changing action is a duplicate.

### Fast does not mean dishonest

A fast-path response may say:

- “Switching the search to Mumbai.”
- “I’m checking that update.”

It must not say:

- “Done.”
- “Booked.”
- “Fixed.”

until the corresponding action is verified.

## Explicit non-goals

Do not spend core implementation time on:

- wake-word detection,
- high-fidelity speech synthesis,
- animated avatars,
- elaborate frontend design,
- persistent cross-session user memory,
- scenario-specific scripts,
- hard-coded travel/booking logic,
- training custom ASR/CV models.

## Demo scenarios versus evaluator behavior

The repository may include polished demo scenarios, but the runtime must be generic.

A scenario is acceptable only if it uses the same:

- event pipeline,
- state manager,
- manifest parser,
- planner,
- scheduler,
- cancellation mechanism,
- safety ledger,

as hidden/unseen scenarios.

No separate “demo code path.”
