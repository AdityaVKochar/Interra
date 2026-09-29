from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PackagingTests(unittest.TestCase):
    def test_required_repository_artifacts_exist(self):
        required = {
            "README.md": "python scripts/fdb_v3.py all --force",
            "Dockerfile": "python",
            "docs/ARCHITECTURE.md": "Fast Path",
            "docs/DEMO.md": "STALE_RESULT_DISCARDED",
            "docs/SUBMISSION_DECK.md": "Theme 05",
            "docs/FDB_V3.md": "Full-Duplex-Bench v3",
        }
        for relative, evidence in required.items():
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(evidence, text)

    def test_readme_states_fdb_limitations_and_entrypoints(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("agent.fdb_livekit", readme)
        self.assertIn("does not substitute for an FDB-v3 run", readme)
        self.assertIn("interra_submission:ParticipantAgent", readme)
        self.assertTrue((ROOT / "submission.yaml").is_file())
