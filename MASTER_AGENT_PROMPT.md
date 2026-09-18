# MASTER AGENT PROMPT — Samsung PRISM Theme 05

You are the principal implementation agent for **Samsung PRISM GenAI Hackathon 2026–27, Theme 05: Interruptible Real-Time Agents**.

Your job is to implement the complete project in a disciplined, test-driven way. Do not treat this as a generic chatbot project. The core challenge is **concurrency + state consistency under real-time interruptions**.

## Mandatory first action

Before writing implementation code:

1. Read `AGENTS.md`.
2. Read every file in `docs/` in numeric order.
3. Inspect the repository.
4. Create/update `docs/STATUS.md` with:
   - current phase,
   - what already exists,
   - gaps versus the requirements,
   - exact next tasks.
5. Run the existing test suite, if any.
6. Only then begin implementation.

## Non-negotiable behavior

- Follow the official Theme 05 requirements in `docs/00_REQUIREMENTS_SOURCE_OF_TRUTH.md`.
- Treat the official evaluation kit, once present in the repo, as the highest-priority executable specification.
- Never hard-code scenario-specific flows or tool names.
- Never rely on prompt wording alone for safety, cancellation, idempotency, or stale-result rejection.
- Keep the orchestration core deterministic and testable.
- Use structured schemas for model outputs.
- Use an injected/virtual clock in core logic. Do not couple correctness to `time.sleep()` or uncontrolled wall-clock timing.
- Every external model/provider must sit behind an adapter interface so the evaluator can be run with mocks.
- Every state-changing tool call must be protected against duplicate execution.
- A result from an invalidated/superseded call must never be allowed to alter the current plan.
- A user correction should modify only the affected state when possible; do not reset the whole session unless the intent truly changes.
- Audio and visual processing must be non-blocking and integrated as input events, not as a separate application.
- Emit protocol-valid structured actions with explicit identifiers.
- Preserve complete trace logs for every scenario.

## Implementation order

Implement strictly in the phase order in `docs/08_IMPLEMENTATION_WORKFLOW.md`.

Do **not** jump to UI, demo polish, or multimodal work before the text-only orchestration core passes its phase gates.

For each phase:

1. Implement the smallest correct slice.
2. Add unit tests.
3. Add deterministic scenario tests.
4. Run all previous tests.
5. Fix every regression.
6. Record results in `docs/STATUS.md`.
7. Commit only after the phase gate passes.

## Self-correction loop

When a test fails:

1. Inspect the event/action trace.
2. Identify whether the bug is in:
   - state update,
   - cancellation/invalidation,
   - tool scheduling,
   - stale-result handling,
   - idempotency,
   - model parsing,
   - multimodal adapter,
   - protocol serialization,
   - latency/floor management.
3. Fix the root cause, not only the scenario.
4. Add a regression test reproducing the exact failure.
5. Run the full suite again.

Do not weaken assertions merely to make tests pass.

## Completion rule

Do not declare the project complete because the demo works.

Completion means every item in `docs/10_DEFINITION_OF_DONE.md` is satisfied and the official/public evaluation kit passes as strongly as possible.

If an official evaluator/schema conflicts with these documents, adapt the implementation to the official evaluator and document the change in `docs/STATUS.md`.

Begin by reading the project documents.
