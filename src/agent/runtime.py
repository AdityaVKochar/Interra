"""Single owner of session mutations; slow work returns through the input mailbox."""
import asyncio
from dataclasses import dataclass

from .models import Action, Call, CallStatus, Event
from .planner import propose
from .protocol import LocalProtocol
from .providers.base import PlanningContext
from .state import StateManager
from .tools.registry import ToolRegistry
from .trace import IDs, TraceRecorder
from .scheduler import ToolScheduler, Timer
from jsonschema.exceptions import ValidationError as SchemaError
from .coordinator import compatible


@dataclass
class Completion:
    token: int
    value: object = None
    error: str | None = None


class SessionRuntime:
    def __init__(self, session_id, provider, clock, input_queue=None, output_queue=None):
        self.session_id, self.provider, self.clock = session_id, provider, clock
        self.input = input_queue if input_queue is not None else asyncio.Queue()
        self.output = output_queue if output_queue is not None else asyncio.Queue()
        self.ids = IDs(session_id)
        self.trace = TraceRecorder(session_id, clock, self.ids)
        self.protocol = LocalProtocol()
        self.state = StateManager(session_id)
        self.registry = ToolRegistry()
        self.scheduler = ToolScheduler(self)
        self.calls = self.scheduler.calls
        self.results = {}
        self.tasks = set()
        self.planner_task = None
        self.token = 0
        self.chunks = []
        self.seen = set()
        self.last_input = {}
        self.user_pending = False
        self.deferred_retries = set()

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def emit(self, kind, **payload):
        action = Action(action_id=self.ids.new("action"), session_id=self.session_id,
                        timestamp=self.clock.now(), type=kind, payload=payload)
        self.protocol.encode(action)
        self.trace.record("ACTION_EMITTED", action=action.model_dump(mode="json"))
        self.output.put_nowait(action)

    async def run(self):
        try:
            while True:
                item = await self.input.get()
                try:
                    if item is None:
                        break
                    if isinstance(item, Completion):
                        self.complete(item)
                    elif isinstance(item, Timer):
                        self.scheduler.timer(item)
                    else:
                        try:
                            event = self.protocol.decode(item.model_dump() if isinstance(item, Event) else item)
                            self.handle(event)
                        except (ValueError, TypeError, KeyError, SchemaError) as exc:
                            self.trace.record("INPUT_REJECTED", error=str(exc))
                finally:
                    self.input.task_done()
        finally:
            tasks = list(self.tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.trace.record("SESSION_CLOSED", state=self.state.snapshot.model_dump())

    def handle(self, event):
        if event.session_id != self.session_id:
            self.trace.record("INPUT_REJECTED", event_id=event.event_id, error="wrong session")
            return
        if event.event_id in self.seen:
            self.trace.record("DUPLICATE_EVENT", event_id=event.event_id)
            return
        self.seen.add(event.event_id)
        self.trace.record("INPUT_RECEIVED", event=event.model_dump())
        if event.type == "TOOL_MANIFEST":
            self.registry.replace(event.payload["tools"])
            self.trace.record("MANIFEST_UPDATED")
        elif event.type == "TEXT_CHUNK":
            if not self.chunks:
                self.user_pending = True
                self.token += 1
                if self.planner_task and not self.planner_task.done():
                    self.planner_task.cancel()
            self.chunks.append(event.payload["text"])
            if event.payload["end_of_turn"]:
                self.last_input = {"text": "".join(self.chunks), "event_id": event.event_id}
                self.chunks.clear()
                self.start_plan()
        elif event.type == "TOOL_RESULT":
            self.result(event.payload)
        elif event.type == "INTERRUPTION":
            self.token += 1
            self.user_pending = True
            self.chunks.clear()
            if self.planner_task and not self.planner_task.done():
                self.planner_task.cancel()
            self.scheduler.reconcile(self.state.snapshot, all_calls=True)
            self.trace.record("INTERRUPTED", event_id=event.event_id)
        elif event.type == "CANCEL_ACK":
            call = self.calls.get(event.payload["call_id"])
            if call and call.status == CallStatus.CANCEL_REQUESTED:
                self.calls[call.call_id] = call.model_copy(update={"status": CallStatus.CANCELLED})
                self.trace.record("CANCEL_ACKNOWLEDGED", call_id=call.call_id)
            else:
                self.trace.record("CANCEL_ACK_IGNORED", call_id=event.payload["call_id"])
        else:
            self.trace.record("UNSUPPORTED_INPUT", event_id=event.event_id)

    def start_plan(self):
        self.token += 1
        token = self.token
        if self.planner_task and not self.planner_task.done():
            self.planner_task.cancel()
        context = PlanningContext(state=self.state.snapshot, input=self.last_input,
                                  tools=self.registry.specs, results=self.results)
        self.trace.record("PLANNER_STARTED", token=token, version=context.state.version)
        async def work():
            try:
                value = await propose(self.provider, context)
                self.input.put_nowait(Completion(token, value))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.input.put_nowait(Completion(token, error=str(exc)))
        self.planner_task = self.spawn(work())

    def complete(self, completion):
        if completion.token != self.token:
            self.trace.record("STALE_PLAN_DISCARDED", token=completion.token)
            return
        if completion.error:
            self.trace.record("PLANNER_FAILED", error=completion.error)
            self.emit("CLARIFY", question="I could not interpret that request safely. What should I do next?")
            return
        proposal = completion.value
        try:
            candidate, _, _ = self.state.preview(proposal.state_patch)
            specs = [self.registry.validate(req, candidate) for req in proposal.tool_requests]
            if any(s.effect_type != "READ_ONLY" for s in specs):
                raise ValueError("state-changing tools not enabled yet")
        except Exception as exc:
            self.trace.record("PROPOSAL_REJECTED", error=str(exc))
            self.emit("CLARIFY", question="The proposed tool arguments were invalid. Please clarify the request.")
            return
        self.trace.record("PROPOSAL_ACCEPTED", proposal=proposal.model_dump())
        old = self.state.snapshot
        state, changed, switched = self.state.apply(proposal.state_patch)
        if state.version != old.version:
            self.trace.record("STATE_UPDATED", before=old.model_dump(), after=state.model_dump(),
                              changed=sorted(changed), intent_changed=switched)
        self.scheduler.reconcile(state)
        self.user_pending = False
        for call_id in list(self.deferred_retries):
            self.deferred_retries.discard(call_id)
            self.scheduler.timer(Timer(call_id, "retry"))
        for request, spec in zip(proposal.tool_requests, specs):
            self.dispatch(request, spec)
        if proposal.clarification:
            self.emit("CLARIFY", question=proposal.clarification)
        if proposal.final_response:
            if any(c.status == CallStatus.DISPATCHED for c in self.calls.values()):
                self.trace.record("FINAL_DEFERRED")
            else:
                self.emit("FINAL", text=proposal.final_response,
                          state_snapshot={"intent": state.intent, "slots": state.slots})

    def dispatch(self, request, spec):
        return self.scheduler.dispatch(request, spec)

    def result(self, payload):
        call = self.calls.get(payload["call_id"])
        if call is None:
            self.trace.record("UNKNOWN_RESULT", call_id=payload["call_id"])
            return
        if call.status in {CallStatus.STALE, CallStatus.CANCEL_REQUESTED, CallStatus.CANCELLED} or not compatible(call, self.state.snapshot):
            self.trace.record("STALE_RESULT_DISCARDED", call_id=call.call_id)
            return
        if call.status != CallStatus.DISPATCHED:
            self.trace.record("DUPLICATE_RESULT_DISCARDED", call_id=call.call_id)
            return
        self.scheduler.disarm(call.call_id)
        if not payload["ok"]:
            self.scheduler.failure(call, CallStatus.FAILED, payload.get("error"))
            return
        self.calls[call.call_id] = call.model_copy(update={"status": CallStatus.COMPLETED})
        self.results[call.call_id] = payload
        self.trace.record("RESULT_ACCEPTED", call_id=call.call_id, result=payload)
        if not self.user_pending:
            self.start_plan()
        else:
            self.trace.record("RESULT_PLANNING_DEFERRED", call_id=call.call_id)
