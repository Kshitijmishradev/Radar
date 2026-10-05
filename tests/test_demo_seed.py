import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ai_costs import AICostService
from app.domain import Repository
from scripts.seed_demo import main as seed_demo


class DemoSeedTests(unittest.TestCase):
    def test_seed_demo_resets_cloud_and_ai_recording_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "radar.db")
            with patch.dict(os.environ, {"DATABASE_PATH": database_path}):
                seed_demo()

            repository = Repository(database_path)
            self.assertEqual(len(repository.list_anomalies("demo-video")), 8)
            actions = repository.list_actions("demo-video")
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["status"], "PENDING_APPROVAL")
            overview = AICostService(repository).overview("demo-video")
            self.assertEqual(overview["request_count"], 5)
            self.assertEqual(len(overview["budgets"]), 2)
            self.assertEqual(overview["policy_summary"]["total_decisions"], 4)
