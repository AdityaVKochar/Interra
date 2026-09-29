"""Build a self-contained Kaggle worker from tracked runtime files."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def package(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "archive", "--format=zip", "HEAD", "src", "scripts", "pyproject.toml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    payload = base64.b64encode(archive).decode("ascii")
    source = (ROOT / "scripts" / "kaggle_setup.py").read_text(encoding="utf-8")
    source = source.replace("RUN_FULL_BENCHMARK = False", "RUN_FULL_BENCHMARK = True", 1)
    source = source.replace('EMBEDDED_SOURCE_B64 = ""', f'EMBEDDED_SOURCE_B64 = "{payload}"', 1)
    if "RUN_FULL_BENCHMARK = True" not in source or f'EMBEDDED_SOURCE_B64 = "{payload}"' not in source:
        raise RuntimeError("Kaggle setup source has changed; packaging substitutions failed")
    (destination / "interra_setup.py").write_text(source, encoding="utf-8")
    metadata = json.loads((ROOT / "kaggle" / "kernel-metadata.json").read_text(encoding="utf-8"))
    metadata["code_file"] = "interra_setup.py"
    (destination / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return destination


if __name__ == "__main__":
    package(Path(sys.argv[1]))
