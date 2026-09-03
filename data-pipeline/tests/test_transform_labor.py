import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_PATH = PROJECT_DIR / "data-pipeline" / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.geography import DistrictResolver  # noqa: E402
from transform.labor import transform_job_vacancies, transform_wages  # noqa: E402


class TestTransformLabor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_vacancy_preserves_snapshot_salary_bounds_and_truncation_warning(self):
        raw = {
            "district": "板橋區",
            "JOB_PERSON（雇用人數）": "2",
            "SALARYCD": "月薪",
            "NT_L": "面議",
            "NT_U": "40,000",
            "salary_type": "月薪",
            "salary_lower": None,
            "salary_upper": 40000,
            "salary_midpoint": None,
            "salary_estimate_type": "upper_bound",
            "CJOB_STOP_DATE": "額滿為止",
            "query_truncated": True,
            "snapshot_fetched_at": "2026-09-01T00:00:00+00:00",
        }

        result = transform_job_vacancies([raw], resolver=self.resolver)

        record = result.records[0]
        self.assertEqual(record["position_count"], 2)
        self.assertIsNone(record["closing_date"])
        self.assertIsNone(record["salary_lower"])
        self.assertEqual(record["salary_upper"], 40000)
        self.assertEqual(record["salary_estimate_type"], "upper_bound")
        self.assertEqual(record["snapshot_fetched_at"], raw["snapshot_fetched_at"])
        self.assertIn("query_truncated", record["quality_flags"])
        self.assertIn("query_truncated", result.quality["warnings"])
        self.assertEqual(record["raw_record"]["NT_L"], "面議")
        self.assertEqual(record["age_scope"], "not_age_specific")

    def test_vacancy_county_row_uses_county_geography(self):
        county_row = {
            "geo_scope": "county",
            "district": "",
            "query_zipno": "220",
            "JOB_PERSON": "1",
            "snapshot_fetched_at": "2026-09-01T00:00:00+00:00",
        }

        result = transform_job_vacancies([county_row], resolver=self.resolver)

        self.assertEqual(result.records[0]["geo_level"], "county")
        self.assertIsNone(result.records[0]["district_id"])
        self.assertIsNone(result.records[0]["district_name"])
        self.assertEqual(result.records[0]["county_name"], "新北市")

    def test_vacancy_propagates_collector_query_warnings_to_quality(self):
        raw = {
            "district": "中和區",
            "JOB_PERSON": "1",
            "query_filtered_row_count": 1,
            "query_warnings": ["cross_county_cityname_filtered"],
            "snapshot_fetched_at": "2026-09-02T00:00:00+00:00",
        }

        result = transform_job_vacancies([raw], resolver=self.resolver)

        self.assertIn(
            "cross_county_cityname_filtered",
            result.records[0]["quality_flags"],
        )
        self.assertIn(
            "cross_county_cityname_filtered",
            result.quality["warnings"],
        )

    def test_official_age_group_wage_is_proxy_not_exact_youth(self):
        raw = {
            "資料年度": "113年",
            "縣市別": "新北市",
            "統計方式": "平均數",
            "年齡別": "30-39歲",
            "薪資": 69.0,
            "單位": "萬元",
            "原始欄位": "平均數／30-39歲",
        }

        result = transform_wages([raw], fetched_at="2026-09-01T00:00:00+00:00")

        record = result.records[0]
        self.assertEqual(record["geo_level"], "county")
        self.assertIsNone(record["district_id"])
        self.assertEqual(record["period_start"], "2024-01-01")
        self.assertEqual(record["official_age_group"], "30-39歲")
        self.assertEqual(record["age_min"], 30)
        self.assertEqual(record["age_max"], 39)
        self.assertEqual(record["age_scope"], "official_age_group_proxy")
        self.assertEqual(record["youth_eligibility"], "proxy_only")
        self.assertNotEqual(record["metric_id"], "youth_18_35_wage")

    def test_invalid_closing_date_is_quarantined_without_aborting_batch(self):
        base = {
            "district": "板橋區",
            "JOB_PERSON": "1",
            "snapshot_fetched_at": "2026-09-01T00:00:00+00:00",
        }
        valid = dict(base, CJOB_STOP_DATE="1140521")
        malformed = dict(base, CJOB_STOP_DATE="1140230")

        result = transform_job_vacancies([valid, malformed], resolver=self.resolver)

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["closing_date"], "2025-05-21")
        self.assertEqual(result.quality["rows_rejected"], 1)
        self.assertIn("invalid_value", result.quarantine[0]["reason"])

    def test_missing_vacancy_snapshot_is_visible_in_quality(self):
        raw = {"district": "板橋區", "JOB_PERSON": "1"}

        result = transform_job_vacancies([raw], resolver=self.resolver)

        self.assertEqual(len(result.records), 1)
        self.assertIsNone(result.records[0]["period_start"])
        self.assertIn("missing_snapshot", result.records[0]["quality_flags"])
        self.assertIn("missing_snapshot", result.quality["warnings"])

    def test_unknown_wage_statistic_method_is_quarantined(self):
        valid = {
            "資料年度": "113年", "縣市別": "新北市", "統計方式": "平均數",
            "年齡別": "25-29歲", "薪資": 60, "單位": "萬元",
        }
        unknown = dict(valid, 統計方式="眾數")

        result = transform_wages([valid, unknown])

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["metric_id"], "official_wage_average")
        self.assertEqual(result.quality["rows_rejected"], 1)
        self.assertEqual(result.quarantine[0]["reason"], "unsupported_statistic_method")


if __name__ == "__main__":
    unittest.main()
