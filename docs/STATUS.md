# Implementation status

## Current phase
Phase 12 local performance hardening passed; Phase 11 remains blocked on the absent
official kit and Phase 13 is next (2026-09-19).

## Repository baseline
Read AGENTS.md, all twelve numbered specifications, STATUS.md and root context pack.
Phases 1-10 are committed on `codex/interruptible-runtime`; Phase 12 has passing local
evidence and is ready to commit. The repository currently has 27 Python source files and
13 Python test files, plus generated JSONL scenario traces and local profiler output.
Official evaluation kit, source PDFs, external schemas and evaluator entrypoint are absent.
Python 3.11.15 is installed alongside default Python 3.12.5; target is Python 3.11.

## Requirements gaps
Phase gates 1-10 and available local Phase 12 work have recorded test evidence. Official
evaluator integration is externally blocked; demo mode and submission packaging remain.
README.md, Dockerfile, presentation/demo assets and final release tag are absent.
Definition-of-done boxes remain intentionally unchecked pending a consolidated evidence audit.
Official public-kit validation is blocked until its files are supplied.

## Exact next tasks
1. Commit Phase 12 now that its local checks pass.
2. Integrate the official kit immediately when supplied; until then, retain the explicit
   Phase 11 external blocker and do not claim evaluator compatibility.
3. Build Phase 13's minimal trace/state/call timeline using the actual runtime.
4. Complete Phase 14 reproducible README and Docker verification plus remaining submission
   assets that can be represented in the repository.
5. Audit definition-of-done evidence and do not mark externally unavailable deliverables done.
6. Re-run every available gate and inspect the final diff; do not create the final tag until
   the official-kit and human-produced submission deliverables are supplied and evidenced.

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

## Phase 9 gate - passed
Strict PNG structural/checksum validation, asynchronous vision provider boundary, structured
observations, visual fact grounding and ambiguity handling now use the same owned perception
pipeline as audio. Source event/timestamp/epoch provenance rejects delayed frame analysis after
newer text and cancellation cleanup is asserted.
Full suite: `.venv/Scripts/python -m unittest discover -v`: 40 tests passed in 1.962 seconds.
Tests cover clear frame-grounded tool use, targeted ambiguous-frame clarification with no write,
corrupt PNG rejection and stale frame analysis after newer text.
Live vision accuracy is not claimed; provider behavior is deterministic/mocked.
Next: Phase 10 combined text + audio + image + tool-result interruption scenario.

## Phase 10 gate - passed
Audio and vision now retain separately owned in-flight tasks within the same semantic epoch,
so one modality no longer cancels the other. Accepted observations are fused into one planner
context with per-modality source event, timestamp and epoch provenance; newer text or explicit
interruption still invalidates the entire obsolete perception branch.
Test-first failure proved the previous cross-modality cancellation bug (`audio_result` became
cancelled when a frame arrived). The regression now interleaves text, an explicit interruption,
audio, PNG vision, a stale old tool result, canceled partial reasoning and a current tool result.
It asserts combined context, stale-result rejection, planner cancellation and the final Mumbai
evening snapshot.
Full suite: `.venv/Scripts/python -m unittest discover -v`: 41 tests passed in 1.794 seconds.
Next: Phase 11 official evaluator adapter and nine public scenarios when the kit is supplied.

## Phase 11 - externally blocked
No Samsung evaluator package, exact schema, queue harness, expected entrypoint or nine public
scenarios exists in the repository. The provisional `LocalProtocol` remains isolated from the
runtime so an official adapter can replace it without changing orchestration code. No official
compatibility or public-scenario score is claimed.

## Phase 12 local performance hardening - passed
Added trace-derived runtime metrics for input-queue, first-response and cancellation latency,
planner/stale-result counts, invalid inputs, provider failures and duplicate write operation
dispatches. Runtime traces now record source timestamps for queue and cancellation latency.
Protocol and dynamic argument validators are compiled once per stable schema/manifest rather
than reconstructed for every event, action or dispatch.
The first full profile ran 41 tests in 2.700 seconds under `cProfile`; runtime-specific costs
were dominated by the event consumer and test event-loop setup. After instrumentation and two
new tests, the profiled 43-test suite ran in 2.774 seconds. These differently sized runs are
not presented as a speedup claim; focused cumulative costs remained small (protocol decode
0.040 seconds across 139 calls, registry validation 0.011 seconds across 49 calls).
An exact-trace failure caused by the new queue-latency records was fixed by requiring the new
records in the baseline trace rather than weakening the assertion.
Full unprofiled suite: `.venv/Scripts/python -m unittest discover -v`: 43 tests passed in
1.881 seconds. Local profiler files are generated under `artifacts/` and are not source code.
Next: Phase 13 minimal demo view backed by real runtime traces.
