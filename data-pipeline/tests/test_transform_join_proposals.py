import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.config import load_topic_rules  # noqa: E402
from transform.join_proposals import transform_join_proposals  # noqa: E402


class TestTransformJoinProposals(unittest.TestCase):
    def test_preserves_all_rows_and_marks_youth_proxy(self):
        result = transform_join_proposals(
            [
                {
                    "proposal_id": "p-1",
                    "title": "青年居住正義",
                    "content": "社宅",
                    "agency": "內政部",
                    "endorsement_count": "1,200",
                    "submitted_at": "1140102",
                },
                {
                    "proposal_id": "p-2",
                    "title": "一般公共設施議題",
                    "content": "一般內容",
                    "submitted_at": "1131201",
                },
            ],
            fetched_at="2026-09-10T00:00:00+00:00",
            rules=load_topic_rules(CONFIG_DIR / "youth_topic_rules.json"),
        )

        self.assertEqual(len(result.records), 2)
        first, second = result.records
        self.assertEqual(first["geo_level"], "national")
        self.assertIsNone(first["district_id"])
        self.assertEqual(first["period_start"], "2025-01-01")
        self.assertEqual(first["youth_eligibility"], "context_only")
        self.assertTrue(first["youth_topic_proxy"])
        self.assertEqual(first["endorsement_count"], 1200)
        self.assertEqual(first["raw_record"]["proposal_id"], "p-1")
        self.assertFalse(second["youth_topic_proxy"])


if __name__ == "__main__":
    unittest.main()
