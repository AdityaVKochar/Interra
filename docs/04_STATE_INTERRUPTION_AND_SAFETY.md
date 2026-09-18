# 04 — State, Interruption, Cancellation, and Safety

This is the most important engineering document in the repository.

## Core invariant

> Newer user intent/state wins, but only the parts that actually changed should invalidate prior work.

---

## State versioning

Maintain a monotonically increasing `state.version`.

Increment when a semantic state update occurs, such as:

- intent change,
- slot correction,
- slot removal,
- accepted multimodal fact that changes the plan.

Do not increment merely because:

- a tool result arrived,
- a filler was spoken,
- trace metadata changed.

A state version is not sufficient alone to decide staleness because some calls may remain valid after unrelated slot changes.

Therefore use:

- state version for audit,
- dependency compatibility for precision.

---

## Localized slot correction example

Current:

```json
{
  "intent": "search_flights",
  "slots": {
    "origin": "Chennai",
    "destination": "Delhi",
    "date": "tomorrow",
    "time": null
  }
}
```

User:

```text
Actually Mumbai, evening only.
```

New:

```json
{
  "intent": "search_flights",
  "slots": {
    "origin": "Chennai",
    "destination": "Mumbai",
    "date": "tomorrow",
    "time": "evening"
  }
}
```

Changed keys:

```text
destination
time
```

Preserved:

```text
origin
date
```

---

## Interruption workflow

When an interrupting semantic update arrives:

1. **Yield conversational floor** as required.
2. Parse/understand the new user input.
3. Compute a state patch.
4. Apply patch atomically.
5. Compute changed keys / intent change.
6. Inspect active calls.
7. Invalidate calls whose assumptions are no longer valid.
8. Emit cancellation action for invalidated in-flight calls.
9. Mark those calls so late results are rejected.
10. Re-plan using the new state.
11. Dispatch only the new valid calls.
12. Continue/finalize truthfully.

Do not wait for obsolete tool calls to finish before re-planning when the protocol allows cancellation.

---

## Call invalidation logic

A call becomes stale when any of the following is true:

- intent changed and the call belonged to the old intent;
- a dependency key changed;
- a newer plan explicitly superseded it;
- the call was canceled;
- the logical operation is no longer desired.

Example:

```text
call_17 = search_flights(destination=Delhi)
dependencies = {destination, date}

destination changes Delhi → Mumbai
=> call_17 invalid
```

---

## Late-result rule

When a `TOOL_RESULT(call_id)` arrives:

1. find the call record,
2. if unknown → trace protocol anomaly; do not apply,
3. if canceled/stale → record `STALE_RESULT_DISCARDED`; do not apply,
4. if result conflicts with current dependencies → mark stale; do not apply,
5. if valid → reconcile result,
6. update planner/state only through normal validated path.

**Never accept a result solely because it arrived successfully.**

---

## The critical race

This must be tested:

```text
T0    user asks for Delhi
T1    call_17 dispatched
T2    user says "Mumbai instead"
T3    call_17 cancellation emitted
T3+ε  result for call_17 arrives
```

Expected:

- result is traced,
- result is rejected as stale,
- state remains Mumbai,
- no final response is grounded in Delhi,
- no stale re-run occurs.

Also test the inverse ordering:

```text
result arrives just before interruption
```

Then the result may be valid at arrival time, but the subsequent interruption must still update state and new output must reflect the latest state.

---

## Intent switch

Example:

```text
search flight to Delhi
→ user: "Forget that, create a support ticket instead."
```

This is not a localized slot change.

Required:

- update intent,
- invalidate old intent-specific work,
- cancel relevant flight calls,
- preserve only context explicitly useful to the new intent,
- plan against available support-ticket tool schema.

---

## Floor management

Fast response should be semantically tied to what happened.

Good:

```text
"Sure — switching the destination to Mumbai."
```

Bad:

```text
"Done!"
```

before a new search has finished.

Bad:

```text
"One moment... one moment... one moment..."
```

Excessive filler harms quality.

---

## State-changing tool safety

### Distinguish call identity and logical operation identity

Example:

```text
call_id = transport/execution attempt
operation_key = logical booking action
```

If network retry creates a new `call_id`, it must still map to the same `operation_key`.

### Safety ledger

Before dispatching a state-changing tool:

1. derive/assign logical operation key,
2. check ledger,
3. if same operation is already:
   - pending,
   - committed,
   - uncertain-after-dispatch,
   then do not dispatch a duplicate,
4. record dispatch atomically.

### Recommended states

```text
NOT_STARTED
PENDING
COMMITTED
FAILED_SAFE_TO_RETRY
OUTCOME_UNKNOWN
CANCELLED_BEFORE_DISPATCH
```

If a modifying tool may have committed but the result was lost:

- do not blindly retry;
- use a read/check tool if available;
- otherwise clarify/report uncertainty according to evaluator capability.

---

## Cancellation of state-changing calls

Cancellation does not guarantee rollback.

Distinguish:

### Before dispatch

Safe to cancel locally.

### Dispatched but not committed

Request cancellation.

### May already have committed

Treat outcome carefully.

Do not issue a second modification merely because the first call became stale.

The evaluator's manifest/result semantics must guide reconciliation.

---

## Read-only retries

Controlled retries can be allowed for read-only tools when:

- tool failure/timeout policy permits,
- state dependencies are still valid,
- the retry remains useful.

Never let retry logic recreate a superseded call after the user changed the relevant state.

---

## Clarification policy

Clarify when:

- required slot is missing,
- user correction is ambiguous,
- multimodal observation is ambiguous,
- no safe tool choice can be made,
- tool outcome is uncertain and repeating may duplicate side effects.

Clarification should be specific.

Good:

```text
"Did you want Mumbai or Delhi as the destination?"
```

Bad:

```text
"Something went wrong. Please clarify."
```

---

## Safety invariants to encode as assertions/tests

1. No duplicate state-changing operation key is dispatched.
2. Canceled/stale results cannot trigger current-plan finalization.
3. Final snapshot reflects latest accepted user state.
4. Unknown tools are never executed.
5. Invalid arguments are never dispatched.
6. No completion claim without supporting result/state.
7. Every tool call has a unique `call_id`.
8. Every cancellation references a known active/superseded call.
9. A state update is atomic from the runtime's perspective.
10. No cross-session state leakage.
