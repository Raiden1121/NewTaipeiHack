import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.config import load_topic_rules, load_topic_weights  # noqa: E402
from analytics.io import load_curated_dataset  # noqa: E402
from analytics.youth_topic_weight import calculate_youth_topic_weights  # noqa: E402


class TestYouthTopicWeight(unittest.TestCase):
    def test_loads_22_topics_and_configured_weights(self):
        rules = load_topic_rules(CONFIG_DIR / "youth_topic_rules.json")
        weights = load_topic_weights(CONFIG_DIR / "youth_topic_weights.json")

        self.assertEqual(len(rules.topics), 22)
        self.assertIn("社宅", rules.by_label["社會住宅"].aliases)
        self.assertIn("教育部", rules.proxy_agencies)
        self.assertIn("青年", rules.proxy_keywords)
        self.assertEqual(
            (weights.w_join, weights.w_minutes, weights.w_resolved, weights.w_escalated),
            (1.0, 1.8, 1.2, 2.5),
        )

    def test_calculates_alias_deduplicated_counts_and_signal_weight(self):
        rules = load_topic_rules(CONFIG_DIR / "youth_topic_rules.json")
        weights = load_topic_weights(CONFIG_DIR / "youth_topic_weights.json")
        join_rows = [
            {
                "source_record_id": "join-1",
                "year_roc": "114",
                "youth_topic_proxy": True,
                "title": "社宅與居住正義",
                "content": "社會住宅",
                "endorsement_count": 10,
            },
            {
                "source_record_id": "join-2",
                "year_roc": "114",
                "youth_topic_proxy": True,
                "title": "社會住宅政策",
                "content": "",
                "endorsement_count": 2,
            },
            {
                "source_record_id": "join-3",
                "year_roc": "114",
                "youth_topic_proxy": True,
                "title": "青年創業資源",
                "content": "",
                "endorsement_count": 1,
            },
        ]
        minute_rows = [
            {
                "source_record_id": "minute-1",
                "year_roc": "114",
                "source_text": "提案事項：社會住宅與社宅。決議：提請市議會審議。",
                "discussed": True,
                "resolved": True,
                "escalated": True,
            },
            {
                "source_record_id": "minute-2",
                "year_roc": "114",
                "source_text": "討論青年創業支持",
                "discussed": True,
                "resolved": False,
                "escalated": False,
            },
        ]

        result = calculate_youth_topic_weights(
            join_rows, minute_rows, rules=rules, weights=weights
        )
        year = next(item for item in result["years"] if item["year_roc"] == 114)
        housing = next(item for item in year["topics"] if item["label"] == "社會住宅")
        startup = next(item for item in year["topics"] if item["label"] == "青年創業")

        self.assertEqual(housing["join_mentions"], 2)
        self.assertEqual(housing["minutes_mentions"], 1)
        self.assertTrue(housing["escalated"])
        self.assertEqual(housing["weight"], 5)
        self.assertEqual(housing["signal"], "escalated")
        self.assertGreaterEqual(startup["weight"], 3)
        self.assertEqual(len(year["topics"]), 22)

    def test_load_curated_dataset_uses_dataset_index(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            curated = root / "curated" / "join_proposals" / "all.json"
            curated.parent.mkdir(parents=True)
            curated.write_text(json.dumps({"records": [{"id": 1}]}), encoding="utf-8")
            index = root / "quality" / "dataset_index.json"
            index.parent.mkdir(parents=True)
            index.write_text(
                json.dumps(
                    {
                        "datasets": {
                            "join_proposals": [
                                {"output_key": "all", "path": "curated/join_proposals/all.json"}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(load_curated_dataset("join_proposals", output_dir=root), [{"id": 1}])
            with self.assertRaises(ValueError):
                load_curated_dataset("youth_council_minutes", output_dir=root)

    def test_keeps_available_year_when_join_rows_are_not_youth_proxy(self):
        rules = load_topic_rules(CONFIG_DIR / "youth_topic_rules.json")
        weights = load_topic_weights(CONFIG_DIR / "youth_topic_weights.json")
        result = calculate_youth_topic_weights(
            [
                {
                    "source_record_id": "non-youth-1",
                    "year_roc": "113",
                    "youth_topic_proxy": False,
                    "title": "一般公共設施",
                    "content": "",
                }
            ],
            [],
            rules=rules,
            weights=weights,
        )

        self.assertEqual([year["year_roc"] for year in result["years"]], [113])
        self.assertEqual(len(result["years"][0]["topics"]), 22)


if __name__ == "__main__":
    unittest.main()
