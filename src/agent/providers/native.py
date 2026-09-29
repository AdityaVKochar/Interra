"""Bounded native inference. Cancellation discards output but joins running work."""
import asyncio
from concurrent.futures import ThreadPoolExecutor


class NativeWorker:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="interra-inference")
        self.lock = asyncio.Lock()
        self.closed = False
        self.pending = set()

    async def run(self, fn, *args):
        async with self.lock:
            if self.closed:
                raise RuntimeError("inference worker is closed")
            future = asyncio.get_running_loop().run_in_executor(self.executor, fn, *args)
            self.pending.add(future)
            future.add_done_callback(self.pending.discard)
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                # Native inference cannot be killed safely. Keep ownership until it exits;
                # the event loop and runtime's epoch invalidation remain responsive.
                try:
                    await asyncio.shield(future)
                except Exception:
                    pass
                raise

    async def aclose(self):
        async with self.lock:
            self.closed = True
            if self.pending:
                await asyncio.gather(*(asyncio.shield(f) for f in self.pending), return_exceptions=True)
            self.executor.shutdown(wait=True, cancel_futures=True)
