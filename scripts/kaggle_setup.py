"""Prepare a reproducible Interra FDB-v3 worker on Kaggle.

This script is intended to be uploaded as a Kaggle *script* kernel.  It reads
provider credentials only from Kaggle Secrets and writes no credentials into
the notebook output or source dataset.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


WORK = Path("/kaggle/working")
INPUT_ROOT = Path("/kaggle/input/interra-fdb-v3-private-source")
PROJECT = WORK / "Interra"
VENV = WORK / "interra-fdb-venv"
REPORT = WORK / "interra-setup-report.json"
RUN_FULL_BENCHMARK = False


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def venv_python() -> str:
    return str(VENV / "bin" / "python")


def read_kaggle_secrets() -> list[str]:
    missing: list[str] = []
    try:
        from kaggle_secrets import UserSecretsClient

        client = UserSecretsClient()
        for name in (
            "LIVEKIT_URL",
            "LIVEKIT_API_KEY",
            "LIVEKIT_API_SECRET",
            "ELEVEN_API_KEY",
        ):
            try:
                os.environ[name] = client.get_secret(name)
            except Exception:
                missing.append(name)
    except Exception:
        missing = [
            "LIVEKIT_URL",
            "LIVEKIT_API_KEY",
            "LIVEKIT_API_SECRET",
            "ELEVEN_API_KEY",
        ]
    return sorted(set(missing))


def source_root() -> Path:
    if (INPUT_ROOT / "pyproject.toml").is_file():
        return INPUT_ROOT
    candidates = list(Path("/kaggle/input").rglob("pyproject.toml"))
    if len(candidates) != 1:
        raise FileNotFoundError(
            "Could not uniquely locate the private Interra source dataset; "
            f"candidates={candidates}"
        )
    return candidates[0].parent


def start_ollama() -> subprocess.Popen[bytes]:
    log = (WORK / "ollama.log").open("w", encoding="utf-8")
    server = subprocess.Popen(["ollama", "serve"], stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        probe = subprocess.run(
            ["curl", "-fsS", "http://127.0.0.1:11434/api/tags"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return server
        if server.poll() is not None:
            raise RuntimeError(f"Ollama exited during startup: {server.returncode}")
        time.sleep(1)
    raise RuntimeError("Ollama did not become ready within 60 seconds")


def main() -> None:
    shutil.copytree(source_root(), PROJECT, dirs_exist_ok=True)
    run([sys.executable, "-m", "venv", str(VENV)])
    python = venv_python()
    run([python, "-m", "pip", "install", "--upgrade", "pip"])
    run([python, "-m", "pip", "install", "-e", ".[fdb]"], cwd=PROJECT)

    run(["apt-get", "update"])
    run(["apt-get", "install", "-y", "zstd"])
    run(["bash", "-lc", "curl -fsSL https://ollama.com/install.sh | sh"])
    start_ollama()
    run(["ollama", "pull", "qwen3:8b"])
    run(["ollama", "run", "qwen3:8b", "Reply with only READY."])
    run(["nvidia-smi"])

    run([python, "scripts/fdb_v3.py", "bootstrap", "--download-data"], cwd=PROJECT)
    missing = read_kaggle_secrets()
    if not missing:
        run([python, "scripts/fdb_v3.py", "check"], cwd=PROJECT)
        if RUN_FULL_BENCHMARK:
            run([python, "scripts/fdb_v3.py", "all", "--force"], cwd=PROJECT)
    else:
        print("Benchmark deferred; add Kaggle Secrets: " + ", ".join(missing), flush=True)

    report = {
        "qwen_model": "qwen3:8b",
        "project": str(PROJECT),
        "venv": str(VENV),
        "livekit_ready": not missing,
        "missing_secret_names": missing,
        "full_benchmark_run": RUN_FULL_BENCHMARK,
        "next_command": "python scripts/fdb_v3.py all --force",
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
