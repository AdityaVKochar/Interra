from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PackagingTests(unittest.TestCase):
    def test_required_repository_artifacts_exist(self):
        required = {
            "README.md": "python -m agent.demo",
            "Dockerfile": "python",
            "docs/ARCHITECTURE.md": "Fast Path",
            "docs/DEMO.md": "STALE_RESULT_DISCARDED",
            "docs/SUBMISSION_DECK.md": "Theme 05",
        }
        for relative, evidence in required.items():
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(evidence, text)

    def test_readme_states_live_evaluation_limitation_and_entrypoint(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("interra_submission:ParticipantAgent", readme)
        self.assertIn("No live-model task-completion score is claimed", readme)
        self.assertTrue((ROOT / "submission.yaml").is_file())
