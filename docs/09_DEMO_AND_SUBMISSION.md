# 09 — Demo and Submission Plan

## What the demo must prove

The demo should make the technical contribution visible:

1. Agent remains responsive.
2. Tool work is non-blocking.
3. User interrupts.
4. Old work is canceled/invalidated.
5. Late stale result is rejected.
6. Relevant state is preserved.
7. New plan completes correctly.
8. State-changing calls are protected.
9. Multimodal input works through the same runtime.

Do not make the main demo simply “talk to an assistant.”

---

## Recommended 5-minute video structure

### 0:00–0:25 — Problem

Show the failure mode:

```text
Most assistants assume listen → think → speak.
Real users interrupt and change their mind while work is running.
```

### 0:25–0:50 — Architecture

Show:

```text
Fast Path
Slow Path
Coordination Layer
```

Emphasize:

- state snapshots,
- cancellation,
- idempotency,
- dynamic tools.

### 0:50–2:20 — Hero interruption demo

Scenario:

1. User requests a task.
2. Tool call begins.
3. User changes a key slot.
4. State updates.
5. Old call cancellation appears.
6. Old result arrives late.
7. Runtime visibly labels it stale/rejected.
8. New result is accepted.
9. Final response/snapshot is correct.

The stale-result arrival is important because it proves the system is not only cosmetically interruptible.

### 2:20–3:15 — Safety demo

Show a state-changing operation.

Attempt a duplicate/retry.

Show the safety ledger blocks the duplicate.

### 3:15–4:05 — Multimodal demo

Use either:

- WAV correction during active work,
- PNG frame grounding,
- combined audio + visual.

Show that multimodal processing does not bypass state/cancellation logic.

### 4:05–4:35 — Evaluation evidence

Show:

- scenario test count,
- adversarial timing matrix,
- public evaluator results when available,
- first-action latency,
- zero duplicate modifying calls,
- zero accepted stale results in local suite.

Do not fabricate scores.

### 4:35–5:00 — Limitations + future

Be precise and honest.

Examples:

- provider latency variability,
- ambiguity may require clarification,
- external side effects cannot always be rolled back after commit,
- official evaluator constraints define final supported protocol.

---

## Demo UI guidance

UI is out of scope for scoring emphasis, so keep it minimal.

A useful developer-style panel:

```text
EVENT TIMELINE        STATE              ACTIVE CALLS
──────────────        ─────              ────────────
0.00 user ...        intent: search     call_17 STALE
0.12 speak ...       dest: Mumbai       call_18 ACTIVE
0.20 call_17 ...
0.70 interrupt ...
0.74 cancel_17 ...
1.10 result_17 [REJECTED]
1.40 result_18 [ACCEPTED]
```

This communicates the engineering immediately.

---

## PPT content

The overall Samsung guide asks for:

- Theme ID,
- project title,
- team details,
- problem statement in your words,
- solution and architecture diagram,
- tools and tech stack,
- innovation highlights,
- results,
- limitations.

Recommended slide order:

1. Title / Theme 05
2. Why half-duplex agents fail
3. Requirements / evaluation insight
4. Architecture
5. State + interruption lifecycle
6. Tool safety/idempotency
7. Multimodal integration
8. Adversarial testing/evaluation
9. Live/demo results
10. Limitations + worklet/future direction

---

## Submission checklist

Before 25 Sep 2026 11:59 PM:

- [ ] Working repository is public/shared as required.
- [ ] README setup is reproducible from clean environment.
- [x] Docker build/run verified.
- [ ] Demo video <=5 min.
- [ ] PPT/PDF present.
- [ ] Referenced docs/assets are in repo.
- [ ] Known limitations documented.
- [ ] Tests runnable with one documented command.
- [ ] Environment variables documented without secrets.
- [ ] No API keys committed.
- [ ] Final commit reviewed.
- [ ] Release/tag created exactly:
  `PRISM_GENAI_HACKATHON_Y2026`
- [ ] Submission links point to the tagged/final material.

---

## Final live round preparation

If shortlisted, expect questions on:

- why fast/slow paths are separate,
- how cancellation races are handled,
- what happens if a write already committed,
- why a stale result cannot corrupt the latest state,
- how unseen tools are supported,
- how audio/vision remain non-blocking,
- why the system does not double-execute side effects,
- how latency was measured,
- what trade-offs were made.

Every answer should point to an actual implementation decision and trace/test.
