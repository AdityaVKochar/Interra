"""Call lifecycle and clock-driven deadlines; all mutations run in the coordinator."""
from dataclasses import dataclass
from .models import Call, CallStatus


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
        call = Call(call_id=r.ids.new("call"), request=request, spec=spec,
                    state=r.state.snapshot, created_at=r.clock.now(), status=CallStatus.DISPATCHED,
                    attempt=attempt)
        self.calls[call.call_id] = call
        r.trace.record("CALL_DISPATCHED", call=call.model_dump(mode="json"))
        r.emit("TOOL_CALL", call_id=call.call_id, tool_name=request.tool_name, arguments=request.arguments)
        self.arm(call.call_id, "timeout", spec.timeout)
        return call

    def failure(self, call, status, error):
        r = self.runtime
        self.disarm(call.call_id)
        self.calls[call.call_id] = call.model_copy(update={"status": status})
        r.trace.record(status.value, call_id=call.call_id, error=error)
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
            self.timers.pop(call.call_id, None)
            self.dispatch(call.request, call.spec, call.attempt + 1)
