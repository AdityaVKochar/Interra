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
import re
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from livekit.plugins import silero
from livekit.agents.types import APIConnectOptions

# Plugins register themselves with LiveKit Agents during import. LiveKit calls
# the process setup hook on a worker thread, so import optional providers while
# this module is being loaded on the process main thread instead.
if os.environ.get("INTERRA_FDB_LLM_PROVIDER", "livekit") == "ollama":
    from livekit.plugins import openai as _openai_plugin  # noqa: F401


def _model_fallbacks(name: str, default: str) -> tuple[str, ...]:
    configured = os.environ.get(name, default)
    return tuple(model.strip() for model in configured.split(",") if model.strip())


@dataclass(frozen=True)
class FdbConfig:
    fdb_v3_root: Path
    llm_provider: str = "livekit"
    llm_model: str = "openai/gpt-4.1-mini"
    ollama_model: str = "qwen3:8b"
    ollama_url: str = "http://localhost:11434/v1"
    stt_model: str = "deepgram/nova-3"
    stt_fallback_models: tuple[str, ...] = ("assemblyai/universal-3-5-pro",)
    tts_model: str = "cartesia/sonic-3"
    tts_fallback_models: tuple[str, ...] = ("deepgram/aura-2:athena",)
    voice_id: str = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
    latency_profile: str = "instant"
    trace_dir: Path = Path("artifacts/fdb_v3")
    session_cooldown_seconds: float = 3.0

    def __post_init__(self) -> None:
        if self.session_cooldown_seconds < 0:
            raise ValueError("session_cooldown_seconds must be non-negative")

    @classmethod
    def from_env(cls) -> "FdbConfig":
        default_root = Path(".runtime/Full-Duplex-Bench/v3")
        return cls(
            fdb_v3_root=Path(os.environ.get("INTERRA_FDB_V3_ROOT", default_root)),
            llm_provider=os.environ.get("INTERRA_FDB_LLM_PROVIDER", "livekit"),
            llm_model=os.environ.get("INTERRA_FDB_LLM_MODEL", "openai/gpt-4.1-mini"),
            ollama_model=os.environ.get("INTERRA_OLLAMA_MODEL", "qwen3:8b"),
            ollama_url=os.environ.get("INTERRA_OLLAMA_OPENAI_URL", "http://localhost:11434/v1"),
            stt_model=os.environ.get("INTERRA_FDB_STT_MODEL", "deepgram/nova-3"),
            stt_fallback_models=_model_fallbacks(
                "INTERRA_FDB_STT_FALLBACK_MODELS", "assemblyai/universal-3-5-pro"
            ),
            tts_model=os.environ.get("INTERRA_FDB_TTS_MODEL", "cartesia/sonic-3"),
            tts_fallback_models=_model_fallbacks(
                "INTERRA_FDB_TTS_FALLBACK_MODELS", "deepgram/aura-2:athena"
            ),
            voice_id=os.environ.get("INTERRA_FDB_VOICE_ID", "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
            latency_profile=os.environ.get("INTERRA_FDB_LATENCY_PROFILE", "instant"),
            trace_dir=Path(os.environ.get("INTERRA_FDB_TRACE_DIR", "artifacts/fdb_v3")),
            session_cooldown_seconds=float(
                os.environ.get("INTERRA_FDB_SESSION_COOLDOWN_SECONDS", "3")
            ),
        )

    def missing_requirements(self) -> list[str]:
        missing = [
            name
            for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
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


# The official recorder keeps agent audio only until the wav ends plus 1.5s of
# trailing silence, then disconnects. A reply that starts after that window is
# scored as silence. These bounds keep the turn inside that window.
RECORDING_TAIL_S = 1.5
def benchmark_turn_handling() -> dict[str, Any]:
    """Start the model during the utterance and commit the turn before the recorder leaves."""
    return {
        "endpointing": {"mode": "fixed", "min_delay": 0.7, "max_delay": RECORDING_TAIL_S - 0.3},
        "preemptive_generation": {
            "enabled": True,
            "preemptive_tts": True,
            "max_speech_duration": 180.0,
            "max_retries": 200,
        },
    }


def ollama_llm_kwargs(config: FdbConfig) -> dict[str, Any]:
    """Local Qwen must answer inside the recording window. Thinking is off only after a live probe."""
    kwargs: dict[str, Any] = {
        "model": config.ollama_model,
        "api_key": "ollama",
        "base_url": config.ollama_url,
        "temperature": 0.1,
        "parallel_tool_calls": False,
        "_strict_tool_schema": False,
    }
    if os.environ.get("INTERRA_OLLAMA_DISABLE_THINK") == "1":
        kwargs["extra_body"] = {"think": False}
    return kwargs


def livekit_speech_models(inference: Any, config: FdbConfig) -> tuple[Any, Any]:
    """Route speech through LiveKit with cross-provider failover and spaced retries."""
    retry_options = APIConnectOptions(max_retry=2, retry_interval=4.0, timeout=20.0)
    stt_options: dict[str, Any] = {
        "model": config.stt_model,
        "language": "en",
        "conn_options": retry_options,
    }
    if config.stt_fallback_models:
        stt_options["fallback"] = list(config.stt_fallback_models)
    tts_options: dict[str, Any] = {
        "model": config.tts_model,
        "voice": config.voice_id,
        "conn_options": retry_options,
    }
    if config.tts_fallback_models:
        tts_options["fallback"] = list(config.tts_fallback_models)
    return (
        inference.STT(**stt_options),
        inference.TTS(**tts_options),
    )


def livekit_llm_model(inference: Any, config: FdbConfig) -> Any:
    """Use a hosted tool-calling model under the same LiveKit project."""
    return inference.LLM(
        model=config.llm_model,
        extra_kwargs={"temperature": 0.1, "parallel_tool_calls": False},
    )


def _as_float(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise TypeError(f"expected a number, got {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    normalized = str(value).strip().replace(",", "").replace("$", "")
    try:
        return float(normalized)
    except ValueError:
        pass
    units = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16,
        "seventeen": 17, "eighteen": 18, "nineteen": 19,
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    }
    total = current = 0
    tokens = re.findall(r"[a-z]+", normalized.lower().replace("-", " "))
    if not tokens:
        raise ValueError(f"Invalid numeric value: {value!r}")
    for token in tokens:
        if token in {"and", "dollar", "dollars"}:
            continue
        if token in units:
            current += units[token]
        elif token == "hundred":
            current = max(current, 1) * 100
        elif token == "thousand":
            total += max(current, 1) * 1000
            current = 0
        else:
            raise ValueError(f"Invalid numeric value: {value!r}")
    return float(total + current)


def _as_int(value: Any) -> int:
    return int(_as_float(value))


def normalize_identifier(value: str) -> str:
    """Join explicitly spelled letters/digits without rewriting ordinary IDs."""
    digits = {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    }
    tokens = value.split()
    if len(tokens) > 1 and all(
        token.lower() in digits or (len(token) == 1 and token.isalnum())
        for token in tokens
    ):
        return "".join(digits.get(token.lower(), token.upper()) for token in tokens)
    return value


def normalize_filter_value(value: str | float | bool) -> str | float | bool:
    """Preserve strings while restoring explicit numeric and boolean types."""
    if not isinstance(value, str):
        return value
    normalized = value.strip().lower()
    if normalized in {"true", "false"}:
        return normalized == "true"
    try:
        number = _as_float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


INSTRUCTIONS = """
You are Interra, a voice assistant in a simulated tool benchmark.
Listen to the complete request and apply the user's latest corrections.
Call every tool needed to finish the requested task. For dependent calls,
use identifiers returned by earlier tools. Do not speak a final answer after
only the first step of a multi-step request. If a required value is truly
missing, ask one concise clarification. Never invent a tool result.
When all requested tools have finished, speak one brief grounded answer.
Write spoken identifiers and street numbers in their ordinary letter/digit
form. Preserve the user's requested product wording, including plurals.
Use currency codes for currencies and account types or identifiers without
conversational filler. Keep numeric and boolean tool values properly typed.
""".strip()


def prewarm(process: Any) -> None:
    """Load model code and weights before a recording enters the job event loop."""
    process.userdata["vad"] = silero.VAD.load(
        min_speech_duration=0.05, min_silence_duration=0.3
    )
    config = FdbConfig.from_env()
    process.userdata["benchmark"] = load_benchmark_module(config.fdb_v3_root)


async def run_session_lifecycle(
    ctx: Any,
    session: Any,
    agent: Any,
    room_options: Any,
    trace: TraceWriter,
    *,
    participant_identity: str,
    drain_timeout: float = 20.0,
    cooldown_seconds: float = 0.0,
) -> None:
    """Own the session until its participant leaves or the session fails.

    Drain pending speech after disconnect, then release STT and the worker job.
    Other participants leaving must not end this participant's session.
    """
    disconnected = asyncio.Event()
    closed = asyncio.Event()

    def on_disconnect(participant: Any) -> None:
        if participant.identity == participant_identity and not disconnected.is_set():
            trace.append("participant_disconnected", room=ctx.room.name)
            disconnected.set()

    def on_close(event: Any) -> None:
        trace.append(
            "session_closed", room=ctx.room.name,
            reason=str(event.reason), failed=event.error is not None,
        )
        closed.set()

    ctx.room.on("participant_disconnected", on_disconnect)
    session.on("close", on_close)
    waiters: list[asyncio.Task[Any]] = []
    try:
        await session.start(room=ctx.room, agent=agent, room_options=room_options)
        waiters = [
            asyncio.create_task(disconnected.wait(), name="interra-participant-disconnect"),
            asyncio.create_task(closed.wait(), name="interra-session-close"),
        ]
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        if disconnected.is_set() and not closed.is_set():
            trace.append("session_drain_started", room=ctx.room.name)
            try:
                await asyncio.wait_for(session.drain(), timeout=drain_timeout)
            except TimeoutError:
                trace.append("session_drain_timeout", room=ctx.room.name)
            else:
                trace.append("session_drain_completed", room=ctx.room.name)
    finally:
        for waiter in waiters:
            waiter.cancel()
        if waiters:
            await asyncio.gather(*waiters, return_exceptions=True)
        try:
            await session.aclose()
        finally:
            ctx.room.off("participant_disconnected", on_disconnect)
            session.off("close", on_close)
            trace.append("session_cleanup", room=ctx.room.name)
            if cooldown_seconds > 0:
                trace.append(
                    "provider_cooldown_started",
                    room=ctx.room.name,
                    seconds=cooldown_seconds,
                )
                try:
                    await asyncio.sleep(cooldown_seconds)
                finally:
                    ctx.shutdown(reason="Interra session ended")
                trace.append("provider_cooldown_completed", room=ctx.room.name)
            else:
                ctx.shutdown(reason="Interra session ended")


def create_benchmark_tools(executor: ToolExecutor, function_tool: Any) -> Any:
    """Expose the official backend contract with typed speech arguments."""
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

        @function_tool(description="Convert an amount using the simulated exchange-rate service. Pass amount as a number.")
        async def get_exchange_rate(self, amount: float | str, from_currency: str, to_currency: str) -> str:
            return await self.executor.call(
                "get_exchange_rate",
                amount=_as_float(amount),
                from_currency=from_currency,
                to_currency=to_currency,
            )

        @function_tool(description="Modify the simulated autopay source for a bill type.")
        async def modify_autopay(self, bill_type: str, source_account: str) -> str:
            return await self.executor.call("modify_autopay", bill_type=bill_type, source_account=source_account)

        @function_tool(description="Search for apartments. Pass bedrooms and max_price as numbers.")
        async def search_apartments(
            self, city: str, bedrooms: int | str, max_price: float | str,
            pets_allowed: bool | None = None,
        ) -> str:
            arguments: dict[str, Any] = {
                "city": city, "bedrooms": _as_int(bedrooms), "max_price": _as_float(max_price),
            }
            if pets_allowed is not None:
                arguments["pets_allowed"] = pets_allowed
            return await self.executor.call("search_apartments", **arguments)

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
        async def update_search_filter(self, filter_name: str, value: str | float | bool) -> str:
            return await self.executor.call(
                "update_search_filter", filter_name=filter_name, value=normalize_filter_value(value)
            )

        @function_tool(description="Track a physical order using its order identifier.")
        async def track_order(self, order_id: str) -> str:
            return await self.executor.call("track_order", order_id=normalize_identifier(order_id))

        @function_tool(description="Search the simulated product catalog. Pass max_price as a number when the user gives one.")
        async def search_products(self, query: str, max_price: float | str | None = None) -> str:
            arguments: dict[str, Any] = {"query": query}
            if max_price is not None:
                arguments["max_price"] = _as_float(max_price)
            return await self.executor.call("search_products", **arguments)

        @function_tool(description="Add a product and quantity to the simulated cart. Pass quantity as a number.")
        async def add_to_cart(self, product_id: str, quantity: int | str = 1) -> str:
            return await self.executor.call(
                "add_to_cart", product_id=normalize_identifier(product_id), quantity=_as_int(quantity)
            )

    return BenchmarkTools(executor)


async def entrypoint(ctx: Any) -> None:
    """LiveKit job entrypoint. Must stay module-level so the worker process can import it."""
    config = FdbConfig.from_env()
    missing = config.missing_requirements()
    if missing:
        raise RuntimeError("Missing FDB-v3 configuration: " + ", ".join(missing))

    benchmark = ctx.proc.userdata["benchmark"]
    from livekit.agents import Agent, AgentSession, inference, llm

    function_tool = llm.function_tool if hasattr(llm, "function_tool") else llm.ai_callable

    class InterraVoiceAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=INSTRUCTIONS)

    trace = TraceWriter(config.trace_dir)
    registry = benchmark.MockAPIRegistry(latency_profile=config.latency_profile)
    executor = ToolExecutor(registry, ctx.room.name, trace)
    tools = llm.find_function_tools(create_benchmark_tools(executor, function_tool))

    speech_stt, speech_tts = livekit_speech_models(inference, config)
    if config.llm_provider == "livekit":
        model = livekit_llm_model(inference, config)
    elif config.llm_provider == "ollama":
        from livekit.plugins import openai

        model = openai.LLM(**ollama_llm_kwargs(config))
    else:
        raise ValueError(f"Unsupported FDB LLM provider: {config.llm_provider}")
    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=speech_stt,
        llm=model,
        tts=speech_tts,
        tools=tools,
        turn_handling=benchmark_turn_handling(),
        max_tool_steps=6,
        user_away_timeout=None,
    )
    @session.on("user_state_changed")
    def on_user_state(event: Any) -> None:
        trace.append("user_state", room=ctx.room.name, state=str(event.new_state))

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
    print(
        "Interra FDB speech:"
        f" stt={config.stt_model} llm={config.llm_provider}:{config.llm_model} tts={config.tts_model}",
        flush=True,
    )
    # Keep playout alive briefly after disconnect, then explicitly release the
    # session. Leaving close_on_disconnect=False without cleanup leaks STT jobs.
    from livekit.agents import room_io

    await ctx.connect()
    participant = await ctx.wait_for_participant()
    await run_session_lifecycle(
        ctx, session, InterraVoiceAgent(),
        room_io.RoomOptions(
            close_on_disconnect=False, participant_identity=participant.identity
        ),
        trace,
        participant_identity=participant.identity,
        cooldown_seconds=config.session_cooldown_seconds,
    )


def main() -> None:
    config = FdbConfig.from_env()
    missing = config.missing_requirements()
    if missing:
        raise SystemExit("Missing FDB-v3 configuration: " + ", ".join(missing))

    from livekit import agents
    from livekit.agents import AgentServer

    server = AgentServer(setup_fnc=prewarm, num_idle_processes=1, initialize_process_timeout=60.0)
    server.rtc_session(entrypoint)
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
