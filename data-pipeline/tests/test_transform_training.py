import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_PATH = PROJECT_DIR / "data-pipeline" / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.geography import DistrictResolver  # noqa: E402
from transform.training import (  # noqa: E402
    transform_talent_demand,
    transform_training_numbers,
    transform_vt_courses,
)


class TestTransformTraining(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_vt_courses_count_distinct_course_ids_not_source_quantity(self):
        records = [
            {"訓練縣市": "新北市", "訓練區域": "板橋區", "郵遞區號前三碼": "220", "課程編號": "1001", "課程名稱": "A", "數量": "2"},
            {"訓練縣市": "新北市", "訓練區域": "板橋區", "郵遞區號前三碼": "220", "課程編號": "1001", "課程名稱": "A", "數量": "3"},
            {"訓練縣市": "新北市", "訓練區域": "板橋區", "郵遞區號前三碼": "220", "課程編號": "1002", "課程名稱": "B", "數量": "4"},
        ]

        result = transform_vt_courses(records, resolver=self.resolver)

        self.assertEqual(result.records[0]["metric_id"], "distinct_course_count")
        self.assertEqual(result.records[0]["value"], 2)
        self.assertNotEqual(result.records[0]["value"], 9)
        self.assertEqual(result.records[0]["geo_level"], "district")

    def test_training_numbers_keep_county_grain_and_normalize_fields(self):
        raw = {
            "訓練單位名稱": "測試單位",
            "縣市別辦訓地": "新北市",
            "課程代碼": "T1",
            "課程名稱": "測試課程",
            "訓練時數": "30.5",
            "訓練人次": "20",
            "每人訓練費用": "5,000",
            "開訓日期": "2026/01/01",
            "結訓日期": "2026/02/01",
        }

        result = transform_training_numbers([raw])

        record = result.records[0]
        self.assertEqual(record["geo_level"], "county")
        self.assertIsNone(record["district_id"])
        self.assertEqual(record["training_hours"], 30.5)
        self.assertEqual(record["training_people"], 20)
        self.assertEqual(record["fee_per_person"], 5000)
        self.assertEqual(record["period_start"], "2026-01-01")
        self.assertEqual(record["period_end"], "2026-02-01")

    def test_talent_demand_remains_national_and_normalizes_year(self):
        raw = {
            "統計期": "102年",
            "職業別": "專業人員",
            "新登記求才人數（人次）": "10",
            "新登記求才僱用人數（人次）": "2",
            "有效求才僱用人數（人次）": "5",
        }

        result = transform_talent_demand([raw])

        record = result.records[0]
        self.assertEqual(record["geo_level"], "national")
        self.assertEqual(record["period_start"], "2013-01-01")
        self.assertEqual(record["new_demand_count"], 10)
        self.assertEqual(record["new_hired_count"], 2)
        self.assertEqual(record["valid_hired_count"], 5)
        self.assertEqual(record["youth_eligibility"], "context_only")

    def test_training_numbers_support_compact_source_dates(self):
        raw = {
            "縣市別辦訓地": "新北市",
            "課程代碼": "T2",
            "訓練時數": "8",
            "訓練人次": "10",
            "每人訓練費用": "0",
            "開訓日期": "20260823",
            "結訓日期": "20260824",
        }

        result = transform_training_numbers([raw])

        self.assertEqual(result.records[0]["period_start"], "2026-08-23")
        self.assertEqual(result.records[0]["period_end"], "2026-08-24")

    def test_malformed_nonempty_training_date_is_quarantined(self):
        raw = {
            "縣市別辦訓地": "新北市",
            "課程代碼": "T3",
            "訓練時數": "8",
            "訓練人次": "10",
            "每人訓練費用": "0",
            "開訓日期": "20261340",
            "結訓日期": "20260824",
        }

        result = transform_training_numbers([raw])

        self.assertEqual(result.records, [])
        self.assertEqual(result.quarantine[0]["reason"], "invalid_date")


if __name__ == "__main__":
    unittest.main()
