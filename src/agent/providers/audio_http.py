"""Adapter for an explicitly configured WAV-to-observation HTTP service.

Contract: POST audio/wav bytes -> JSON AudioObservation. No vendor protocol is assumed.
"""
import httpx


class HTTPAudioProvider:
    def __init__(self, endpoint, client=None):
        self.endpoint = endpoint
        self.client = client or httpx.AsyncClient(timeout=60.)
        self.owns_client = client is None

    async def understand_wav(self, data):
        response = await self.client.post(self.endpoint, content=data, headers={"Content-Type": "audio/wav"})
        response.raise_for_status()
        return response.json()

    async def aclose(self):
        if self.owns_client:
            await self.client.aclose()
