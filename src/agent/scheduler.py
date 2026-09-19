"""Call lifecycle and clock-driven deadlines; all mutations run in the coordinator."""
from dataclasses import dataclass
from .models import Call, CallStatus
from .coordinator import compatible


@dataclass
class Timer:
    call_id: str
    kind: str


class ToolScheduler:
    def __init__(self, runtime):
        self.runtime = runtime
        self.calls = {}
        self.timers = {}

    def arm(self, call_id, kind, delay):
        self.disarm(call_id)
        deadline = self.runtime.clock.now() + delay
        async def wait():
            remaining = deadline - self.runtime.clock.now()
            if remaining > 0:
                await self.runtime.clock.sleep(remaining)
            self.runtime.input.put_nowait(Timer(call_id, kind))
        self.timers[call_id] = self.runtime.spawn(wait())

    def disarm(self, call_id):
        task = self.timers.pop(call_id, None)
        if task is not None:
            task.cancel()

    def dispatch(self, request, spec, attempt=0):
        r = self.runtime
        call_id = r.ids.new("call")
        operation_key = None
        if spec.effect_type == "STATE_MODIFYING":
            if r.perception.unresolved or r.chunks:
                r.trace.record("WRITE_DEFERRED_PERCEPTION", tool_name=request.tool_name)
                return None
            if r.ledger.uncertain:
                r.trace.record("WRITE_BLOCKED_UNCERTAIN", tool_name=request.tool_name)
                r.emit("CLARIFY", question="A previous change has an unknown outcome. Please verify it before making another change.")
                return None
            operation = r.ledger.reserve(request, call_id)
            if operation is None:
                r.trace.record("DUPLICATE_WRITE_BLOCKED", tool_name=request.tool_name)
                return None
            operation_key = operation.key
        call = Call(call_id=call_id, request=request, spec=spec,
                    state=r.state.snapshot, created_at=r.clock.now(), status=CallStatus.DISPATCHED,
                    attempt=attempt, operation_key=operation_key)
        self.calls[call.call_id] = call
        r.trace.record("CALL_DISPATCHED", call=call.model_dump(mode="json"))
        payload = dict(call_id=call.call_id, tool_name=request.tool_name, arguments=request.arguments)
        if operation_key:
            payload["operation_key"] = operation_key
        r.emit("TOOL_CALL", **payload)
        self.arm(call.call_id, "timeout", spec.timeout)
        return call

    def failure(self, call, status, error):
        r = self.runtime
        self.disarm(call.call_id)
        self.calls[call.call_id] = call.model_copy(update={"status": status})
        r.trace.record(status.value, call_id=call.call_id, error=error)
        if call.operation_key:
            r.ledger.update(call.operation_key, "OUTCOME_UNKNOWN")
            r.trace.record("WRITE_OUTCOME_UNKNOWN", call_id=call.call_id, operation_key=call.operation_key)
            r.emit("CLARIFY", question="The change may have completed, but its outcome is unknown. Please verify it before retrying.")
            return
        if call.spec.effect_type == "READ_ONLY" and call.attempt < call.spec.max_retries:
            r.trace.record("RETRY_SCHEDULED", call_id=call.call_id)
            self.arm(call.call_id, "retry", call.spec.retry_delay)
        else:
            r.emit("CLARIFY", question="The tool did not complete successfully. Would you like to revise the request?")

    def timer(self, timer):
        call = self.calls.get(timer.call_id)
        if call is None:
            return
        if timer.kind == "timeout" and call.status == CallStatus.DISPATCHED:
            self.failure(call, CallStatus.TIMED_OUT, "deadline exceeded")
        elif timer.kind == "retry" and call.status in {CallStatus.FAILED, CallStatus.TIMED_OUT}:
            if not compatible(call, self.runtime.state.snapshot):
                self.invalidate(call, "dependencies changed")
                return
            if self.runtime.user_pending:
                self.runtime.trace.record("RETRY_DEFERRED", call_id=call.call_id)
                self.runtime.deferred_retries.add(call.call_id)
                return
            self.timers.pop(call.call_id, None)
            self.dispatch(call.request, call.spec, call.attempt + 1)

    def invalidate(self, call, reason):
        if call.status in {CallStatus.STALE, CallStatus.CANCEL_REQUESTED, CallStatus.CANCELLED}:
            return
        self.disarm(call.call_id)
        r = self.runtime
        r.deferred_retries.discard(call.call_id)
        status = CallStatus.CANCEL_REQUESTED if call.status == CallStatus.DISPATCHED else CallStatus.STALE
        self.calls[call.call_id] = call.model_copy(update={"status": status})
        if call.operation_key and call.status == CallStatus.DISPATCHED:
            r.ledger.update(call.operation_key, "OUTCOME_UNKNOWN")
            r.trace.record("WRITE_OUTCOME_UNKNOWN", call_id=call.call_id, operation_key=call.operation_key)
        r.results.pop(call.call_id, None)
        r.trace.record("CALL_INVALIDATED", call_id=call.call_id, reason=reason)
        if status == CallStatus.CANCEL_REQUESTED:
            r.emit("CANCEL_TOOL_CALL", call_id=call.call_id)
            r.trace.record("CANCEL_EMITTED", call_id=call.call_id)
            if r.latest_user_timestamp is not None:
                r.trace.record(
                    "CANCEL_EMISSION_LATENCY",
                    call_id=call.call_id,
                    source_timestamp=r.latest_user_timestamp,
                    latency=r.clock.now() - r.latest_user_timestamp,
                )

    def reconcile(self, state, all_calls=False):
        for call in list(self.calls.values()):
            if all_calls or not compatible(call, state):
                self.invalidate(call, "superseded" if all_calls else "dependencies changed")
