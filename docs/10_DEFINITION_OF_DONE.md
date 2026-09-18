# 10 — Definition of Done

The project is not done because the UI works.

It is done when the following are true.

## Official requirement coverage

- [ ] Two-queue/event-action evaluator interface is supported.
- [ ] Text chunks/end-of-turn handling works.
- [ ] WAV audio input works.
- [ ] PNG frame input works.
- [ ] Interruption signals work.
- [ ] Async tool results work.
- [ ] Dynamic tool manifests work.
- [ ] Spoken/fast-path actions work.
- [ ] Non-blocking tool calls contain explicit call IDs.
- [ ] Cancellation actions work.
- [ ] Clarification actions work.
- [ ] Final response carries required intent/slot snapshot.
- [ ] JSON protocol output is valid.

## Floor management

- [ ] First substantive response latency is measured.
- [ ] Fast path does not claim unverified completion.
- [ ] Filler is not spammed.
- [ ] Clarifications are specific.

## Interruption recovery

- [ ] Localized slot corrections preserve unrelated state.
- [ ] Intent switches invalidate old work.
- [ ] Superseded calls are canceled promptly.
- [ ] Late stale results are rejected.
- [ ] Stale retries do not reappear.
- [ ] Rapid multiple corrections converge on newest state.

## Tool correctness

- [ ] Tool manifests are parsed dynamically.
- [ ] Unseen tool test passes.
- [ ] Arguments are schema-validated.
- [ ] Read-only vs state-modifying behavior is respected.
- [ ] Chained calls work.
- [ ] Timeouts/failures do not deadlock.

## State-changing safety

- [ ] Logical operation keys exist.
- [ ] Duplicate state-changing dispatch count is zero in tests.
- [ ] No blind write retry.
- [ ] Cancellation-after-dispatch is handled explicitly.
- [ ] Uncertain side-effect outcome is not treated as safely repeatable.

## Multimodal

- [ ] Audio understanding is asynchronous.
- [ ] Vision understanding is asynchronous.
- [ ] Ambiguous audio/vision can trigger clarification.
- [ ] Multimodal results carry source provenance.
- [ ] Delayed multimodal results cannot overwrite newer state incorrectly.
- [ ] Combined multimodal interruption test passes.

## Concurrency

- [ ] No orphan async tasks.
- [ ] All spawned tasks have lifecycle ownership.
- [ ] Cancellation cleanup is tested.
- [ ] Cross-session isolation test passes.
- [ ] Virtual-clock deterministic tests pass.
- [ ] Same-timestamp ordering behavior is deterministic.

## Evaluation

- [ ] Unit suite passes.
- [ ] Scenario suite passes.
- [ ] Adversarial timing suite passes.
- [ ] Multimodal mocked suite passes.
- [ ] Protocol validation passes.
- [ ] Official 9-scenario public suite has been run once available.
- [ ] Every official-kit failure has a local regression test.

## Observability

- [ ] Every event/action is traceable by ID.
- [ ] State version transitions are logged.
- [ ] Call lifecycle is logged.
- [ ] Stale-result rejection is logged.
- [ ] Duplicate-blocking is logged.
- [ ] Latency can be computed from trace.

## Packaging

- [ ] Clean setup works on Python 3.10–3.12-compatible target chosen for project.
- [ ] README complete.
- [ ] Docker verified.
- [ ] No secrets in repo.
- [ ] Demo instructions complete.
- [ ] Architecture diagram included.
- [ ] Known limitations included.
- [ ] <=5 minute demo video ready.
- [ ] PPT/PDF ready.
- [ ] Final tag ready:
  `PRISM_GENAI_HACKATHON_Y2026`

Only mark a box complete when there is evidence.
