"""Local CPU speech recognition; only weights are cached between sessions."""
import io
from functools import lru_cache
from threading import Lock

from .native import NativeWorker


@lru_cache(maxsize=1)
def load_whisper(model_path):
    from faster_whisper import WhisperModel
    return WhisperModel(model_path, device="cpu", compute_type="int8", cpu_threads=2,
                        num_workers=1, local_files_only=True), Lock()


class LocalAudioProvider:
    def __init__(self, model_path):
        self.model_path = str(model_path)
        self.worker = NativeWorker()

    async def setup(self):
        await self.worker.run(load_whisper, self.model_path)

    def transcribe(self, data):
        model, lock = load_whisper(self.model_path)
        with lock:
            segments, _ = model.transcribe(io.BytesIO(data), beam_size=1,
                word_timestamps=True, condition_on_previous_text=False,
                temperature=0, vad_filter=False)
            segments = list(segments)  # Generator inference must also stay off the loop.
        transcript = ' '.join(s.text.strip() for s in segments).strip()
        uncertain = [w.word.strip() for s in segments for w in (s.words or [])
                     if w.probability < 0.55 and w.word.strip()]
        ambiguous = not transcript or bool(uncertain) or any(s.avg_logprob < -1.0 for s in segments)
        question = ("Could you repeat " + ', '.join(uncertain[:3]) + "?") if uncertain else "Could you repeat that request?"
        return {"transcript": transcript, "ambiguous": ambiguous,
                "question": question if ambiguous else None,
                "evidence": "Local Whisper transcription; low-confidence words: " + ', '.join(uncertain)}

    async def understand_wav(self, data):
        return await self.worker.run(self.transcribe, data)

    async def aclose(self):
        await self.worker.aclose()
