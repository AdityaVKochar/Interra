import asyncio
import unittest
from agent.runtime import PlannerDeadline
from tests.helpers import Harness, ScriptedPlanner, plan, spec
from tests.scenarios.test_multimodal import settle
from tests.scenarios.test_audio import AudioMock, wav_ref
from tests.scenarios.test_vision import VisionMock, png_ref


class LifecycleAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_perception_deadline_is_virtual_and_cleans_up(self):
        pending = asyncio.get_running_loop().create_future()
        async with Harness(ScriptedPlanner(), self.id()) as h:
            h.runtime.perception_timeout = 1.
            h.runtime.perception.audio_provider = AudioMock(pending)
            await h.send("AUDIO_CLIP", mime_type="audio/wav", data_ref=wav_ref())
            await h.advance(1.)
            self.assertIn("PERCEPTION_TIMED_OUT", h.kinds())
            await h.action("CLARIFY")
            self.assertTrue(pending.cancelled())
        self.assertEqual(h.clock.pending, 0)

    async def test_frame_during_partial_text_waits_for_end_of_turn(self):
        provider = ScriptedPlanner({"clarification": "Which warning?"})
        async with Harness(provider, self.id()) as h:
            h.runtime.perception.vision_provider = VisionMock({"summary": "warning", "facts": {"code": 4}})
            await h.send("TEXT_CHUNK", text="explain ", end_of_turn=False)
            await h.send("VIDEO_FRAME", mime_type="image/png", data_ref=png_ref(), frame_id="f")
            await settle(h.runtime)
            self.assertFalse(provider.contexts)
            await h.text("this warning")
            await h.action("CLARIFY")
            self.assertIn("explain this warning", provider.contexts[0].input["text"])
            self.assertIn("vision", provider.contexts[0].input["observations"])

    async def test_final_cannot_use_result_invalidated_by_its_own_patch(self):
        bad_final = {"state_patch": {"set_slots": {"destination": "Mumbai"}}, "final_response": "Found Mumbai"}
        async with Harness(ScriptedPlanner(plan(), bad_final), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("Delhi")
            old = (await h.action("TOOL_CALL")).payload["call_id"]
            await h.send("TOOL_RESULT", call_id=old, ok=True, result={"city": "Delhi"})
            await settle(h.runtime)
            self.assertIn("FINAL_BLOCKED_NO_EVIDENCE", h.kinds())
            finals = [e for e in h.runtime.trace.entries if e.kind == "ACTION_EMITTED" and e.data["action"]["type"] == "FINAL"]
            self.assertFalse(finals)

    async def test_invalid_manifest_schema_does_not_terminate_session(self):
        async with Harness(ScriptedPlanner({"clarification": "Which item?"}), self.id()) as h:
            invalid = spec()
            invalid["argument_schema"]["required"] = "not-an-array"
            # Direct mailbox insertion allows checking consumer health before joining again.
            await h.runtime.input.put(dict(session_id=h.runtime.session_id, event_id="bad", timestamp=0.,
                type="TOOL_MANIFEST", payload={"tools": [invalid]}))
            await settle(h.runtime)
            self.assertFalse(h.task.done())
            self.assertIn("INPUT_REJECTED", h.kinds())
            await h.text("item")
            await h.action("CLARIFY")

    async def test_late_write_success_after_timeout_reconciles_ledger_only(self):
        async with Harness(ScriptedPlanner(plan()), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec(effect="STATE_MODIFYING", timeout=1.)])
            await h.text("change")
            call = (await h.action("TOOL_CALL")).payload["call_id"]
            await h.advance(1.)
            await h.action("CLARIFY")
            await h.send("TOOL_RESULT", call_id=call, ok=True, result={"committed": True})
            self.assertFalse(h.runtime.ledger.uncertain)
            self.assertFalse(h.runtime.results)
            self.assertIn("LATE_WRITE_RECONCILED", h.kinds())

    async def test_completed_plan_ignores_already_queued_deadline(self):
        async with Harness(ScriptedPlanner({"final_response": "Hello"}), self.id()) as h:
            await h.text("hello")
            await h.action("FINAL")
            await h.runtime.input.put(PlannerDeadline(h.runtime.token))
            await h.runtime.input.join()
            self.assertNotIn("PLANNER_TIMED_OUT", h.kinds())

    async def test_partial_perception_cannot_dispatch_write(self):
        pending = asyncio.get_running_loop().create_future()
        async with Harness(ScriptedPlanner(plan()), self.id()) as h:
            h.runtime.perception.audio_provider = AudioMock({"transcript": "change"})
            h.runtime.perception.vision_provider = VisionMock(pending)
            await h.send("TOOL_MANIFEST", tools=[spec(effect="STATE_MODIFYING")])
            await h.send("VIDEO_FRAME", mime_type="image/png", data_ref=png_ref(), frame_id="f")
            await h.send("AUDIO_CLIP", mime_type="audio/wav", data_ref=wav_ref())
            await settle(h.runtime)
            self.assertFalse(h.runtime.calls)
            self.assertIn("WRITE_DEFERRED_PERCEPTION", h.kinds())

    async def test_ambiguous_companion_blocks_write(self):
        pending = asyncio.get_running_loop().create_future()
        async with Harness(ScriptedPlanner(plan()), self.id()) as h:
            h.runtime.perception.audio_provider = AudioMock(pending)
            h.runtime.perception.vision_provider = VisionMock({"summary": "unclear", "ambiguous": True})
            await h.send("TOOL_MANIFEST", tools=[spec(effect="STATE_MODIFYING")])
            await h.send("AUDIO_CLIP", mime_type="audio/wav", data_ref=wav_ref())
            await h.send("VIDEO_FRAME", mime_type="image/png", data_ref=png_ref(), frame_id="f")
            await h.action("CLARIFY")
            pending.set_result({"transcript": "change"})
            await settle(h.runtime)
            self.assertFalse(h.runtime.calls)
            self.assertIn("WRITE_DEFERRED_PERCEPTION", h.kinds())

    async def test_older_timestamp_user_input_does_not_override_newer(self):
        async with Harness(ScriptedPlanner(plan("Mumbai"), plan("Delhi")), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.advance(2.)
            await h.text("Mumbai")
            await h.action("TOOL_CALL")
            await h.runtime.input.put(dict(session_id=h.runtime.session_id, event_id="late", timestamp=1.,
                                          type="TEXT_CHUNK", payload={"text": "Delhi", "end_of_turn": True}))
            await settle(h.runtime)
            self.assertEqual(h.runtime.state.snapshot.slots["destination"], "Mumbai")
            self.assertIn("STALE_INPUT_DISCARDED", h.kinds())

    async def test_manifest_removal_prevents_old_retry(self):
        async with Harness(ScriptedPlanner(plan()), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec(max_retries=1, retry_delay=1.)])
            await h.text("lookup")
            old = (await h.action("TOOL_CALL")).payload["call_id"]
            await h.send("TOOL_RESULT", call_id=old, ok=False, result=None)
            await h.send("TOOL_MANIFEST", tools=[])
            await h.advance(1.)
            self.assertEqual(h.kinds().count("CALL_DISPATCHED"), 1)
            self.assertIn("CALL_INVALIDATED", h.kinds())

    async def test_outgoing_payload_cannot_mutate_call(self):
        async with Harness(ScriptedPlanner(plan()), self.id()) as h:
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("lookup")
            action = await h.action("TOOL_CALL")
            action.payload["arguments"]["value"] = "tampered"
            record = h.runtime.calls[action.payload["call_id"]]
            self.assertEqual(record.request.arguments["value"], "Delhi")
