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
from analytics.homepage import _budget_trend_points, _build_homepage_policy  # noqa: E402


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

    def test_budget_execution_uses_reported_ratio_for_prior_year_summary(self):
        result = calculate_budget_series(
            [
                {
                    "budget_year_roc": "114",
                    "row_type": "total",
                    "document_status": "legal_budget",
                    "budget_amount": 196153,
                    "unit": "TWD_thousand",
                }
            ],
            [
                {
                    "budget_year_roc": "114",
                    "row_type": "total",
                    "document_status": "final_settlement",
                    "budget_amount": 196653000,
                    "settlement_amount": 183283665,
                    "realized_amount": None,
                    "source_execution_ratio_percent": "93.20",
                    "unit": "TWD",
                    "raw_record": {
                        "source_record_type": "prior_year_settlement_summary"
                    },
                }
            ],
            annual_years_roc=[114],
        )

        row = result["trend"][0]
        self.assertEqual(row["execution_rate"], 93.2)
        self.assertIsNone(row["execution_failure"])
        self.assertEqual(row["execution_rate_source"], "source_execution_ratio_percent")
        self.assertEqual(
            row["execution_source_record_type"], "prior_year_settlement_summary"
        )
        self.assertIsNone(row["legal_budget_amount_for_execution"])
        self.assertIsNone(row["execution_denominator_unit"])
        self.assertIsNone(row["execution_unit_conversion"])

    def test_homepage_policy_selects_latest_budget_and_latest_usable_execution_separately(self):
        policy = _build_homepage_policy(
            [
                {
                    "year_roc": 114,
                    "legal_budget_amount": 196153,
                    "budget_yoy_percent": 23.63,
                    "execution_rate": 93.2,
                    "execution_failure": None,
                    "quality_status": "observed",
                },
                {
                    "year_roc": 115,
                    "legal_budget_amount": 213022,
                    "budget_yoy_percent": 8.6,
                    "execution_rate": None,
                    "execution_failure": "final_settlement_unavailable",
                    "quality_status": "observed",
                },
            ]
        )

        self.assertEqual(policy["currentBudget"], 213022)
        self.assertEqual(policy["budgetYoY"], 8.6)
        self.assertEqual(policy["executionRate"], 93.2)
        self.assertEqual(policy["executionRateYearRoc"], 114)
        self.assertIsNone(policy["executionFailure"])

    def test_budget_trend_runs_to_latest_budget_document_while_policy_scalars_stay_in_window(self):
        def total(year, status, amount, unit="TWD_thousand"):
            return {
                "budget_year_roc": str(year),
                "row_type": "total",
                "document_status": status,
                "budget_amount": amount,
                "unit": unit,
            }

        records = [
            total(112, "legal_budget", 149029),
            total(113, "legal_budget", 158650),
            total(114, "legal_budget", 196153),
            total(115, "proposed_budget", 999999),
            total(115, "legal_budget", 213022),
            total(116, "proposed_budget", 220101),
            total(114, "final_settlement", 196653000, unit="TWD"),
            {"budget_year_roc": "116", "row_type": "detail", "document_status": "proposed_budget", "budget_amount": 1},
        ]

        trend = _budget_trend_points(records, first_year_roc=110)

        # The source's first budget year is 112 (the bureau did not exist before),
        # so 110/111 are not emitted as missing points.
        self.assertEqual([row["year_roc"] for row in trend], [112, 113, 114, 115, 116])
        self.assertEqual(
            [row["value_thousand"] for row in trend],
            [149029, 158650, 196153, 213022, 220101],
        )
        # A year's legal budget wins over its proposal; the proposal-only year stays a normal point.
        self.assertEqual(trend[3]["document_status"], "legal_budget")
        self.assertEqual(trend[4]["document_status"], "proposed_budget")
        self.assertEqual(trend[4]["quality_status"], "observed")
        self.assertIsNone(trend[0]["budget_yoy_percent"])
        self.assertAlmostEqual(trend[4]["budget_yoy_percent"], (220101 - 213022) / 213022 * 100)

        series = calculate_budget_series(records, records, annual_years_roc=[110, 111, 112, 113, 114])
        policy = _build_homepage_policy(series["trend"], trend)

        self.assertEqual(policy["budgetTrend"], trend)
        self.assertEqual(policy["currentBudget"], 196153)

    def test_budget_trend_keeps_gaps_after_the_first_published_year_and_respects_window_start(self):
        records = [
            {"budget_year_roc": "105", "row_type": "total", "document_status": "legal_budget", "budget_amount": 1, "unit": "TWD_thousand"},
            {"budget_year_roc": "112", "row_type": "total", "document_status": "legal_budget", "budget_amount": 100, "unit": "TWD_thousand"},
            {"budget_year_roc": "114", "row_type": "total", "document_status": "legal_budget", "budget_amount": 120, "unit": "TWD_thousand"},
        ]

        trend = _budget_trend_points(records, first_year_roc=110)

        self.assertEqual([row["year_roc"] for row in trend], [112, 113, 114])
        self.assertIsNone(trend[1]["value_thousand"])
        self.assertEqual(trend[1]["quality_status"], "unavailable")
        self.assertAlmostEqual(trend[2]["budget_yoy_percent"], 20.0)
        self.assertEqual(_budget_trend_points([], first_year_roc=110), [])


if __name__ == "__main__":
    unittest.main()
