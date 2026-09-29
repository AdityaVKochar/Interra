import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.fdb_livekit import FdbConfig, load_benchmark_module


class FdbLiveKitTests(unittest.TestCase):
    def test_config_reports_missing_keys_and_benchmark(self):
        with patch.dict(os.environ, {}, clear=True):
            config = FdbConfig.from_env()
            missing = config.missing_requirements()
        self.assertIn("LIVEKIT_URL", missing)
        self.assertIn("ELEVEN_API_KEY", missing)
        self.assertTrue(any(item.startswith("INTERRA_FDB_V3_ROOT") for item in missing))

    def test_loads_official_backend_by_path_without_import_side_effects(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "latency_injector.py").write_text(
                "MARKER = 'sibling-loaded'\n", encoding="utf-8"
            )
            (root / "mock_apis.py").write_text(
                "from latency_injector import MARKER\n"
                "class MockAPIRegistry:\n"
                "    def __init__(self, latency_profile='instant'): self.profile = latency_profile\n"
                "    def call(self, name, **kwargs): return {'name': name, **kwargs}\n",
                encoding="utf-8",
            )
            module = load_benchmark_module(root)
            registry = module.MockAPIRegistry()
            self.assertEqual(module.MARKER, "sibling-loaded")
            self.assertEqual(registry.call("track_order", order_id="A1")["order_id"], "A1")


if __name__ == "__main__":
    unittest.main()
