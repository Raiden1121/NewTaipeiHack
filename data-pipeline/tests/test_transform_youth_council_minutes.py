import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.config import load_topic_rules  # noqa: E402
from transform.youth_council_minutes import transform_youth_council_minutes  # noqa: E402


class TestTransformYouthCouncilMinutes(unittest.TestCase):
    def test_extracts_discussed_resolved_and_escalated_item(self):
        result = transform_youth_council_minutes(
            [
                {
                    "meeting_id": "meeting-1",
                    "meeting_name": "青年諮詢會",
                    "meeting_date": "1140102",
                    "term": "第六屆",
                    "year_roc": "114",
                    "page_texts": [
                        "提案事項\n一、社宅與居住正義\n說明：增加供給。\n"
                        "決議事項\n本案提請市議會審議。"
                    ],
                    "source_pdf_sha256": "sha256:abc",
                }
            ],
            rules=load_topic_rules(CONFIG_DIR / "youth_topic_rules.json"),
        )

        self.assertEqual(len(result.records), 1)
        row = result.records[0]
        self.assertEqual(row["geo_level"], "organization")
        self.assertTrue(row["discussed"])
        self.assertTrue(row["resolved"])
        self.assertTrue(row["escalated"])
        self.assertEqual(row["section_type"], "resolved")
        self.assertEqual(row["source_page_start"], 1)
        self.assertEqual(row["topic_text"], "社宅與居住正義")
        self.assertIn("增加供給", row["discussion_text"])
        self.assertIn("提請市議會", row["resolution_text"])

    def test_marks_missing_resolution_for_manual_review(self):
        result = transform_youth_council_minutes(
            [
                {
                    "meeting_id": "meeting-2",
                    "meeting_name": "青年工作坊",
                    "meeting_date": "1140202",
                    "term": "第六屆",
                    "year_roc": "114",
                    "page_texts": ["討論事項\n一、青年創業支持"],
                }
            ],
            rules=load_topic_rules(CONFIG_DIR / "youth_topic_rules.json"),
        )

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["parse_status"], "partial")
        self.assertTrue(result.records[0]["manual_review_required"])


if __name__ == "__main__":
    unittest.main()
