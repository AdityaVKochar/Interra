import asyncio
from agent.clock import VirtualClock
from agent.runtime import SessionRuntime


def spec(name="lookup", effect="READ_ONLY", **kwargs):
    return dict(name=name, description="Look up the requested value", effect_type=effect,
                argument_schema={"type": "object", "properties": {"value": {"type": "string"}},
                                 "required": ["value"], "additionalProperties": False}, **kwargs)


def plan(value="Delhi", name="lookup", **extra):
    return dict(state_patch={"intent": "lookup", "set_slots": {"destination": value, "origin": "Chennai"}},
                tool_requests=[dict(tool_name=name, arguments={"value": value}, bindings={"value": "destination"})], **extra)


class ScriptedPlanner:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.contexts = []

    async def plan(self, context):
        self.contexts.append(context)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, asyncio.Future):
            return await response
        return response


class Harness:
    def __init__(self, provider, session="s"):
        self.clock = VirtualClock()
        self.runtime = SessionRuntime(session, provider, self.clock)
        self.n = 0

    async def __aenter__(self):
        self.task = asyncio.create_task(self.runtime.run())
        return self

    async def __aexit__(self, *args):
        self.runtime.input.put_nowait(None)
        await self.task
        self.runtime.trace.save(f"artifacts/traces/{self.runtime.session_id}.jsonl")

    async def send(self, kind, **payload):
        self.n += 1
        await self.runtime.input.put(dict(event_id=f"e{self.n}", session_id=self.runtime.session_id,
                                         timestamp=self.clock.now(), type=kind, payload=payload))
        await self.runtime.input.join()

    async def action(self, kind):
        async with asyncio.timeout(3):
            while True:
                action = await self.runtime.output.get()
                if action.type == kind:
                    return action

    async def text(self, text):
        await self.send("TEXT_CHUNK", text=text, end_of_turn=True)

    def kinds(self):
        return [e.kind for e in self.runtime.trace.entries]
