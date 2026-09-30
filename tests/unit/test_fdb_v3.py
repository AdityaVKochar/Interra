"""The full Kaggle run must stop if the official recorder hears silence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import fdb_v3


class FdbSpeechGateTests(unittest.TestCase):
    def test_readiness_requires_livekit_without_elevenlabs(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mock_apis.py").write_text("", encoding="utf-8")
            with (
                patch.dict(os.environ, {
                    "LIVEKIT_URL": "wss://example.invalid",
                    "LIVEKIT_API_KEY": "test-key",
                    "LIVEKIT_API_SECRET": "test-secret",
                }, clear=True),
                patch.object(fdb_v3.shutil, "which", return_value="ffmpeg"),
            ):
                fdb_v3.check(root, require_data=False)

    def _exercise(self, transcript: str) -> list[str]:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "released"
            sample = data / ("example_" + "a" * 24)
            sample.mkdir(parents=True)
            (sample / "input.wav").write_bytes(b"RIFF")
            (sample / "metadata.json").write_text("{}", encoding="utf-8")
            commands: list[str] = []

            def official_runner(command: list[str], **_: object) -> None:
                commands.extend(command)
                smoke_root = Path(command[command.index("--root_dir") + 1])
                result = smoke_root / sample.name / "result_interra_elevenlabs.json"
                result.write_text(
                    json.dumps({"status": "completed", "transcript": transcript}),
                    encoding="utf-8",
                )

            with patch.object(fdb_v3, "data_root", return_value=data), patch.object(
                fdb_v3.subprocess, "run", side_effect=official_runner
            ):
                fdb_v3.smoke_benchmark(root)
            return commands

    def test_stops_before_full_run_when_output_is_silent(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "heard no agent reply"):
            self._exercise("")

    def test_uses_official_runner_and_accepts_recognized_speech(self) -> None:
        command = self._exercise("Okay.")
        self.assertIn("run_tool_benchmark_all_released.py", command)
        self.assertIn("--root_dir", command)
        self.assertIn("--force", command)


if __name__ == "__main__":
    unittest.main()
