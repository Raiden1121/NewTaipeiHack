import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_PATH = PROJECT_DIR / "data-pipeline" / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.geography import DistrictResolver  # noqa: E402
from transform.population import transform_population  # noqa: E402


class TestTransformPopulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_includes_18_and_35_but_excludes_17_and_36(self):
        raw = {
            "statistic_yyymm": "11405",
            "district_code": "65000010001",
            "site_id": "新北市板橋區",
            "village": "留侯里",
            "people_total": "1,000",
        }
        for age in range(18, 36):
            raw[f"people_age_{age:03d}_m"] = "0"
            raw[f"people_age_{age:03d}_f"] = "0"
        raw.update(
            {
                "people_age_017_m": "100",
                "people_age_018_m": "2",
                "people_age_035_f": "3",
                "people_age_036_f": "100",
            }
        )

        result = transform_population([raw], resolver=self.resolver)

        metrics = {row["metric_id"]: row for row in result.records}
        self.assertEqual(metrics["youth_18_35_total"]["value"], 5)
        self.assertEqual(metrics["youth_18_35_male"]["value"], 2)
        self.assertEqual(metrics["youth_18_35_female"]["value"], 3)
        self.assertEqual(metrics["youth_18_35_total"]["age_scope"], "derived_18_35")
        self.assertEqual(metrics["people_total"]["value"], 1000)
        self.assertEqual(metrics["people_total"]["age_scope"], "all_ages")
        self.assertEqual(metrics["people_total"]["period_start"], "2025-05-01")
        self.assertEqual(metrics["people_total"]["period_end"], "2025-05-31")
        self.assertEqual(metrics["people_total"]["raw_records"], [raw])

    def test_aggregates_villages_by_district_and_month(self):
        rows = []
        for village, total, youth in (("甲里", "10", "2"), ("乙里", "20", "3")):
            row = {
                "statistic_yyymm": "11405",
                "district_code": f"65000010{len(rows) + 1:03d}",
                "site_id": "板橋區",
                "village": village,
                "people_total": total,
            }
            for age in range(18, 36):
                row[f"people_age_{age:03d}_m"] = youth if age == 18 else "0"
                row[f"people_age_{age:03d}_f"] = "0"
            rows.append(row)

        result = transform_population(rows, resolver=self.resolver)

        metrics = {row["metric_id"]: row for row in result.records}
        self.assertEqual(metrics["people_total"]["value"], 30)
        self.assertEqual(metrics["youth_18_35_total"]["value"], 5)
        self.assertEqual(len(metrics["people_total"]["source_record_ids"]), 2)
        self.assertEqual(result.quality["rows_in"], 2)
        self.assertEqual(result.quality["rows_out"], 4)

    def test_accepts_bom_prefixed_period_key_and_preserves_raw_record(self):
        raw = {
            "\ufeffstatistic_yyymm": "10701",
            "district_code": "65000010001",
            "site_id": "板橋區",
            "village": "甲里",
            "people_total": "10",
        }

        result = transform_population([raw], resolver=self.resolver)

        self.assertEqual(result.quarantine, [])
        metrics = {row["metric_id"]: row for row in result.records}
        self.assertEqual(metrics["people_total"]["period_start"], "2018-01-01")
        self.assertEqual(metrics["people_total"]["raw_records"], [raw])
        self.assertNotIn("statistic_yyymm", metrics["people_total"]["raw_records"][0])

    def test_unmapped_district_is_quarantined_without_guessing(self):
        raw = {"statistic_yyymm": "11405", "site_id": "未知區", "people_total": "1"}

        result = transform_population([raw], resolver=self.resolver)

        self.assertEqual(result.records, [])
        self.assertEqual(result.quality["unmapped_district_count"], 1)
        self.assertEqual(result.quarantine[0]["reason"], "unmapped_district")


if __name__ == "__main__":
    unittest.main()
