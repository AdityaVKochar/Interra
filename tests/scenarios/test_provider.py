import asyncio
import json
import unittest
import httpx
from agent.providers.ollama import OllamaProvider
from tests.helpers import Harness, ScriptedPlanner, spec, plan


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_exception_with_empty_message_is_failure(self):
        async with Harness(ScriptedPlanner(EOFError()), self.id()) as h:
            await h.text("item")
            await h.action("CLARIFY")
            self.assertIn("PLANNER_FAILED", h.kinds())

    async def test_real_adapter_swaps_without_runtime_changes(self):
        requests = []
        def transport(request):
            body = json.loads(request.content)
            requests.append(body)
            proposal = plan(name="opaque_live") if len(requests) == 1 else {"final_response": "Found"}
            return httpx.Response(200, json={"message": {"content": json.dumps(proposal)}})
        async with httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(transport)) as client:
            async with Harness(OllamaProvider("configured-model", client=client), self.id()) as h:
                await h.send("TOOL_MANIFEST", tools=[spec("opaque_live")])
                await h.text("find")
                call = await h.action("TOOL_CALL")
                await h.send("TOOL_RESULT", call_id=call.payload["call_id"], ok=True, result={"found": True})
                await h.action("FINAL")
                self.assertIn("RESULT_ACCEPTED", h.kinds())
        self.assertFalse(requests[0]["stream"])
        self.assertIn("properties", requests[0]["format"])
        self.assertIn("opaque_live", requests[0]["messages"][1]["content"])

    async def test_bounded_schema_repair(self):
        provider = ScriptedPlanner({"bad": 1}, {"clarification": "Which item?"})
        async with Harness(provider, self.id()) as h:
            h.runtime.planner_repairs = 1
            await h.text("item")
            await h.action("CLARIFY")
            self.assertEqual(len(provider.contexts), 2)
            self.assertIn("schema_error", provider.contexts[1].input)
            self.assertEqual(h.kinds().count("MODEL_SCHEMA_REJECTED"), 1)

    async def test_repair_exhaustion_is_safe(self):
        provider = ScriptedPlanner({"bad": 1}, {"bad": 2})
        async with Harness(provider, self.id()) as h:
            h.runtime.planner_repairs = 1
            await h.text("item")
            await h.action("CLARIFY")
            self.assertEqual(h.kinds().count("MODEL_SCHEMA_REJECTED"), 2)
            self.assertIn("PLANNER_FAILED", h.kinds())
            self.assertFalse(h.runtime.calls)

    async def test_provider_deadline_and_interrupt_cleanup(self):
        pending = asyncio.get_running_loop().create_future()
        async with Harness(ScriptedPlanner(pending), self.id()) as h:
            h.runtime.planner_timeout = 1.
            await h.text("item")
            await h.action("SPEAK")
            await h.advance(1.)
            await h.action("CLARIFY")
            self.assertIn("PLANNER_TIMED_OUT", h.kinds())
        self.assertTrue(pending.cancelled())
        self.assertEqual(h.clock.pending, 0)
