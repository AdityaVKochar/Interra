"""Bootstrap, run, and evaluate Interra against Full-Duplex-Bench v3."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path


REPOSITORY = "https://github.com/DanielLin94144/Full-Duplex-Bench.git"
PINNED_COMMIT = "3e799c45a045256f47d5f1c9cda90157e2d2ec9e"
DATA_FILE_ID = "1SO_4MTazWQ_jvCx0dtmpQ-t40bdd07yz"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCH_ROOT = PROJECT_ROOT / ".runtime" / "Full-Duplex-Bench"
REPORT_ROOT = PROJECT_ROOT / "artifacts" / "fdb_v3"


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def benchmark_root() -> Path:
    configured = os.environ.get("INTERRA_FDB_V3_ROOT")
    return Path(configured).resolve().parent if configured else DEFAULT_BENCH_ROOT


def data_root(v3_root: Path) -> Path:
    return Path(os.environ.get("INTERRA_FDB_DATA_ROOT", v3_root / "fdb_v3_data_released")).resolve()


def bootstrap(download_data: bool) -> Path:
    root = benchmark_root()
    v3_root = root / "v3"
    if not (root / ".git").is_dir():
        root.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", REPOSITORY, str(root)], cwd=PROJECT_ROOT)
    run(["git", "fetch", "--depth", "1", "origin", PINNED_COMMIT], cwd=root)
    run(["git", "checkout", "--detach", PINNED_COMMIT], cwd=root)

    target = data_root(v3_root)
    if download_data and not target.is_dir():
        import gdown

        archive = root / "fdb_v3_data_released.zip"
        print(f"Downloading official FDB-v3 data to {archive}", flush=True)
        gdown.download(id=DATA_FILE_ID, output=str(archive), quiet=False)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(v3_root)
        archive.unlink()
        if not target.is_dir():
            raise RuntimeError(f"Downloaded archive did not produce {target}")
    return v3_root


def check(v3_root: Path, require_data: bool = True) -> None:
    missing = [
        name
        for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ELEVEN_API_KEY")
        if not os.environ.get(name)
    ]
    if not (v3_root / "mock_apis.py").is_file():
        missing.append(f"benchmark checkout ({v3_root / 'mock_apis.py'})")
    if require_data and not data_root(v3_root).is_dir():
        missing.append(f"benchmark data ({data_root(v3_root)})")
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg executable")
    if missing:
        raise SystemExit("FDB-v3 readiness failed; missing: " + ", ".join(missing))
    print("FDB-v3 configuration is ready.")


def benchmark(v3_root: Path, force: bool) -> None:
    command = [
        sys.executable,
        "run_tool_benchmark_all_released.py",
        "--provider",
        "interra_elevenlabs",
        "--root_dir",
        str(data_root(v3_root)),
    ]
    if force:
        command.append("--force")
    run(command, cwd=v3_root, env=os.environ.copy())


def evaluate(v3_root: Path, use_llm: bool) -> None:
    if use_llm and not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for the optional self-reported LLM-judge evaluation.")
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    shared = [
        "--benchmark",
        str(v3_root / "benchmark_data_v2.json"),
        "--results-dir",
        str(data_root(v3_root)),
        "--provider",
        "interra_elevenlabs",
    ]
    for script, output in (
        ("evaluate_tool_calls.py", "interra_elevenlabs_evaluation_report.json"),
        ("evaluate_pass_rate.py", "interra_elevenlabs_pass_rate_report.json"),
    ):
        command = [sys.executable, script, *shared, "--output", str(REPORT_ROOT / output)]
        if use_llm:
            command.append("--use-llm")
        run(command, cwd=v3_root)
    if use_llm:
        run(
            [
                sys.executable,
                "analyze_tool_latency.py",
                "--results-dir",
                str(data_root(v3_root)),
                "--provider",
                "interra_elevenlabs",
                "--output",
                str(REPORT_ROOT / "interra_elevenlabs_latency_report.json"),
            ],
            cwd=v3_root,
        )
    else:
        print(
            "Skipped LLM-assisted latency post-analysis; pass --use-llm with "
            "OPENAI_API_KEY to generate it.",
            flush=True,
        )


def all_steps(v3_root: Path, force: bool, use_llm: bool) -> None:
    env = os.environ.copy()
    env["INTERRA_FDB_V3_ROOT"] = str(v3_root)
    agent = subprocess.Popen([sys.executable, "-m", "agent.fdb_livekit", "start"], cwd=PROJECT_ROOT, env=env)
    try:
        for _ in range(20):
            if agent.poll() is not None:
                raise RuntimeError(f"LiveKit agent exited during startup with code {agent.returncode}")
            time.sleep(0.5)
        benchmark(v3_root, force)
    finally:
        agent.terminate()
        try:
            agent.wait(timeout=10)
        except subprocess.TimeoutExpired:
            agent.kill()
            agent.wait(timeout=5)
    evaluate(v3_root, use_llm)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bootstrap", "check", "agent", "benchmark", "evaluate", "all"))
    parser.add_argument("--download-data", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--use-llm", action="store_true")
    args = parser.parse_args()

    if args.command == "bootstrap":
        print(bootstrap(args.download_data))
        return

    v3_root = Path(os.environ.get("INTERRA_FDB_V3_ROOT", DEFAULT_BENCH_ROOT / "v3")).resolve()
    if args.command == "check":
        check(v3_root)
    elif args.command == "agent":
        check(v3_root, require_data=False)
        run([sys.executable, "-m", "agent.fdb_livekit", "start"], cwd=PROJECT_ROOT)
    elif args.command == "benchmark":
        check(v3_root)
        benchmark(v3_root, args.force)
    elif args.command == "evaluate":
        check(v3_root)
        evaluate(v3_root, args.use_llm)
    else:
        check(v3_root)
        all_steps(v3_root, args.force, args.use_llm)


if __name__ == "__main__":
    main()
