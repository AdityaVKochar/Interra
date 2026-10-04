"""The full Kaggle run must stop if the official recorder hears silence."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import tempfile
from tempfile import TemporaryDirectory
import unittest
import unittest.mock
from unittest.mock import patch

from scripts import fdb_v3


class FdbSpeechGateTests(unittest.TestCase):
    def test_failed_evaluator_cannot_reuse_old_report(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "interra_elevenlabs_evaluation_report.json"
            old.write_text('{"total_scenarios":100}', encoding="utf-8")
            with patch.object(fdb_v3, "REPORT_ROOT", root), patch.object(
                fdb_v3, "run", side_effect=subprocess.CalledProcessError(1, "evaluate")
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    fdb_v3.evaluate(root, False)
            self.assertEqual(json.loads(old.read_text())["total_scenarios"], 100)

    def test_fresh_report_survives_known_post_report_nonzero_exit(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            def runner(command, **_):
                output = Path(command[command.index("--output") + 1])
                output.write_text('{"total_scenarios":93}', encoding="utf-8")
                raise subprocess.CalledProcessError(1, command)
            with patch.object(fdb_v3, "REPORT_ROOT", root), patch.object(fdb_v3, "run", side_effect=runner):
                fdb_v3.evaluate(root, False)
            for filename in ("interra_elevenlabs_evaluation_report.json", "interra_elevenlabs_pass_rate_report.json"):
                self.assertEqual(json.loads((root / filename).read_text())["total_scenarios"], 93)

    def test_malformed_new_report_does_not_replace_existing_evidence(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "interra_elevenlabs_evaluation_report.json"
            old.write_text('{"total_scenarios":100}', encoding="utf-8")
            def runner(command, **_):
                Path(command[command.index("--output") + 1]).write_text('{}', encoding="utf-8")
            with patch.object(fdb_v3, "REPORT_ROOT", root), patch.object(fdb_v3, "run", side_effect=runner):
                with self.assertRaisesRegex(RuntimeError, "Invalid official"):
                    fdb_v3.evaluate(root, False)
            self.assertEqual(json.loads(old.read_text())["total_scenarios"], 100)

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


class SeedResultsTests(unittest.TestCase):
    def test_seeds_are_placed_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data, seed = root / "released", root / "seed"
            for name in ("kept", "rerun"):
                (data / name).mkdir(parents=True)
                (data / name / "input.wav").write_bytes(b"RIFF")
            (seed / "kept").mkdir(parents=True)
            (seed / "kept" / fdb_v3.RESULT_NAME).write_text('{"status": "completed"}')
            (seed / "seed-manifest.json").write_text(json.dumps({"rerun": ["rerun"]}))
            with patch.object(fdb_v3, "data_root", return_value=data), patch.object(
                fdb_v3, "REPORT_ROOT", root / "reports"
            ):
                report = fdb_v3.seed_results(root, seed)
            self.assertTrue((data / "kept" / fdb_v3.RESULT_NAME).is_file())
            self.assertFalse((data / "rerun" / fdb_v3.RESULT_NAME).exists())
            self.assertEqual(report["seeded_into_run"], ["kept"])
            saved = json.loads((root / "reports" / "seeded-results.json").read_text())
            self.assertEqual(saved["rerun"], ["rerun"])

    def test_seed_without_released_recording_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "released").mkdir()
            (root / "seed" / "unknown").mkdir(parents=True)
            (root / "seed" / "unknown" / fdb_v3.RESULT_NAME).write_text("{}")
            with patch.object(fdb_v3, "data_root", return_value=root / "released"), patch.object(
                fdb_v3, "REPORT_ROOT", root / "reports"
            ), self.assertRaises(RuntimeError):
                fdb_v3.seed_results(root, root / "seed")

    def test_seeded_run_never_forces_over_seeds(self) -> None:
        agent = unittest.mock.Mock()
        agent.poll.return_value = None
        with patch.dict(os.environ, {"INTERRA_FDB_SEED_RESULTS": "fdb-seed"}), patch.object(
            fdb_v3.subprocess, "Popen", return_value=agent
        ), patch.object(fdb_v3.time, "sleep"), patch.object(fdb_v3, "smoke_benchmark"), patch.object(
            fdb_v3, "seed_results"
        ) as seed, patch.object(fdb_v3, "benchmark") as benchmark, patch.object(fdb_v3, "evaluate"):
            fdb_v3.all_steps(Path("/v3"), force=True, use_llm=False)
        seed.assert_called_once_with(Path("/v3"), (fdb_v3.PROJECT_ROOT / "fdb-seed").resolve())
        benchmark.assert_called_once_with(Path("/v3"), False)


class RecorderRetryTests(unittest.TestCase):
    def test_only_crashed_recordings_are_rerun_and_logged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "released"
            statuses = {"ok_one": "completed", "crashed": "inference_failed"}
            for name, status in statuses.items():
                (data / name).mkdir(parents=True)
                (data / name / fdb_v3.RESULT_NAME).write_text(json.dumps({"status": status}))
                (data / name / fdb_v3.OUTPUT_NAME).write_bytes(b"RIFF")
            runs: list[list[str]] = []

            def runner(command, **_):
                runs.append(command)
                if len(runs) == 2:  # the retry re-creates only the deleted result
                    self.assertFalse((data / "crashed" / fdb_v3.RESULT_NAME).exists())
                    self.assertFalse((data / "crashed" / fdb_v3.OUTPUT_NAME).exists())
                    self.assertTrue((data / "ok_one" / fdb_v3.OUTPUT_NAME).exists())
                    (data / "crashed" / fdb_v3.RESULT_NAME).write_text('{"status": "completed"}')

            with patch.object(fdb_v3, "data_root", return_value=data), patch.object(
                fdb_v3, "run", side_effect=runner
            ), patch.object(fdb_v3, "REPORT_ROOT", root / "reports"):
                fdb_v3.benchmark(root, force=True, recorder_retries=2)
            self.assertEqual(len(runs), 2)
            self.assertIn("--force", runs[0])
            self.assertNotIn("--force", runs[1])
            log = json.loads((root / "reports" / "recorder-retries.json").read_text())
            self.assertEqual(log["retried"], [{"attempt": 1, "recording": "crashed"}])
            self.assertEqual(log["still_failed"], [])

    def test_retries_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "released" / "crashed").mkdir(parents=True)
            (root / "released" / "crashed" / fdb_v3.RESULT_NAME).write_text('{"status": "inference_error"}')
            with patch.object(fdb_v3, "data_root", return_value=root / "released"), patch.object(
                fdb_v3, "run"
            ) as runner, patch.object(fdb_v3, "REPORT_ROOT", root / "reports"):
                fdb_v3.benchmark(root, force=False, recorder_retries=0)
            runner.assert_called_once()
            log = json.loads((root / "reports" / "recorder-retries.json").read_text())
            self.assertEqual(log["still_failed"], ["crashed"])


if __name__ == "__main__":
    unittest.main()
