# 07 — Testing and Evaluation

The official evaluation is trace-based and includes adversarial timing. Testing is therefore a first-class product feature.

## Testing pyramid

### Unit tests

Test pure logic:

- state patches,
- changed-key calculation,
- manifest normalization,
- argument validation,
- dependency compatibility,
- idempotency ledger,
- protocol serialization.

### Deterministic scenario tests

Use:

- virtual clock,
- mock planner,
- mock audio provider,
- mock vision provider,
- mock tool executor.

Assert full traces.

### Adversarial timing tests

Vary ordering around interruption/result boundaries.

### Official kit tests

Once released, integrate immediately and treat failures as highest priority.

---

## Required deterministic harness

Build a local harness that can schedule:

```text
at 0.000 → input event
at 0.250 → another input
at 0.400 → tool result
```

The harness must:

- replay events deterministically,
- simulate tool delays,
- inject failures,
- capture all output actions,
- capture state transitions,
- report latency metrics.

Never rely on real network timing for core tests.

---

## Minimum scenario suite

### S01 — Basic read-only success

User request → planner → tool call → result → final.

Assert:

- one call,
- correct arguments,
- final snapshot correct.

### S02 — Chained calls

Read-only lookup → dependent second call.

Assert proper ordering.

### S03 — Slot correction during read-only call

```text
Delhi search active
→ "Mumbai instead"
```

Assert:

- Delhi call canceled/invalidated,
- Mumbai state applied,
- new search dispatched,
- stale Delhi result ignored.

### S04 — Intent switch

Flight request → support-ticket request.

Assert old chain stops.

### S05 — Result just before interruption

Assert old result may be recorded, but newer user update becomes authoritative afterward.

### S06 — Result just after cancellation

Assert result discarded as stale.

### S07 — Two rapid corrections

```text
Delhi → Mumbai → Bengaluru
```

Assert only latest plan remains current.

### S08 — Duplicate tool result

Same `call_id` result arrives twice.

Assert second result has no side effect.

### S09 — Duplicate write proposal

Planner proposes same state-changing logical operation twice.

Assert only one dispatch.

### S10 — Write timeout/outcome uncertain

Assert no blind duplicate retry.

### S11 — Read-only retry

Inject transient failure, state unchanged.

Assert bounded retry may succeed.

### S12 — Retry becomes stale

Failure occurs, but user changes relevant slot before retry.

Assert old retry does not dispatch.

### S13 — Clarification

Missing/ambiguous required value.

Assert specific clarification and no unsafe call.

### S14 — Unknown intent/tool mismatch

No appropriate tool.

Assert no invented tool name.

### S15 — Unseen tool

Provide novel manifest.

Assert planner can select it from description/schema.

### S16 — Malformed planner output

Assert schema rejection and safe recovery.

### S17 — Audio normal

WAV → semantic request → valid execution.

### S18 — Audio correction during tool call

Assert normal cancellation/state behavior.

### S19 — Delayed audio interpretation

A newer text correction arrives first.

Assert delayed old audio interpretation cannot revert current state incorrectly.

### S20 — Visual grounding

PNG produces relevant observation used in answer/tool call.

### S21 — Ambiguous visual

Assert clarification rather than confident destructive action.

### S22 — Delayed visual result

Newer user input makes old visual analysis irrelevant.

Assert no stale override.

### S23 — Audio + visual + interruption

Interleaved modalities.

Assert latest coherent state wins.

### S24 — Out-of-order tool results

Two concurrent read calls complete reverse order.

Assert each result is matched by `call_id`.

### S25 — Cross-session isolation

Two sessions in parallel.

Assert zero shared state leakage.

---

## Boundary timing matrix

For every important cancellation scenario, test result arrival:

```text
-50 ms before interruption
-10 ms
-1 ms
same virtual timestamp
+1 ms
+10 ms
+50 ms after
```

Use deterministic sequence numbers to resolve same-timestamp ordering according to harness rules.

---

## Property/invariant tests

Encode invariants:

```text
duplicate_write_dispatch_count == 0
unknown_tool_dispatch_count == 0
accepted_stale_result_count == 0
invalid_final_snapshot_count == 0
cross_session_leak_count == 0
```

Consider property-based generation for event orderings if dependency budget permits.

---

## Trace assertions

Do not test only final text.

For interruption scenario, assert trace contains:

```text
CALL_DISPATCHED old
STATE_UPDATED
CALL_INVALIDATED old
CANCEL_EMITTED old
CALL_DISPATCHED new
STALE_RESULT_DISCARDED old
FINAL new
```

Order may vary slightly based on official protocol, but semantic invariants must hold.

---

## Local metrics

Track at least:

- task success rate,
- first substantive action latency,
- cancellation emission latency,
- stale-result acceptance count,
- duplicate modifying-call count,
- invalid JSON/action count,
- clarification correctness count,
- provider failure count.

Do not invent a single “Samsung score” unless the official kit computes it.

---

## Official scoring awareness

Optimize in this order because official weights are:

1. Task completion — 40%
2. Interruption recovery — 35%
3. Response latency — 15%
4. Safety/protocol — 10%

Quality multiplier also rewards natural, truthful, relevant transcripts.

Hidden multimodal scenarios receive additional weighting, so multimodal tests must be part of the final hardening phase.

---

## CI gate

Before merging/finalizing:

```text
unit tests                 PASS
deterministic scenarios    PASS
adversarial timing         PASS
multimodal mocked tests    PASS
protocol validation        PASS
official public kit        PASS/record score
```

A flashy demo is not a substitute for this gate.
