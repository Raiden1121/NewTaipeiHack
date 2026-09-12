import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.geography import DistrictResolver  # noqa: E402
from transform.population_villages import transform_population_villages  # noqa: E402


def _row(village: str, code: str, *, missing_age: bool = False) -> dict[str, str]:
    row = {
        "statistic_yyymm": "11405",
        "district_code": code,
        "site_id": "新北市板橋區",
        "village": village,
        "people_total": "20",
    }
    for age in range(18, 36):
        row[f"people_age_{age:03d}_m"] = "1"
        row[f"people_age_{age:03d}_f"] = "2"
    if missing_age:
        row.pop("people_age_020_f")
    return row


class TestTransformPopulationVillages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_emits_one_village_row_with_youth_fields(self):
        result = transform_population_villages(
            [_row("甲里", "65000010001"), _row("乙里", "65000010002")],
            resolver=self.resolver,
        )

        self.assertEqual(len(result.records), 2)
        first = result.records[0]
        self.assertEqual(first["geo_level"], "village")
        self.assertEqual(first["village_code"], "65000010001")
        self.assertEqual(first["village_name"], "甲里")
        self.assertEqual(first["district_id"], "65000010")
        self.assertEqual(first["people_total"], 20)
        self.assertEqual(first["youth_18_35_female"], 36)
        self.assertEqual(first["youth_18_35_male"], 18)
        self.assertEqual(first["youth_18_35_total"], 54)
        self.assertEqual(first["period_start"], "2025-05-01")

    def test_missing_age_is_null_and_quality_warning_is_preserved(self):
        result = transform_population_villages(
            [_row("甲里", "65000010001", missing_age=True)],
            resolver=self.resolver,
        )

        self.assertEqual(result.records[0]["youth_18_35_female"], None)
        self.assertEqual(result.records[0]["youth_18_35_total"], None)
        self.assertIn("incomplete_youth_age_fields", result.quality["warnings"])
        self.assertEqual(result.quality["missing_value_count"], 1)


if __name__ == "__main__":
    unittest.main()
