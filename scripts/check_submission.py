"""Verify committed score evidence and presentation limits without hosted calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    results = ROOT / "docs/results"
    manifest = json.loads((results / "run-manifest.json").read_text(encoding="utf-8"))
    pass_report = json.loads((results / "interra_elevenlabs_pass_rate_report.json").read_text(encoding="utf-8"))
    tool_report = json.loads((results / "interra_elevenlabs_evaluation_report.json").read_text(encoding="utf-8"))
    if (manifest["recordings"], manifest["strict_passes"], manifest["turn_taken"]) != (
        pass_report["total_scenarios"], pass_report["passed"], tool_report["turn_taking"]["turn_taken"]
    ):
        raise SystemExit("Run manifest and official reports disagree.")
    archive_path = results / "best-run-evidence.zip"
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        raise SystemExit("Evidence archive hash mismatch.")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise SystemExit("Evidence archive is damaged.")
        if set(archive.namelist()) != set(manifest["archive_entries"]):
            raise SystemExit("Evidence archive entries disagree with manifest.")
        for name, expected in manifest["archive_entries"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise SystemExit(f"Evidence entry hash mismatch: {name}")
        recordings = [name for name in archive.namelist() if name.startswith("recordings/")]
        if len(recordings) != manifest["recordings"]:
            raise SystemExit("Recording evidence count mismatch.")
        if manifest["measured_source_sha256"] != manifest["archive_entries"]["measured-source.zip"]:
            raise SystemExit("Measured source hash mismatch.")
    with zipfile.ZipFile(ROOT / "docs/Interra_Theme05_submission.pptx") as deck:
        slides = [name for name in deck.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)]
        if not 1 <= len(slides) <= 8:
            raise SystemExit(f"Official guide permits at most eight slides; found {len(slides)}.")
        for name in slides:
            ElementTree.fromstring(deck.read(name))
    print(f"Evidence verified: {len(recordings)} recordings, {pass_report['passed']} strict passes, {len(slides)} slides.")
    print("Demo: https://cursor.com/artifacts/v/art-65efdeb4-9b6f-4416-839a-875b82833f5a")
    print("Final submission still requires consistent registered team details.")


if __name__ == "__main__":
    main()
