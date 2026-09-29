"""Summarize the official FDB-v3 reports without changing their scores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "artifacts" / "fdb_v3"


def load(name: str) -> dict[str, Any] | None:
    path = REPORT_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def main() -> None:
    reports = {
        "tool_call_evaluation": load("interra_elevenlabs_evaluation_report.json"),
        "pass_rate": load("interra_elevenlabs_pass_rate_report.json"),
        "latency": load("interra_elevenlabs_latency_report.json"),
    }
    if not any(reports.values()):
        raise SystemExit(
            "No FDB-v3 reports found. Run: python scripts/fdb_v3.py evaluate"
        )

    summary = {
        "benchmark": "Full-Duplex-Bench v3",
        "provider": "interra_elevenlabs",
        "source_reports": {
            key: value is not None for key, value in reports.items()
        },
        "official_report_data": reports,
        "note": (
            "This file only groups official evaluator output. Organizer reruns and "
            "their pinned LLM judge determine the scored submission result."
        ),
    }
    destination = REPORT_DIR / "verification-summary.json"
    destination.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
