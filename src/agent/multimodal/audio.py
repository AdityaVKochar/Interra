import base64
import io
import wave
from typing import Protocol
from pydantic import Field, JsonValue
from ..models import Model


class AudioObservation(Model):
    transcript: str
    intent_hint: str | None = None
    slot_hints: dict[str, JsonValue] = Field(default_factory=dict)
    ambiguous: bool = False
    question: str | None = None
    evidence: str = ""


class AudioUnderstandingProvider(Protocol):
    async def understand_wav(self, data: bytes) -> dict | str: ...


def decode_media(data_ref: str) -> bytes:
    # File/remote references are deliberately resolved by an evaluator adapter, not arbitrary I/O.
    if not data_ref.startswith("base64:") or len(data_ref) > 16_000_000:
        raise ValueError("local media protocol requires bounded base64: data")
    return base64.b64decode(data_ref[7:], validate=True)


def validate_wav(data):
    with wave.open(io.BytesIO(data), "rb") as wav:
        if wav.getnchannels() not in (1, 2) or wav.getsampwidth() not in (1, 2, 3, 4):
            raise ValueError("unsupported WAV layout")
        if wav.getnframes() == 0 or wav.getnframes() / wav.getframerate() > 120:
            raise ValueError("WAV must contain 0-120 seconds of audio")
        expected = wav.getnframes() * wav.getnchannels() * wav.getsampwidth()
        if len(wav.readframes(wav.getnframes())) != expected:
            raise ValueError("truncated WAV data")


async def understand_audio(provider, data_ref):
    data = decode_media(data_ref)
    validate_wav(data)
    raw = await provider.understand_wav(data)
    return AudioObservation.model_validate_json(raw) if isinstance(raw, str) else AudioObservation.model_validate(raw)
