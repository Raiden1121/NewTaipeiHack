from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.policy_support import (  # noqa: E402
    calculate_population_trend,
    calculate_wage_trend,
    write_policy_support_data,
)


class TestPolicySupportAnalytics(unittest.TestCase):
    def test_wage_trend_uses_25_29_average_and_does_not_bridge_missing_year(self):
        records = [
            self._wage(110, 50.0, "平均數"),
            self._wage(110, 45.0, "中位數"),
            self._wage(111, 55.0, "平均數"),
            self._wage(112, 48.0, "平均數", age_group="30-39歲"),
            self._wage(113, 60.0, "平均數"),
        ]

        rows = calculate_wage_trend(records, annual_years_roc=range(110, 114))

        self.assertEqual([row["year_roc"] for row in rows], [110, 111, 112, 113])
        self.assertEqual(rows[0]["wage"], 50.0)
        self.assertIsNone(rows[0]["yoy"])
        self.assertEqual(rows[1]["wage"], 55.0)
        self.assertAlmostEqual(rows[1]["yoy"], 10.0)
        self.assertIsNone(rows[2]["wage"])
        self.assertIsNone(rows[2]["yoy"])
        self.assertEqual(rows[3]["wage"], 60.0)
        self.assertIsNone(rows[3]["yoy"])

    def test_population_trend_uses_july_and_previous_youth_population_denominator(self):
        records = [
            self._population("2022-07-01", "d1", 100),
            self._population("2022-07-01", "d2", 200),
            self._population("2022-08-01", "d1", 999),
            self._population("2023-07-01", "d1", 150),
            self._population("2023-07-01", "d2", 250),
            self._population("2024-07-01", "d1", 160),
            self._population("2024-07-01", "d2", 260),
        ]

        rows = calculate_population_trend(
            records,
            annual_years_roc=range(111, 114),
            expected_district_ids=("d1", "d2"),
        )

        self.assertEqual([row["year_roc"] for row in rows], [111, 112, 113])
        self.assertEqual(rows[0]["population"], 300)
        self.assertIsNone(rows[0]["yoy"])
        self.assertEqual(rows[1]["population"], 400)
        self.assertAlmostEqual(rows[1]["yoy"], (400 - 300) / 300 * 100, places=2)
        self.assertEqual(rows[2]["population"], 420)
        self.assertAlmostEqual(rows[2]["yoy"], 5.0, places=2)

    def test_population_missing_district_keeps_city_value_null(self):
        records = [
            self._population("2022-07-01", "d1", 100),
            self._population("2023-07-01", "d1", 150),
            self._population("2023-07-01", "d2", 250),
        ]

        rows = calculate_population_trend(
            records,
            annual_years_roc=range(111, 113),
            expected_district_ids=("d1", "d2"),
        )

        self.assertIsNone(rows[0]["population"])
        self.assertIsNone(rows[0]["yoy"])
        self.assertEqual(rows[1]["population"], 400)
        self.assertIsNone(rows[1]["yoy"])

    def test_public_writer_excludes_private_quality_and_raw_fields(self):
        result = {
            "metric_id": "policy_support",
            "status": "partial",
            "policyOutcomes": {"wageTrend": [], "populationTrend": []},
            "_quality": {"raw_record": "must not be published", "coverage": {}},
        }
        with tempfile.TemporaryDirectory() as tempdir:
            output_path, quality_path = write_policy_support_data(result, output_dir=tempdir)
            public = json.loads(output_path.read_text(encoding="utf-8"))
            quality = json.loads(quality_path.read_text(encoding="utf-8"))

        self.assertNotIn("_quality", public)
        self.assertNotIn("raw_record", quality)
        self.assertEqual(public["metric_id"], "policy_support")

    @staticmethod
    def _wage(year_roc: int, value: float, method: str, *, age_group: str = "25-29歲"):
        return {
            "period_start": f"{year_roc + 1911}-01-01",
            "county_name": "新北市",
            "official_age_group": age_group,
            "statistic_method": method,
            "value": value,
        }

    @staticmethod
    def _population(period_start: str, district_id: str, value: int):
        return {
            "period_start": period_start,
            "district_id": district_id,
            "metric_id": "youth_18_35_total",
            "value": value,
        }


if __name__ == "__main__":
    unittest.main()
