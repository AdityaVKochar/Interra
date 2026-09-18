import asyncio
import unittest

from tests.helpers import Harness, ScriptedPlanner, plan, spec
from tests.scenarios.test_audio import AudioMock, wav_ref
from tests.scenarios.test_vision import VisionMock, png_ref


async def settle(runtime):
    for _ in range(4):
        await asyncio.sleep(0)
    await runtime.input.join()


class MultimodalFusionTests(unittest.IsolatedAsyncioTestCase):
    async def test_audio_visual_tool_result_and_interruption_converge(self):
        loop = asyncio.get_running_loop()
        audio_result = loop.create_future()
        vision_result = loop.create_future()
        audio_only_plan = loop.create_future()
        fused_plan = {
            "state_patch": {
                "intent": "lookup",
                "set_slots": {
                    "origin": "Chennai",
                    "destination": "Mumbai",
                    "time_of_day": "evening",
                },
            },
            "tool_requests": [{
                "tool_name": "lookup",
                "arguments": {"value": "Mumbai"},
                "bindings": {"value": "destination"},
            }],
        }
        planner = ScriptedPlanner(
            plan("Delhi"),
            audio_only_plan,
            fused_plan,
            {"final_response": "Found the evening Mumbai options."},
        )

        async with Harness(planner, self.id()) as h:
            h.runtime.perception.audio_provider = AudioMock(audio_result)
            h.runtime.perception.vision_provider = VisionMock(vision_result)
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("Find Delhi options")
            old_call = (await h.action("TOOL_CALL")).payload["call_id"]

            await h.send("INTERRUPTION", reason="user_barge_in")
            self.assertEqual(
                (await h.action("CANCEL_TOOL_CALL")).payload["call_id"],
                old_call,
            )
            await h.send("AUDIO_CLIP", mime_type="audio/wav", data_ref=wav_ref())
            await h.send(
                "VIDEO_FRAME",
                mime_type="image/png",
                data_ref=png_ref(),
                frame_id="evening-board",
            )
            await h.send(
                "TOOL_RESULT",
                call_id=old_call,
                ok=True,
                result={"destination": "Delhi"},
            )

            self.assertFalse(audio_result.cancelled())
            audio_result.set_result({
                "transcript": "Mumbai instead",
                "evidence": "spoken correction",
            })
            await settle(h.runtime)
            self.assertEqual(len(planner.contexts), 2)

            vision_result.set_result({
                "summary": "The board shows evening departures.",
                "facts": {"time_of_day": "evening"},
                "evidence": "departure board",
            })
            new_call = await h.action("TOOL_CALL")
            fused_input = planner.contexts[-1].input
            self.assertEqual(set(fused_input["observations"]), {"audio", "vision"})
            self.assertTrue(audio_only_plan.cancelled())

            await h.send(
                "TOOL_RESULT",
                call_id=new_call.payload["call_id"],
                ok=True,
                result={"destination": "Mumbai", "time_of_day": "evening"},
            )
            final = await h.action("FINAL")

            self.assertEqual(
                final.payload["state_snapshot"]["slots"]["destination"],
                "Mumbai",
            )
            self.assertEqual(
                final.payload["state_snapshot"]["slots"]["time_of_day"],
                "evening",
            )
            self.assertIn("STALE_RESULT_DISCARDED", h.kinds())
            self.assertIn("FUSION_CONTEXT_UPDATED", h.kinds())
