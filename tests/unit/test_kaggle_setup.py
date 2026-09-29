"""Kaggle worker setup sequencing and credential boundary."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from scripts import kaggle_setup


class KaggleSetupTests(unittest.TestCase):
    def test_extracts_explicit_source_archive(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "input"
            inputs.mkdir()
            with zipfile.ZipFile(inputs / "interra-source.zip", "w") as bundle:
                bundle.writestr("pyproject.toml", "[project]\nname='interra-runtime'\n")
                bundle.writestr("scripts/fdb_v3.py", "# setup entry point\n")
            with (
                patch.object(kaggle_setup, "INPUT_ROOT", inputs),
                patch.object(kaggle_setup, "WORK", root / "work"),
            ):
                source = kaggle_setup.source_root()
            self.assertTrue((source / "pyproject.toml").is_file())
            self.assertTrue((source / "scripts" / "fdb_v3.py").is_file())

    def test_rejects_archive_path_traversal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "input"
            inputs.mkdir()
            with zipfile.ZipFile(inputs / "interra-source.zip", "w") as bundle:
                bundle.writestr("../escape.txt", "unsafe")
            with (
                patch.object(kaggle_setup, "INPUT_ROOT", inputs),
                patch.object(kaggle_setup, "WORK", root / "work"),
            ):
                with self.assertRaises(ValueError):
                    kaggle_setup.source_root()
            self.assertFalse((root / "escape.txt").exists())

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
