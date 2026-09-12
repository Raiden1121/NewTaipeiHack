import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.fertility import (  # noqa: E402
    calculate_annual_fertility_metrics,
    calculate_fafi_scores,
)


class TestFertilityAnalytics(unittest.TestCase):
    def test_calculates_weighted_city_rate_and_keeps_missing_district_null(self):
        districts = [
            {"district_id": "d1", "district_name": "一區"},
            {"district_id": "d2", "district_name": "二區"},
            {"district_id": "d3", "district_name": "三區"},
        ]
        births = [
            {"district_id": "d1", "period_start": "2021-01-01", "value": 12},
            {"district_id": "d2", "period_start": "2021-01-01", "value": 6},
        ]
        population = [
            {"district_id": "d1", "metric_id": "youth_18_35_female", "period_start": "2021-01-01", "value": 100},
            {"district_id": "d1", "metric_id": "youth_18_35_female", "period_start": "2021-02-01", "value": 200},
            {"district_id": "d2", "metric_id": "youth_18_35_female", "period_start": "2021-01-01", "value": 100},
            {"district_id": "d2", "metric_id": "youth_18_35_female", "period_start": "2021-02-01", "value": 100},
            {"district_id": "d1", "metric_id": "people_total", "period_start": "2021-02-01", "value": 1000},
            {"district_id": "d1", "metric_id": "youth_18_35_total", "period_start": "2021-02-01", "value": 200},
            {"district_id": "d2", "metric_id": "people_total", "period_start": "2021-02-01", "value": 500},
            {"district_id": "d2", "metric_id": "youth_18_35_total", "period_start": "2021-02-01", "value": 100},
        ]

        result = calculate_annual_fertility_metrics(
            births,
            population,
            annual_years_roc=[110],
            districts=districts,
        )

        year = result["years"][0]
        self.assertEqual(year["citySummary"]["totalBirths"], 18)
        self.assertAlmostEqual(year["citySummary"]["fertilityRate"], 72.0)
        self.assertAlmostEqual(year["citySummary"]["youthRatio"], 20.0)
        self.assertEqual(year["citySummary"]["status"], "partial")
        self.assertEqual(len(year["districts"]), 3)
        self.assertEqual(year["districts"][0]["fertilityRate"], 80.0)
        self.assertIsNone(year["districts"][2]["fertilityRate"])
        self.assertIsNone(year["districts"][2]["totalBirths"])

    def test_fafi_uses_equal_components_and_preserves_missing_values(self):
        rows = [
            {"district_id": "d1", "daycareCoverage": 10, "score_housing": 20, "estimatedWage": 100},
            {"district_id": "d2", "daycareCoverage": 20, "score_housing": 50, "estimatedWage": 200},
            {"district_id": "d3", "daycareCoverage": 30, "score_housing": 80, "estimatedWage": 300},
            {"district_id": "d4", "daycareCoverage": None, "score_housing": 80, "estimatedWage": None},
        ]

        result = calculate_fafi_scores(rows)

        self.assertAlmostEqual(result["districts"]["d2"]["fafiScore"], 50.0)
        self.assertIsNone(result["districts"]["d4"]["fafiScore"])
        self.assertEqual(result["status"], "partial")
        self.assertIn("daycareCoverage", result["normalization"]["inputs"])


if __name__ == "__main__":
    unittest.main()
