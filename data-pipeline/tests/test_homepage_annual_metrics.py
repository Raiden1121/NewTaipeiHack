import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.annual_metrics import (  # noqa: E402
    calculate_annual_fertility,
    calculate_annual_population,
    calculate_budget_series,
)


class TestHomepageAnnualMetrics(unittest.TestCase):
    def test_population_uses_latest_month_and_excludes_109_from_output(self):
        rows = [
            {"metric_id": "people_total", "district_id": "d1", "district_name": "一區", "period_start": "2021-11-01", "period_end": "2021-11-30", "value": 100},
            {"metric_id": "people_total", "district_id": "d1", "district_name": "一區", "period_start": "2021-12-01", "period_end": "2021-12-31", "value": 110},
            {"metric_id": "youth_18_35_total", "district_id": "d1", "period_start": "2021-12-01", "period_end": "2021-12-31", "value": 22},
            {"metric_id": "people_total", "district_id": "d1", "period_start": "2020-12-01", "period_end": "2020-12-31", "value": 100},
            {"metric_id": "youth_18_35_total", "district_id": "d1", "period_start": "2020-12-01", "period_end": "2020-12-31", "value": 20},
        ]

        result = calculate_annual_population(rows, annual_years_roc=[110])

        self.assertEqual([item["year_roc"] for item in result["years"]], [110])
        self.assertEqual(result["years"][0]["city"]["people_total"], 110)
        self.assertEqual(result["years"][0]["city"]["yoy_percent"], 10)

    def test_fertility_uses_average_available_months_and_reports_coverage(self):
        births = [{"district_id": "d1", "period_start": "2021-01-01", "value": 12}]
        population = [
            {"metric_id": "youth_18_35_female", "district_id": "d1", "period_start": "2021-01-01", "value": 100},
            {"metric_id": "youth_18_35_female", "district_id": "d1", "period_start": "2021-02-01", "value": 200},
        ]

        result = calculate_annual_fertility(births, population, annual_years_roc=[110])
        city = result["years"][0]["city"]

        self.assertEqual(city["available_months"], 2)
        self.assertEqual(city["coverage_ratio"], 2 / 12)
        self.assertEqual(city["fertility_rate"], 80)
        self.assertEqual(city["quality_status"], "partial")

    def test_budget_does_not_mix_proposed_or_substitute_settlement_amount(self):
        budgets = [
            {"budget_year_roc": "110", "row_type": "total", "document_status": "legal_budget", "budget_amount": 100, "unit": "TWD_thousand"},
            {"budget_year_roc": "111", "row_type": "total", "document_status": "proposed_budget", "budget_amount": 999, "unit": "TWD_thousand"},
        ]
        settlements = [
            {"budget_year_roc": "110", "row_type": "total", "document_status": "final_settlement", "settlement_amount": 90, "realized_amount": None, "payable_amount": 1, "reserved_amount": 2, "surplus_amount": 3},
        ]

        result = calculate_budget_series(budgets, settlements, annual_years_roc=[110, 111])

        self.assertEqual(result["trend"][0]["legal_budget_amount"], 100)
        self.assertIsNone(result["trend"][0]["execution_rate"])
        self.assertEqual(result["trend"][0]["execution_failure"], "realized_amount_unparsed")
        self.assertIsNone(result["trend"][1]["legal_budget_amount"])
        self.assertEqual(result["trend"][1]["execution_failure"], "final_settlement_unavailable")

    def test_budget_execution_aligns_thousand_and_twd_units(self):
        result = calculate_budget_series(
            [
                {
                    "budget_year_roc": "113",
                    "row_type": "total",
                    "document_status": "legal_budget",
                    "budget_amount": 158650,
                    "unit": "TWD_thousand",
                }
            ],
            [
                {
                    "budget_year_roc": "113",
                    "row_type": "total",
                    "document_status": "final_settlement",
                    "realized_amount": 138627956,
                    "unit": "TWD",
                }
            ],
            annual_years_roc=[113],
        )

        row = result["trend"][0]
        self.assertAlmostEqual(row["execution_rate"], 138627956 / 158650000 * 100)
        self.assertEqual(row["execution_unit_conversion"], "legal_budget_thousand_to_twd")


if __name__ == "__main__":
    unittest.main()
