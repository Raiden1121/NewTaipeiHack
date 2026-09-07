import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_PATH = PROJECT_DIR / "data-pipeline" / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.geography import DistrictResolver  # noqa: E402
from transform.mobility import transform_movement  # noqa: E402


class TestTransformMovement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_outputs_only_all_ages_context_metrics(self):
        raw = {
            "statistic_yyymm": "11405",
            "district_code": "65000010001",
            "site_id": "板橋區",
            "village": "甲里",
            "in_total_m": "10",
            "in_total_f": "5",
            "out_total_m": "4",
            "out_total_f": "3",
            "in_tp_m": "2",
        }

        result = transform_movement([raw], resolver=self.resolver)

        metrics = {row["metric_id"]: row for row in result.records}
        self.assertEqual(metrics["movement_in_total"]["value"], 15)
        self.assertEqual(metrics["movement_out_total"]["value"], 7)
        self.assertEqual(metrics["net_movement_total"]["value"], 8)
        self.assertEqual(metrics["in_tp_m"]["value"], 2)
        self.assertTrue(all(row["age_scope"] == "all_ages" for row in result.records))
        self.assertTrue(all(row["youth_eligibility"] == "context_only" for row in result.records))
        self.assertFalse(any("youth" in row["metric_id"] for row in result.records))

    def test_missing_operand_keeps_net_movement_null(self):
        raw = {
            "statistic_yyymm": "11405",
            "site_id": "板橋區",
            "village": "甲里",
            "in_total_m": "10",
            "in_total_f": "5",
            "out_total_m": "4",
            "out_total_f": None,
        }

        result = transform_movement([raw], resolver=self.resolver)

        metrics = {row["metric_id"]: row for row in result.records}
        self.assertIsNone(metrics["movement_out_total"]["value"])
        self.assertIsNone(metrics["net_movement_total"]["value"])
        self.assertIn("incomplete_movement_totals", result.quality["warnings"])
        self.assertGreaterEqual(result.quality["missing_value_count"], 1)

    def test_accepts_bom_prefixed_period_key_and_preserves_raw_record(self):
        raw = {
            "\ufeffstatistic_yyymm": "10701",
            "district_code": "65000010001",
            "site_id": "板橋區",
            "village": "甲里",
            "in_total_m": "10",
            "in_total_f": "5",
            "out_total_m": "4",
            "out_total_f": "3",
        }

        result = transform_movement([raw], resolver=self.resolver)

        self.assertEqual(result.quarantine, [])
        metrics = {row["metric_id"]: row for row in result.records}
        self.assertEqual(metrics["net_movement_total"]["period_start"], "2018-01-01")
        self.assertEqual(metrics["net_movement_total"]["raw_records"], [raw])
        self.assertNotIn("statistic_yyymm", metrics["net_movement_total"]["raw_records"][0])


if __name__ == "__main__":
    unittest.main()
