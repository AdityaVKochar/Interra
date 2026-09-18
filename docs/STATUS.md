# Implementation status

## Current phase
Phase 0 reconnaissance complete; Phase 1 next (2026-09-18).

## Repository baseline
Read AGENTS.md, all twelve numbered specifications, STATUS.md and root context pack.
Only specifications exist: no implementation, dependencies, tests or commits.
Official evaluation kit, source PDFs, external schemas and evaluator entrypoint are absent.
Python 3.11.15 is installed alongside default Python 3.12.5; target is Python 3.11.

## Requirements gaps
All runtime, protocol, state, scheduling, interruption, safety, provider, multimodal,
evaluation and packaging requirements remain unimplemented. No requirement is marked done.
Official public-kit validation is blocked until its files are supplied.

## Exact next tasks
1. Run baseline unittest discovery (no existing suite found).
2. Phase 1: typed models, strict local protocol, manifests, IDs, traces, injected clock;
   test validation, round trips, snapshot isolation and deterministic clock behavior.
3. Phase 2: two-queue runtime and mock planner; prove a single-turn trace.
4. Phase 3: dynamic scheduler, chaining, timeout/failure and bounded read retries.
5. Phase 4: dependency invalidation and adversarial interruption timing matrix.
6. Proceed through phases 5-10 only after each preceding gate passes.
7. Integrate official kit at phase 11 before advancing to performance/demo/release gates.

## Decisions
- Documented local envelopes are provisional; official schema compatibility is not claimed.
- One session-owned serialized coordinator; providers propose, never mutate state.
- Python 3.11, asyncio, deterministic virtual clock; no network needed for core gates.
- No final release tag until the definition of done is evidenced.

## Test log
Baseline pending. No pre-existing tests or traces.

## Phase 1 gate - passed
Strict domain/proposal models, event/action payload validation, provisional protocol adapter,
manifest normalization, deterministic IDs, isolated trace records and virtual clock implemented.
Baseline: `py -V:Astral/CPython3.11.15 -m unittest discover -v`: 0 tests, passed.
Phase gate: `.venv/Scripts/python -m unittest discover -v`: 8 tests, passed.
Dependencies: pydantic for strict model parsing, jsonschema for dynamic tool schemas.
Next: Phase 2 text-only queue runtime, state manager, planner boundary and exact scenario trace.
Limits: no runtime yet; no official schema/evaluator available.

## Phase 2 gate - passed (2026-09-19)
Session-owned two-queue runtime, serialized state manager, mockable planner, call/result path,
chunk assembly and complete JSONL traces implemented. Proposal validation precedes state mutation.
Full suite: `.venv/Scripts/python -m unittest discover -v`: 10 tests passed.
Exact single-turn trace and malformed planner/chunk scenarios added; shutdown leaves no planner tasks.
Trace files: artifacts/traces/*.jsonl (generated, not source-controlled).
Next: Phase 3 scheduler, timeouts, failures, read-only retries, chained/unseen tool tests.
Limits: interruption and writes remain disabled; phase 4/5 gates are not claimed.

## Phase 3 gate - passed
Dynamic schema-validated tools, call registry, virtual deadlines, bounded read retries and failure
handling implemented. Added chained opaque tool names, timeout/retry limits, duplicate result,
atomic batch validation and malformed input regression scenarios.
Full suite: 15 tests passed. Traces saved under artifacts/traces.
Inspection found JSON Schema errors were not caught by the input boundary; corrected with a
regression proving malformed payloads do not terminate consumption.
Next: Phase 4 dependency invalidation, pending-user barriers, late-plan/result rejection and timing matrix.
