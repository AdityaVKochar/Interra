"""Kaggle worker setup sequencing and credential boundary."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import kaggle_setup


class KaggleSetupTests(unittest.TestCase):
    def test_installs_venv_package_before_creating_environment(self) -> None:
        commands: list[list[str]] = []
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(kaggle_setup, "PROJECT", root / "project"),
                patch.object(kaggle_setup, "VENV", root / "venv"),
                patch.object(kaggle_setup, "REPORT", root / "report.json"),
                patch.object(kaggle_setup, "source_root", return_value=root),
                patch.object(kaggle_setup.shutil, "copytree"),
                patch.object(kaggle_setup, "run", side_effect=lambda command, **_: commands.append(command)),
                patch.object(kaggle_setup, "start_ollama"),
                patch.object(kaggle_setup, "read_kaggle_secrets", return_value=["ELEVEN_API_KEY"]),
            ):
                kaggle_setup.main()

            install = next(i for i, command in enumerate(commands) if command[:3] == ["apt-get", "install", "-y"])
            create = next(i for i, command in enumerate(commands) if command[1:3] == ["-m", "venv"])
            self.assertLess(install, create)
            self.assertIn(
                f"python{kaggle_setup.sys.version_info.major}.{kaggle_setup.sys.version_info.minor}-venv",
                commands[install],
            )
            self.assertFalse(json.loads((root / "report.json").read_text())["livekit_ready"])
            self.assertFalse(any("fdb_v3.py" in " ".join(command) and "all" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
