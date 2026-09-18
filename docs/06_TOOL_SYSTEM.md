# 06 — Dynamic Tool System

The official challenge requires schema-driven tools supplied through manifests and includes unseen tools in evaluation.

Therefore the system must be **tool-generic**.

## Manifest normalization

Create an adapter that converts evaluator manifests into an internal `ToolSpec`.

Suggested fields:

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    argument_schema: Mapping[str, Any]
    effect_type: EffectType  # READ_ONLY / STATE_MODIFYING
    metadata: Mapping[str, Any]
```

If the official manifest expresses side-effect semantics differently, map them here.

Do not hard-code:

```python
if tool_name == "book_flight":
    ...
```

in orchestration code.

Scenario-specific adapters may exist only at the edge for local mocks.

---

## Tool selection

Planner receives the current normalized tool specs.

It proposes:

```json
{
  "tool_name": "...",
  "arguments": {...}
}
```

Before dispatch:

1. tool exists,
2. argument schema validates,
3. current state supports the request,
4. safety policy permits it,
5. duplicate ledger permits it.

---

## Read-only versus state-modifying

### Read-only examples conceptually

- search,
- lookup,
- fetch manual,
- check status.

### State-modifying examples conceptually

- book,
- create ticket,
- purchase,
- submit/change persistent external state.

Exact classification comes from the manifest/adapter, not the name.

---

## Tool call lifecycle

Suggested:

```text
proposal
  ↓
validate
  ↓
allocate call_id
  ↓
record call
  ↓
emit TOOL_CALL
  ↓
DISPATCHED
  ↓
wait asynchronously
  ├─ result
  ├─ failure
  ├─ timeout
  └─ cancellation/supersession
```

---

## Dependency tracking

For every call, record which session fields materially determined it.

Possible implementation:

- planner returns explicit `dependency_keys`, then runtime validates them; or
- runtime derives dependencies from tool arguments + state bindings.

Prefer explicit traceability.

Example:

```text
search_flights:
  args.destination ← state.slots.destination
  args.date        ← state.slots.date

dependency_keys = {"destination", "date"}
```

---

## Tool result acceptance

Acceptance gate:

```python
def can_accept_result(call, current_state) -> bool:
    return (
        call.status not in {CANCELLED, STALE}
        and call_is_dependency_compatible(call, current_state)
        and call_is_known(call)
    )
```

Do not literally copy this pseudocode without adapting to final domain types.

---

## Timeouts and faults

The official mock environment includes deterministic latency/fault injection.

Requirements:

- timeout must not block the session runtime;
- failure must be traced;
- failure response must remain truthful;
- read-only retry may be attempted only if useful and still current;
- state-changing retry requires explicit safe semantics.

---

## Chained calls

A scenario may require:

```text
search → choose result → book
```

Rules:

- later call depends on validated earlier result,
- interruption can invalidate the chain,
- if search becomes stale, downstream booking must not start,
- if booking already committed, a later correction must not silently double-book.

---

## Unseen tools

Hidden/public tests may introduce tools not used during development.

To handle unseen tools:

- use manifest descriptions,
- use argument schemas,
- use generic structured planning,
- do not enumerate a fixed action taxonomy unnecessarily.

Add tests with randomly named tools whose descriptions/schemas are sufficient to use them.

---

## Tool trace fields

Recommended trace record:

```json
{
  "call_id": "call_17",
  "tool_name": "search_flights",
  "effect_type": "READ_ONLY",
  "originating_state_version": 4,
  "dependency_keys": ["destination", "date"],
  "status": "DISPATCHED",
  "operation_key": null
}
```

For state-modifying tools, include the logical operation key.
