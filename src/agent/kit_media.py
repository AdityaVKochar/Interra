"""Resolve only delivered media references beneath the configured kit root."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import wave

from .multimodal.audio import validate_wav


class KitMediaLoader:
    def __init__(self, root, ffmpeg=None):
        self.root = Path(root).resolve()
        self.ffmpeg = ffmpeg or os.environ.get("INTERRA_FFMPEG", "ffmpeg")

    def read(self, ref):
        if not isinstance(ref, str) or Path(ref).is_absolute():
            raise ValueError("media reference must be relative")
        path = (self.root / ref).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("media reference escapes kit root")
        with path.open("rb") as stream:
            data = stream.read(12_000_001)
        if len(data) > 12_000_000:
            raise ValueError("media exceeds size limit")
        return data

    async def wav(self, data):
        if data.startswith(b"RIFF"):
            validate_wav(data)
            return data
        # stdin prevents ffmpeg from resolving paths or fetching network resources.
        proc = await asyncio.create_subprocess_exec(self.ffmpeg, "-v", "error", "-nostdin",
            "-f", "mp3", "-i", "pipe:0", "-t", "120", "-ar", "16000", "-ac", "1",
            "-f", "s16le", "pipe:1", stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            async with asyncio.timeout(15):
                pcm, error = await proc.communicate(data)
            if proc.returncode or not pcm:
                raise ValueError("MP3 decoding failed")
            out = io.BytesIO()
            with wave.open(out, "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(pcm)
            return out.getvalue()
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

    async def __call__(self, event):
        ref = event.payload["data_ref"]
        if not ref.startswith("kit:"):
            return ref
        refs = json.loads(ref[4:])
        if not isinstance(refs, list) or not 1 <= len(refs) <= 64:
            raise ValueError("invalid media references")
        if event.type == "VIDEO_FRAME":
            data = await asyncio.to_thread(self.read, refs[-1])
        else:
            frames, params = [], None
            for item in refs:
                data = await self.wav(await asyncio.to_thread(self.read, item))
                with wave.open(io.BytesIO(data), "rb") as wav:
                    layout = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
                    if params is not None and layout != params:
                        raise ValueError("incompatible audio chunk layouts")
                    params = layout
                    frames.append(wav.readframes(wav.getnframes()))
                    if sum(map(len, frames)) > 12_000_000:
                        raise ValueError("audio turn exceeds size limit")
            out = io.BytesIO()
            with wave.open(out, "wb") as wav:
                wav.setparams((*params, 0, "NONE", "not compressed"))
                wav.writeframes(b"".join(frames))
            data = out.getvalue()
            validate_wav(data)
        return "base64:" + base64.b64encode(data).decode("ascii")
