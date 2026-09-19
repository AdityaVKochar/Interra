# 10 — Definition of Done

The project is not done because the UI works.

It is done when the following are true.

## Official requirement coverage

- [ ] Two-queue/event-action evaluator interface is supported.
- [x] Text chunks/end-of-turn handling works.
- [x] WAV audio input works.
- [x] PNG frame input works.
- [x] Interruption signals work.
- [x] Async tool results work.
- [x] Dynamic tool manifests work.
- [x] Spoken/fast-path actions work.
- [x] Non-blocking tool calls contain explicit call IDs.
- [x] Cancellation actions work.
- [x] Clarification actions work.
- [x] Final response carries required intent/slot snapshot.
- [ ] JSON protocol output is valid.

## Floor management

- [x] First substantive response latency is measured.
- [x] Fast path does not claim unverified completion.
- [x] Filler is not spammed.
- [x] Clarifications are specific.

## Interruption recovery

- [x] Localized slot corrections preserve unrelated state.
- [x] Intent switches invalidate old work.
- [x] Superseded calls are canceled promptly.
- [x] Late stale results are rejected.
- [x] Stale retries do not reappear.
- [x] Rapid multiple corrections converge on newest state.

## Tool correctness

- [x] Tool manifests are parsed dynamically.
- [x] Unseen tool test passes.
- [x] Arguments are schema-validated.
- [x] Read-only vs state-modifying behavior is respected.
- [x] Chained calls work.
- [x] Timeouts/failures do not deadlock.

## State-changing safety

- [x] Logical operation keys exist.
- [x] Duplicate state-changing dispatch count is zero in tests.
- [x] No blind write retry.
- [x] Cancellation-after-dispatch is handled explicitly.
- [x] Uncertain side-effect outcome is not treated as safely repeatable.

## Multimodal

- [x] Audio understanding is asynchronous.
- [x] Vision understanding is asynchronous.
- [x] Ambiguous audio/vision can trigger clarification.
- [x] Multimodal results carry source provenance.
- [x] Delayed multimodal results cannot overwrite newer state incorrectly.
- [x] Combined multimodal interruption test passes.

## Concurrency

- [x] No orphan async tasks.
- [x] All spawned tasks have lifecycle ownership.
- [x] Cancellation cleanup is tested.
- [x] Cross-session isolation test passes.
- [x] Virtual-clock deterministic tests pass.
- [x] Same-timestamp ordering behavior is deterministic.

## Evaluation

- [x] Unit suite passes.
- [x] Scenario suite passes.
- [x] Adversarial timing suite passes.
- [x] Multimodal mocked suite passes.
- [x] Protocol validation passes.
- [ ] Official 9-scenario public suite has been run once available.
- [ ] Every official-kit failure has a local regression test.

## Observability

- [x] Every event/action is traceable by ID.
- [x] State version transitions are logged.
- [x] Call lifecycle is logged.
- [x] Stale-result rejection is logged.
- [x] Duplicate-blocking is logged.
- [x] Latency can be computed from trace.

## Packaging

- [x] Clean setup works on Python 3.10–3.12-compatible target chosen for project.
- [x] README complete.
- [x] Docker verified.
- [x] No secrets in repo.
- [x] Demo instructions complete.
- [x] Architecture diagram included.
- [x] Known limitations included.
- [ ] <=5 minute demo video ready.
- [ ] PPT/PDF ready.
- [ ] Final tag ready:
  `PRISM_GENAI_HACKATHON_Y2026`

Only mark a box complete when there is evidence.
