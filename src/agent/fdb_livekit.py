"""LiveKit voice-agent entry point for Full-Duplex-Bench v3.

The benchmark code and data remain external. Set ``INTERRA_FDB_V3_ROOT`` to the
official repository's ``v3`` directory so this module can load its mock backend.
No benchmark examples or expected answers are imported into the prompt.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class FdbConfig:
    fdb_v3_root: Path
    ollama_model: str = "qwen3:8b"
    ollama_url: str = "http://localhost:11434/v1"
    stt_model: str = "scribe_v2_realtime"
    tts_model: str = "eleven_turbo_v2_5"
    voice_id: str = "hpp4J3VqNfWAUOO0d1Us"
    latency_profile: str = "instant"
    trace_dir: Path = Path("artifacts/fdb_v3")

    @classmethod
    def from_env(cls) -> "FdbConfig":
        default_root = Path(".runtime/Full-Duplex-Bench/v3")
        return cls(
            fdb_v3_root=Path(os.environ.get("INTERRA_FDB_V3_ROOT", default_root)),
            ollama_model=os.environ.get("INTERRA_FDB_LLM_MODEL", "qwen3:8b"),
            ollama_url=os.environ.get("INTERRA_OLLAMA_OPENAI_URL", "http://localhost:11434/v1"),
            stt_model=os.environ.get("INTERRA_ELEVEN_STT_MODEL", "scribe_v2_realtime"),
            tts_model=os.environ.get("INTERRA_ELEVEN_TTS_MODEL", "eleven_turbo_v2_5"),
            voice_id=os.environ.get("INTERRA_ELEVEN_VOICE_ID", "hpp4J3VqNfWAUOO0d1Us"),
            latency_profile=os.environ.get("INTERRA_FDB_LATENCY_PROFILE", "instant"),
            trace_dir=Path(os.environ.get("INTERRA_FDB_TRACE_DIR", "artifacts/fdb_v3")),
        )

    def missing_requirements(self) -> list[str]:
        missing = [
            name
            for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ELEVEN_API_KEY")
            if not os.environ.get(name)
        ]
        if not (self.fdb_v3_root / "mock_apis.py").is_file():
            missing.append(f"INTERRA_FDB_V3_ROOT ({self.fdb_v3_root / 'mock_apis.py'} not found)")
        return missing


def load_benchmark_module(fdb_v3_root: Path) -> ModuleType:
    path = fdb_v3_root / "mock_apis.py"
    if not path.is_file():
        raise FileNotFoundError(
            f"FDB-v3 mock backend not found at {path}. Set INTERRA_FDB_V3_ROOT "
            "to the official Full-Duplex-Bench/v3 directory."
        )
    spec = importlib.util.spec_from_file_location("interra_fdb_mock_apis", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load benchmark backend from {path}")
    module = importlib.util.module_from_spec(spec)
    sibling_path = str(fdb_v3_root.resolve())
    sys.path.insert(0, sibling_path)
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(sibling_path)
        except ValueError:
            pass
    return module


class TraceWriter:
    def __init__(self, trace_dir: Path):
        trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = trace_dir / "livekit-agent.jsonl"
        self._lock = threading.Lock()

    def append(self, kind: str, **payload: Any) -> None:
        record = {"time": time.time(), "kind": kind, **payload}
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class ToolExecutor:
    """Run the official deterministic mock tools without blocking the event loop."""

    def __init__(self, registry: Any, room_name: str, trace: TraceWriter):
        self.registry = registry
        self.room_name = room_name
        self.trace = trace

    async def call(self, name: str, **arguments: Any) -> str:
        started = time.time()
        status = "completed"
        try:
            result = await asyncio.to_thread(self.registry.call, name, **arguments)
        except Exception as exc:
            status = "failed"
            result = {"status": "error", "message": str(exc)}
        ended = time.time()
        call = {
            "function": name,
            "args": arguments,
            "timestamp_start": started,
            "timestamp_end": ended,
        }
        telemetry = Path(tempfile.gettempdir()) / "agent_tool_calls.log"
        with telemetry.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"room": self.room_name, "call": call}) + "\n")
        self.trace.append("tool_call", room=self.room_name, status=status, call=call, result=result)
        return json.dumps(result, ensure_ascii=False)


INSTRUCTIONS = """
You are Interra, a concise voice assistant evaluated on multi-step tool use.
Use the provided tools for every request that needs external or simulated state.
Never invent a tool result and never announce success before a tool returns.
Treat the user's latest words as authoritative: preserve self-corrections, replace
obsolete values, and stop pursuing an earlier goal after an interruption.
For dependent tasks, read each returned identifier or value before making the next
call. Do not ask for confirmation inside this simulated benchmark. Keep spoken
responses short and natural so the user can interrupt at any time.
""".strip()


def main() -> None:
    config = FdbConfig.from_env()
    missing = config.missing_requirements()
    if missing:
        raise SystemExit("Missing FDB-v3 configuration: " + ", ".join(missing))

    benchmark = load_benchmark_module(config.fdb_v3_root)

    from livekit import agents
    from livekit.agents import Agent, AgentServer, AgentSession, llm
    from livekit.plugins import elevenlabs, openai, silero

    function_tool = llm.function_tool if hasattr(llm, "function_tool") else llm.ai_callable

    class BenchmarkTools:
        def __init__(self, executor: ToolExecutor):
            self.executor = executor

        @function_tool(description="Search for available flights to a destination and date.")
        async def search_flights(self, destination: str, date: str) -> str:
            return await self.executor.call("search_flights", destination=destination, date=date)

        @function_tool(description="Book the selected flight for a passenger.")
        async def book_flight(self, passenger_name: str, flight_id: str = "FL123") -> str:
            return await self.executor.call("book_flight", passenger_name=passenger_name, flight_id=flight_id)

        @function_tool(description="Update the simulated user's identity document.")
        async def update_identity_doc(self, doc_type: str, doc_number: str) -> str:
            return await self.executor.call("update_identity_doc", doc_type=doc_type, doc_number=doc_number)

        @function_tool(description="Retrieve exact benefits for a credit-card type.")
        async def get_card_benefits(self, card_type: str) -> str:
            return await self.executor.call("get_card_benefits", card_type=card_type)

        @function_tool(description="Convert an amount using the simulated exchange-rate service.")
        async def get_exchange_rate(self, amount: float, from_currency: str, to_currency: str) -> str:
            return await self.executor.call(
                "get_exchange_rate", amount=amount, from_currency=from_currency, to_currency=to_currency
            )

        @function_tool(description="Modify the simulated autopay source for a bill type.")
        async def modify_autopay(self, bill_type: str, source_account: str) -> str:
            return await self.executor.call("modify_autopay", bill_type=bill_type, source_account=source_account)

        @function_tool(description="Search for apartments matching city, bedroom, and price constraints.")
        async def search_apartments(self, city: str, bedrooms: int, max_price: float) -> str:
            return await self.executor.call(
                "search_apartments", city=city, bedrooms=bedrooms, max_price=max_price
            )

        @function_tool(description="Calculate a commute between two addresses.")
        async def calculate_commute(
            self, origin_address: str, destination_address: str, mode: str = "driving"
        ) -> str:
            return await self.executor.call(
                "calculate_commute",
                origin_address=origin_address,
                destination_address=destination_address,
                mode=mode,
            )

        @function_tool(description="Update one simulated apartment-search filter immediately.")
        async def update_search_filter(self, filter_name: str, value: str) -> str:
            return await self.executor.call("update_search_filter", filter_name=filter_name, value=value)

        @function_tool(description="Track a physical order using its order identifier.")
        async def track_order(self, order_id: str) -> str:
            return await self.executor.call("track_order", order_id=order_id)

        @function_tool(description="Search the simulated product catalog.")
        async def search_products(self, query: str, max_price: float | None = None) -> str:
            return await self.executor.call("search_products", query=query, max_price=max_price)

        @function_tool(description="Add a product and quantity to the simulated cart.")
        async def add_to_cart(self, product_id: str, quantity: int = 1) -> str:
            return await self.executor.call("add_to_cart", product_id=product_id, quantity=quantity)

    class InterraVoiceAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=INSTRUCTIONS)

    server = AgentServer()
    trace = TraceWriter(config.trace_dir)

    @server.rtc_session()
    async def entrypoint(ctx: agents.JobContext) -> None:
        registry = benchmark.MockAPIRegistry(latency_profile=config.latency_profile)
        executor = ToolExecutor(registry, ctx.room.name, trace)
        tools = llm.find_function_tools(BenchmarkTools(executor))

        session = AgentSession(
            vad=silero.VAD.load(min_speech_duration=0.05, min_silence_duration=0.5),
            stt=elevenlabs.STT(model=config.stt_model, no_verbatim=False),
            llm=openai.LLM.with_ollama(
                model=config.ollama_model,
                base_url=config.ollama_url,
                temperature=0.1,
                parallel_tool_calls=False,
            ),
            tts=elevenlabs.TTS(voice_id=config.voice_id, model=config.tts_model),
            tools=tools,
            min_endpointing_delay=0.35,
            max_endpointing_delay=3.0,
        )

        @session.on("user_input_transcribed")
        def on_transcript(event: Any) -> None:
            trace.append(
                "transcript",
                room=ctx.room.name,
                transcript=event.transcript,
                is_final=event.is_final,
            )

        @session.on("agent_state_changed")
        def on_state(event: Any) -> None:
            trace.append("agent_state", room=ctx.room.name, state=str(event.new_state))

        trace.append("session_started", room=ctx.room.name)
        await session.start(room=ctx.room, agent=InterraVoiceAgent())

    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
