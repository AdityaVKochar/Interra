# 11 — Failure Modes and Review Checklist

Use this during code review and before submission.

## Race-condition failures

### Failure: stale result accepted

Symptom:
Old tool result changes final answer after user correction.

Fix direction:
- call lifecycle check,
- dependency compatibility,
- cancellation/invalidation marker.

### Failure: cancellation emitted but old callback still mutates state

Fix:
All tool-result paths must pass through one acceptance gate.

### Failure: newer correction overwritten by slow old model result

Fix:
Derived planner/multimodal results need source state/turn provenance and admissibility checks.

---

## Side-effect failures

### Failure: double booking / duplicate ticket

Cause:
Retry keyed only by `call_id`.

Fix:
Use logical `operation_key` + safety ledger.

### Failure: retry write after unknown outcome

Fix:
No blind retry. Reconcile/check/clarify.

---

## State failures

### Failure: every correction resets everything

Fix:
Use explicit state patches and changed keys.

### Failure: irrelevant old slots leak after true intent switch

Fix:
Define intent-switch transition that preserves only justified context.

---

## Tool failures

### Failure: hard-coded tool names

Fix:
Drive selection/validation from dynamic manifest.

### Failure: planner invents unknown tool

Fix:
Registry validation before dispatch.

### Failure: planner sends malformed args

Fix:
Schema validation before `TOOL_CALL`.

---

## Multimodal failures

### Failure: image model claims uncertain object as fact

Fix:
Structured observation with ambiguity; clarify.

### Failure: audio transcript arrives late and reverts state

Fix:
Source-event provenance and state compatibility.

### Failure: multimodal processing blocks input queue

Fix:
Run provider calls as managed async tasks.

---

## Fast-path failures

### Failure: “Done” before tool success

Fix:
Fast path can acknowledge intent/change, not completion.

### Failure: too many fillers

Fix:
At most one meaningful floor-management action per meaningful wait/update unless evaluator context justifies more.

---

## Protocol failures

### Failure: valid semantics but malformed JSON

Fix:
Typed serializer; schema tests.

### Failure: missing call IDs

Fix:
Allocate IDs before action emission.

### Failure: final snapshot stale

Fix:
Generate final snapshot directly from canonical state at final emission.

---

## Review questions

Before approving a change ask:

1. Can this code execute a side effect twice?
2. Can an old result enter the new plan?
3. Can a slow model response overwrite newer state?
4. Can this block the input loop?
5. Is the behavior generic to unseen tools?
6. Is there a deterministic regression test?
7. Does the trace explain what happened?
8. Is this solving the evaluator problem or only making the demo prettier?
