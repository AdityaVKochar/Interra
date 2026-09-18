import asyncio
import base64
import struct
import zlib
import unittest
from agent.multimodal.fusion import PerceptionResult
from agent.multimodal.vision import VisualObservation, validate_png
from tests.helpers import Harness, ScriptedPlanner, spec, plan


def png_ref():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b"")
    return "base64:" + base64.b64encode(data).decode()


class VisionMock:
    def __init__(self, value):
        self.value = value
        self.data = None

    async def understand_png(self, data):
        self.data = data
        return await self.value if isinstance(self.value, asyncio.Future) else self.value


class VisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_frame_grounded_tool(self):
        provider = ScriptedPlanner(plan("warning", name="manual"), {"final_response": "Found manual"})
        mock = VisionMock({"summary": "A warning", "facts": {"visible_warning": "charging"}, "evidence": "screen"})
        async with Harness(provider, self.id()) as h:
            h.runtime.perception.vision_provider = mock
            await h.send("TOOL_MANIFEST", tools=[spec("manual")])
            await h.send("VIDEO_FRAME", mime_type="image/png", data_ref=png_ref(), frame_id="frame1")
            call = await h.action("TOOL_CALL")
            self.assertEqual(provider.contexts[0].input["observation"]["facts"], {"visible_warning": "charging"})
            await h.send("TOOL_RESULT", call_id=call.payload["call_id"], ok=True, result={"manual": "read"})
            await h.action("FINAL")
            self.assertIn("OBSERVATION_ACCEPTED", h.kinds())
            validate_png(mock.data)

    async def test_ambiguous_frame_no_write(self):
        async with Harness(ScriptedPlanner(), self.id()) as h:
            h.runtime.perception.vision_provider = VisionMock({"summary": "unclear", "ambiguous": True, "question": "Which warning is visible?"})
            await h.send("VIDEO_FRAME", mime_type="image/png", data_ref=png_ref(), frame_id="frame1")
            action = await h.action("CLARIFY")
            self.assertEqual(action.payload["question"], "Which warning is visible?")
            self.assertFalse(h.runtime.calls)
            self.assertIn("OBSERVATION_ACCEPTED", h.kinds())

    async def test_stale_frame_after_new_text(self):
        pending = asyncio.get_running_loop().create_future()
        async with Harness(ScriptedPlanner({"clarification": "What changed?"}), self.id()) as h:
            h.runtime.perception.vision_provider = VisionMock(pending)
            await h.send("VIDEO_FRAME", mime_type="image/png", data_ref=png_ref(), frame_id="old")
            epoch = h.runtime.epoch
            await h.text("different device")
            await h.action("CLARIFY")
            await h.runtime.input.put(PerceptionResult("e1", 0., epoch, "vision", VisualObservation(summary="old")))
            await h.runtime.input.join()
            self.assertIn("STALE_PERCEPTION_DISCARDED", h.kinds())
            self.assertTrue(pending.cancelled())

    async def test_corrupt_png(self):
        data = bytearray(base64.b64decode(png_ref()[7:]))
        data[30] ^= 1
        with self.assertRaises(ValueError):
            validate_png(bytes(data))
