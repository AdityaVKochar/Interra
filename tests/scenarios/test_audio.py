import asyncio
import base64
import io
import unittest
import wave
from agent.multimodal.audio import AudioObservation
from agent.multimodal.fusion import PerceptionResult
from tests.helpers import Harness, ScriptedPlanner, spec, plan


def wav_ref():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 160)
    return "base64:" + base64.b64encode(stream.getvalue()).decode()


class AudioMock:
    def __init__(self, value):
        self.value = value
        self.data = None

    async def understand_wav(self, data):
        self.data = data
        return await self.value if isinstance(self.value, asyncio.Future) else self.value


class AudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_audio_only(self):
        mock = AudioMock({"transcript": "find Delhi"})
        async with Harness(ScriptedPlanner(plan(), {"final_response": "Found"}), self.id()) as h:
            h.runtime.perception.audio_provider = mock
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.send("AUDIO_CLIP", mime_type="audio/wav", data_ref=wav_ref())
            call = await h.action("TOOL_CALL")
            await h.send("TOOL_RESULT", call_id=call.payload["call_id"], ok=True, result={})
            await h.action("FINAL")
            self.assertTrue(mock.data.startswith(b"RIFF"))
            self.assertIn("OBSERVATION_ACCEPTED", h.kinds())

    async def test_audio_correction(self):
        async with Harness(ScriptedPlanner(plan(), plan("Mumbai")), self.id()) as h:
            h.runtime.perception.audio_provider = AudioMock({"transcript": "Mumbai instead"})
            await h.send("TOOL_MANIFEST", tools=[spec()])
            await h.text("Delhi")
            old = (await h.action("TOOL_CALL")).payload["call_id"]
            await h.send("AUDIO_CLIP", mime_type="audio/wav", data_ref=wav_ref())
            await h.action("CANCEL_TOOL_CALL")
            await h.action("TOOL_CALL")
            await h.send("TOOL_RESULT", call_id=old, ok=True, result={})
            self.assertIn("STALE_RESULT_DISCARDED", h.kinds())
            self.assertEqual(h.runtime.state.snapshot.slots["destination"], "Mumbai")

    async def test_delayed_audio_after_text(self):
        pending = asyncio.get_running_loop().create_future()
        async with Harness(ScriptedPlanner({"clarification": "Which Mumbai location?"}), self.id()) as h:
            h.runtime.perception.audio_provider = AudioMock(pending)
            await h.send("AUDIO_CLIP", mime_type="audio/wav", data_ref=wav_ref())
            epoch = h.runtime.epoch
            source = f"e{h.n}"
            await h.text("Mumbai")
            await h.action("CLARIFY")
            await h.runtime.input.put(PerceptionResult(source, 0., epoch, "audio", AudioObservation(transcript="Delhi")))
            await h.runtime.input.join()
            self.assertIn("STALE_PERCEPTION_DISCARDED", h.kinds())
            self.assertTrue(pending.cancelled())

    async def test_ambiguous_and_invalid_audio(self):
        for data, observation in [(wav_ref(), {"transcript": "", "ambiguous": True, "question": "Delhi or Mumbai?"}),
                                  ("base64:bm90IHdhdg==", {"transcript": "ignored"})]:
            async with Harness(ScriptedPlanner(), self.id()+str(len(data))) as h:
                h.runtime.perception.audio_provider = AudioMock(observation)
                await h.send("AUDIO_CLIP", mime_type="audio/wav", data_ref=data)
                await h.action("CLARIFY")
                self.assertFalse(h.runtime.calls)
                self.assertTrue("PERCEPTION_FAILED" in h.kinds() or "OBSERVATION_ACCEPTED" in h.kinds())
