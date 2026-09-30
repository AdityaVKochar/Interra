"""Install Interra and run the pinned FDB-v3 benchmark from a fresh checkout."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_environment(path: Path, environment: dict[str, str]) -> dict[str, str]:
    """Read simple dotenv assignments; existing shell credentials take precedence."""
    result = environment.copy()
    if not path.is_file():
        return result
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid environment assignment at line {line_number}")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"Unclosed environment quote at line {line_number}")
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        if value and not result.get(name):
            result[name] = value
    return result


def reproduction_commands(venv: Path, use_llm: bool) -> list[list[str]]:
    python = str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    evaluate = [python, "scripts/fdb_v3.py", "all", "--force"]
    if use_llm:
        evaluate.append("--use-llm")
    return [
        [sys.executable, "-m", "venv", str(venv)],
        [python, "-m", "pip", "install", "--upgrade", "pip"],
        [python, "-m", "pip", "install", "-r", "requirements.txt"],
        [python, "-m", "pip", "install", "-e", ".", "--no-deps"],
        [python, "scripts/fdb_v3.py", "bootstrap", "--download-data"],
        evaluate,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--venv", type=Path, default=ROOT / ".venv-fdb")
    parser.add_argument("--use-llm", action="store_true", help="Enable the optional semantic judge.")
    parser.add_argument("--seed", type=int, default=0, help="Python hash seed; hosted sampling remains nondeterministic.")
    args = parser.parse_args()
    environment = load_environment(args.env_file, dict(os.environ))
    required = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]
    if args.use_llm:
        required.append("OPENAI_API_KEY")
    missing = [name for name in required if not environment.get(name)]
    if missing:
        parser.error("Set these names in .env or the shell before installing: " + ", ".join(missing))
    if not 0 <= args.seed <= 4294967295:
        parser.error("--seed must be between 0 and 4294967295")
    absent = [name for name in ("git", "ffmpeg") if shutil.which(name) is None]
    if absent:
        parser.error("Install these prerequisites on PATH: " + ", ".join(absent))
    environment["PYTHONHASHSEED"] = str(args.seed)
    for command in reproduction_commands(args.venv.resolve(), args.use_llm):
        print("+", " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, env=environment, check=True)


if __name__ == "__main__":
    main()
