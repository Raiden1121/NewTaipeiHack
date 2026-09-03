import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_PATH = PROJECT_DIR / "data-pipeline" / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.geography import DistrictResolver  # noqa: E402
from transform.life_events import transform_births, transform_marriages  # noqa: E402


class TestTransformLifeEvents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_births_include_mother_ages_18_to_35_and_total_sex_takes_precedence(self):
        records = [
            {"statistic_yyy": "114", "according": "發生日期", "site_id": "新北市板橋區", "mother_age": "18歲", "birth_sex": "男", "birth_count": "2"},
            {"statistic_yyy": "114", "according": "發生日期", "site_id": "新北市板橋區", "mother_age": "18歲", "birth_sex": "女", "birth_count": "3"},
            {"statistic_yyy": "114", "according": "發生日期", "site_id": "新北市板橋區", "mother_age": "18歲", "birth_sex": "總計", "birth_count": "6"},
            {"statistic_yyy": "114", "according": "發生日期", "site_id": "新北市板橋區", "mother_age": "35歲", "birth_sex": "合計", "birth_count": "4"},
            {"statistic_yyy": "114", "according": "發生日期", "site_id": "新北市板橋區", "mother_age": "17歲", "birth_sex": "總計", "birth_count": "999"},
            {"statistic_yyy": "114", "according": "發生日期", "site_id": "新北市板橋區", "mother_age": "36歲", "birth_sex": "總計", "birth_count": "100"},
        ]

        result = transform_births(records, resolver=self.resolver)

        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record["metric_id"], "births_mother_age_18_35")
        self.assertEqual(record["value"], 10)
        self.assertEqual(record["age_scope"], "exact_18_35")
        self.assertEqual(record["age_min"], 18)
        self.assertEqual(record["age_max"], 35)
        self.assertEqual(record["youth_eligibility"], "eligible")
        self.assertEqual(record["according"], ["發生日期"])
        self.assertEqual(record["raw_records"], records[:4])
        self.assertNotIn("17歲", [raw["mother_age"] for raw in record["raw_records"]])

    def test_marriages_aggregate_monthly_villages_to_annual_all_ages_context(self):
        records = [
            {"statistic_yyymm": "11401", "site_id": "板橋區", "village": "甲里", "marry_pair": "2"},
            {"statistic_yyymm": "11402", "site_id": "板橋區", "village": "甲里", "marry_pair": "3"},
            {"statistic_yyymm": "11402", "site_id": "板橋區", "village": "乙里", "marry_pair": "4"},
        ]

        result = transform_marriages(records, resolver=self.resolver)

        self.assertEqual(result.records[0]["value"], 9)
        self.assertEqual(result.records[0]["period_start"], "2025-01-01")
        self.assertEqual(result.records[0]["period_end"], "2025-12-31")
        self.assertEqual(result.records[0]["age_scope"], "all_ages")
        self.assertEqual(result.records[0]["youth_eligibility"], "context_only")
        self.assertNotIn("youth", result.records[0]["metric_id"])

    def test_duplicate_marriage_village_month_is_quarantined(self):
        raw = {"statistic_yyymm": "11401", "site_id": "板橋區", "village": "甲里", "marry_pair": "2"}

        result = transform_marriages([raw, dict(raw)], resolver=self.resolver)

        self.assertEqual(result.records[0]["value"], 2)
        self.assertEqual(result.quality["duplicate_count"], 1)
        self.assertEqual(result.quarantine[0]["reason"], "duplicate_record")


if __name__ == "__main__":
    unittest.main()
