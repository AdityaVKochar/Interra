import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.reproduce import load_environment, reproduction_commands


class ReproduceTests(unittest.TestCase):
    def test_pipeline_installs_package_before_bootstrap_and_scored_run(self):
        commands = reproduction_commands(Path("example-venv"), True)
        self.assertIn("requirements.txt", commands[2])
        self.assertIn("--no-deps", commands[3])
        self.assertEqual(commands[4][-2:], ["bootstrap", "--download-data"])
        self.assertEqual(commands[5][-3:], ["all", "--force", "--use-llm"])

    def test_env_supports_quotes_and_preserves_existing_credentials(self):
        with TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text('export LIVEKIT_URL="wss://example.invalid"\n'
                           'LIVEKIT_API_KEY=file-value\nEMPTY=\nCOUNT=2 # comment\n', encoding="utf-8")
            result = load_environment(env, {"LIVEKIT_API_KEY": "shell-value"})
            self.assertEqual(result["LIVEKIT_API_KEY"], "shell-value")
            self.assertEqual(result["LIVEKIT_URL"], "wss://example.invalid")
            self.assertEqual(result["COUNT"], "2")
            self.assertNotIn("EMPTY", result)

    def test_bad_env_fails_without_exposing_the_value(self):
        with TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("invalid name=sensitive-value\n", encoding="utf-8")
            with self.assertRaises(ValueError) as error:
                load_environment(env, {})
            self.assertNotIn("sensitive-value", str(error.exception))
