# Submission deck source

This is reviewable slide content for export to PPT/PDF. Team names and measured official
results must be completed by the submitters; placeholders must not be presented as final.

## Slide 1 — Interra / Theme 05

- Interruptible Real-Time Agents
- Samsung PRISM GenAI Hackathon 2026–27
- Team: **TODO: submitter-provided team details**

## Slide 2 — The problem

- Real users interrupt, hesitate and correct themselves while work is running.
- Tool and perception results can arrive out of order.
- Cancellation alone is insufficient: late callbacks can still corrupt state.
- Writes introduce duplicate side-effect risk.

## Slide 3 — Evaluation-driven requirements

- Two asynchronous queues with typed, timestamped events/actions.
- Fast substantive response plus non-blocking reasoning and tools.
- 40% completion, 35% interruption recovery, 15% latency, 10% safety/protocol.
- Hidden multimodal scenarios carry additional weight.

## Slide 4 — Architecture

- Fast Path: truthful acknowledgment and floor management.
- Slow Path: validated provider proposals and asynchronous multimodal understanding.
- Coordination: versioned state, task ownership, cancellation, stale gates and idempotency.
- Use the diagram in `docs/ARCHITECTURE.md`.

## Slide 5 — Interruption lifecycle

- Calls capture intent, state snapshot and slot dependencies.
- A localized correction preserves unrelated slots.
- Incompatible calls emit cancellation immediately after validated semantic change.
- Every result passes one lifecycle/dependency acceptance gate.

## Slide 6 — Safe dynamic tools

- Tool names and schemas come only from manifests.
- JSON Schema validation precedes dispatch.
- `call_id` identifies an attempt; `operation_key` identifies a logical write.
- Unknown write outcomes block blind retries.

## Slide 7 — Multimodal, one runtime

- WAV and PNG are asynchronous input events, not separate agents.
- Audio and vision tasks can run concurrently.
- Source event, timestamp and epoch provenance prevents delayed override.
- Ambiguous evidence produces targeted clarification, never speculative writes.

## Slide 8 — Adversarial evidence

- Deterministic virtual clock and FIFO same-timestamp tie breaking.
- Boundary tests around interruption/result order.
- Exact trace assertions cover state, cancellation, stale rejection and final snapshots.
- Local full-suite result: **update from `docs/STATUS.md` before export**.

## Slide 9 — Actual-runtime demo

- Delhi lookup dispatched.
- User barges in and changes destination to Mumbai.
- Delhi call canceled; late Delhi result visibly rejected.
- Mumbai call accepted; final state retains Chennai origin.
- Safety metrics show zero duplicate logical operations in the demo.

## Slide 10 — Limitations and next evidence

- Official Samsung evaluation kit/schema is not yet present; no official score is claimed.
- Live model/audio/vision quality remains provider-dependent and unbenchmarked.
- External write rollback requires tool-specific semantics.
- TODO before submission: team details, official public results, PPT/PDF export and <=5-minute
  recorded demo.
