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

## Phase 4 gate - passed
Dependency-aware cancellation/invalidation and a pending-user barrier prevent old tool completions
from canceling correction reasoning. Explicit interruption invalidates work but retains canonical slots
until semantics arrive. Intent switches clear old intent slots; localized patches preserve other slots.
Full suite: 22 tests passed, including eight boundary matrix cases (-50/-10/-1/0/+1/+10/+50 ms,
both insertion orders at zero), rapid corrections, stale plans, cancel acknowledgment, stale retry,
and unrelated-slot preservation. No stale result entered active planning in these cases.
Next: Phase 5 state-changing ledger and unknown-outcome handling.
Decision: FIFO insertion order resolves equal timestamps; original event timestamps remain in traces.
Explicit bindings must cover every argument and match state; absent bindings conservatively depend
on all slots. Remote cancellation acknowledgment is not required for local invalidation.

## Phase 5 gate - passed
Session ledger reserves writes atomically before emitting actions. Logical keys plus canonical
argument fingerprints block repeated proposals, including attempts using different operation keys.
Write failures, timeouts and cancellation after dispatch become OUTCOME_UNKNOWN; no automatic write
retry is permitted. Unknown outcomes block further writes until reconciled. Late success can update
only the safety ledger, never active state/planning. Cancel acknowledgments do not imply rollback.
Full suite: 25 tests passed; duplicate proposals, timeout and canceled/late-success tests added.
Limit: identical intended repeat operations require a future explicit user-authorized repeat policy;
we conservatively block them throughout the session. Persistence across process crashes is out of scope.
Next: Phase 6 truthful floor management and trace-based latency evidence.

## Phase 6 gate - passed
Truthful floor manager emits one acknowledgment per chunked text turn and on interruption.
Acknowledgment precedes provider work; trace latency uses actual injected-clock values and preserved
input timestamps. Full suite: 27 tests passed, including pending-provider latency and anti-spam cases.
Local virtual first-action latency is 0 seconds for immediate queue processing; this is not a live
provider benchmark or Samsung score. Exact baseline trace updated to require the added floor actions.
Next: Phase 7 configurable real provider adapter with schema repair limits and mocked transport tests.

## Phase 7 gate - passed with transport mocks
Added configurable Ollama structured-output adapter and httpx async transport, bounded schema repair,
provider failure fallback and injected-clock reasoning deadlines. Runtime is unchanged when swapping
scripted and real adapter implementations. Full suite: 31 tests passed, including mocked HTTP
request/response, schema repair/exhaustion, timeout and cancellation cleanup.
Adapter contract checked against https://docs.ollama.com/api/chat and
https://docs.ollama.com/capabilities/structured-outputs on 2026-09-19.
No live model endpoint/model was supplied; no live quality or latency result is claimed.
Next: Phase 8 WAV parsing, asynchronous audio provider interface and provenance-gated observations.

## Phase 8 gate - passed
PCM WAV validation, asynchronous audio boundary, configurable raw-WAV HTTP adapter, source timestamps
and epoch-gated observations integrated into the existing runtime. Local protocol uses bounded
base64 media references; evaluator-specific path/bytes resolution remains an adapter responsibility.
Full suite: 36 tests passed. Audio-only, active-call correction, ambiguous/invalid WAV and delayed
interpretation rejection are covered. Providers are mocked; live speech accuracy is not measured.
Failure/root cause: truncated WAV raised EOFError with an empty string; truthiness-based error checks
misclassified failure as success. Replaced both planning/perception checks with explicit None checks,
added empty-exception regression, and made harness trace saving unconditional on failure.
Next: Phase 9 PNG/vision adapter, ambiguity and delayed-frame cases.
