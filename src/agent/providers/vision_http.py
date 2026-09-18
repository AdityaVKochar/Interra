"""Explicit PNG-to-observation service contract, independent of the coordinator."""
import httpx


class HTTPVisionProvider:
    def __init__(self, endpoint, client=None):
        self.endpoint = endpoint
        self.client = client or httpx.AsyncClient(timeout=60.)
        self.owns_client = client is None

    async def understand_png(self, data):
        response = await self.client.post(self.endpoint, content=data, headers={"Content-Type": "image/png"})
        response.raise_for_status()
        return response.json()

    async def aclose(self):
        if self.owns_client:
            await self.client.aclose()
