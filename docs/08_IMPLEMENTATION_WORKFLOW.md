# 08 — Implementation Workflow

This file tells the coding agent exactly what to build, in order.

Do not skip phase gates.

---

# Phase 0 — Repository and evaluator reconnaissance

## Tasks

- Inspect repo.
- Locate official evaluation kit if present.
- Identify exact input/output schemas.
- Identify entrypoint expected by evaluator.
- Identify dependency/install constraints.
- Record findings in `docs/STATUS.md`.

## Gate

No implementation assumptions contradict the official kit.

---

# Phase 1 — Domain models + protocol shell

## Build

- event models,
- action models,
- state model,
- tool manifest model,
- tool call model,
- trace model,
- clock abstraction,
- protocol adapter interface.

## Tests

- schema round-trips,
- invalid payload rejection,
- unique IDs,
- state serialization,
- tool manifest normalization.

## Gate

All core objects are typed and testable without any LLM/API.

---

# Phase 2 — Text-only single-turn runtime

## Build

- session runtime,
- input queue consumer,
- output queue emitter,
- state manager,
- mock planner,
- mock read-only tool,
- trace recorder.

Flow:

```text
text turn → state → plan → tool → result → final
```

## Gate

Basic deterministic scenario passes with exact trace assertions.

---

# Phase 3 — Dynamic tools + scheduler

## Build

- manifest registry,
- argument validation,
- tool scheduler,
- call registry,
- timeout/failure handling,
- read-only retry policy.

## Gate

- chained calls pass,
- unseen-tool test passes,
- tool failure/timeout does not block runtime.

---

# Phase 4 — Interruption engine

This is the highest-priority phase.

## Build

- state versioning,
- changed-key detection,
- dependency tracking,
- invalidation,
- cancellation action emission,
- stale-result rejection,
- intent switch handling,
- localized slot updates.

## Required tests

- Delhi → Mumbai,
- Delhi → Mumbai → Bengaluru,
- result immediately before interrupt,
- result immediately after interrupt,
- stale result after cancellation,
- retry becoming stale.

## Gate

Zero stale accepted results in the adversarial timing matrix.

Do not proceed if this gate fails.

---

# Phase 5 — State-changing safety/idempotency

## Build

- effect classification,
- logical operation key,
- safety ledger,
- duplicate-blocking,
- uncertain-outcome behavior,
- no blind write retry.

## Gate

Repeated proposals/results never dispatch duplicate state-changing operations.

---

# Phase 6 — Fast path / floor management

## Build

- truthful rapid acknowledgment,
- clarification fast path,
- progress narration policy,
- anti-filler-spam rule.

Do not mix fast acknowledgment with actual finalization.

## Local target

Aim for a first substantive action within a few hundred milliseconds in the evaluator's time model. Do not hard-code a fake timestamp to satisfy this.

## Gate

Latency trace exists and fast output never falsely claims completion.

---

# Phase 7 — Real planner/provider integration

Only now connect a real reasoning model.

## Build

- provider interface,
- structured planner schema,
- tool grounding from manifests,
- bounded schema-repair/retry,
- safe failure fallback.

## Gate

Swap between mock and real planner without changing runtime code.

---

# Phase 8 — Audio

## Build

- WAV input adapter,
- asynchronous audio understanding/transcription,
- audio-derived semantic observation,
- trace provenance.

## Gate

- normal audio scenario,
- audio correction during active call,
- delayed audio result after newer input,
all pass.

---

# Phase 9 — Vision

## Build

- PNG frame adapter,
- asynchronous vision understanding,
- structured observations,
- ambiguity handling.

## Gate

- clear frame,
- ambiguous frame,
- stale/delayed frame analysis,
all pass.

---

# Phase 10 — Multimodal fusion

## Build

Integrate:

```text
text + audio + image + tool results
```

through the same state/planning pipeline.

## Gate

Audio + visual + interruption adversarial scenario passes.

---

# Phase 11 — Official evaluator integration

When the public kit is available:

- map exact protocol,
- run all 9 public scenarios,
- inspect trace failures,
- fix root causes,
- add every discovered failure as a local regression test.

Do not create special-case code based on scenario IDs.

## Gate

Strong public-kit performance with no protocol violations.

---

# Phase 12 — Performance hardening

Profile:

- model calls,
- queue latency,
- serialization,
- tool scheduling,
- unnecessary re-planning.

Improve latency without weakening correctness.

Possible techniques:

- concurrent safe preprocessing,
- cached tool-manifest parsing within the session/runtime setup,
- short fast-path generation,
- avoid unnecessary model calls,
- speculative read-only work only when safe and cancellable.

Never speculate state-changing actions.

---

# Phase 13 — Demo mode

Only after evaluator core is stable.

Build a minimal visualization of:

- user events,
- current state snapshot,
- active calls,
- cancellations,
- stale-result rejection,
- timeline.

The UI must use the actual runtime, never a simulated fake path.

Suggested hero demo:

```text
User: Find a Chennai → Delhi flight tomorrow.
Agent dispatches search.
User interrupts: Actually Mumbai, evening only.
Old call canceled.
Old result arrives late and is visibly rejected.
New call succeeds.
Final snapshot shows Mumbai + evening.
```

Second demo can show multimodal grounding.

---

# Phase 14 — Submission packaging

Required:

- README with reproducible setup,
- Dockerfile,
- tests,
- demo instructions,
- architecture diagram,
- known limitations,
- PPT/PDF,
- <=5 min demo video: [Interra demo](https://cursor.com/artifacts/v/art-65efdeb4-9b6f-4416-839a-875b82833f5a),
- final Git tag:
  `PRISM_GENAI_HACKATHON_Y2026`

Everything referenced by submission should exist in the tagged commit.

---

# Daily execution plan for the remaining week

## Day 1

Phases 0–3.

Goal: deterministic text runtime + dynamic tool scheduler.

## Day 2

Phases 4–5.

Goal: interruption correctness + idempotency.

## Day 3

Phase 6–7 + adversarial testing.

Goal: real planner behind stable runtime.

## Day 4

Phase 8.

Goal: audio scenarios.

## Day 5

Phases 9–10.

Goal: visual + multimodal.

## Day 6

Phase 11–12.

Goal: official-kit hardening, protocol, latency.

## Day 7

Phases 13–14.

Goal: demo, deck, README, Docker, release-tag readiness.

If behind schedule, cut UI first, not correctness.
