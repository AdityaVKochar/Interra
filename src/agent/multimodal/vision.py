import struct
import zlib
from typing import Protocol
from pydantic import Field, JsonValue
from ..models import Model
from .audio import decode_media


class VisualObservation(Model):
    summary: str
    facts: dict[str, JsonValue] = Field(default_factory=dict)
    ambiguous: bool = False
    question: str | None = None
    evidence: str = ""
    image_embedding: list[float] | None = Field(default=None, min_length=512, max_length=512)
    embedding_model: str | None = None


class VisionUnderstandingProvider(Protocol):
    async def understand_png(self, data: bytes) -> dict | str: ...


def validate_png(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature")
    offset, chunks = 8, []
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("truncated PNG data")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", data[end - 4:end])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError("PNG checksum mismatch")
        if not chunks:
            if kind != b"IHDR" or length != 13:
                raise ValueError("PNG requires IHDR first")
            width, height = struct.unpack(">II", payload[:8])
            if width == 0 or height == 0 or width * height > 16_000_000:
                raise ValueError("PNG dimensions outside supported limits")
        chunks.append(kind)
        offset = end
        if kind == b"IEND":
            if length or end != len(data):
                raise ValueError("invalid PNG ending")
            break
    if not chunks or chunks[-1] != b"IEND" or b"IDAT" not in chunks:
        raise ValueError("incomplete PNG")


async def understand_image(provider, data_ref):
    data = decode_media(data_ref)
    validate_png(data)
    raw = await provider.understand_png(data)
    return VisualObservation.model_validate_json(raw) if isinstance(raw, str) else VisualObservation.model_validate(raw)
