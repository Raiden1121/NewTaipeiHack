import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.budget_allocation import calculate_budget_allocation  # noqa: E402


AMOUNTS = {
    "01": ("綜合規劃業務", 38_960_000, "經常門"),
    "02": ("職涯發展業務", 37_730_000, "經常門"),
    "03": ("創業資源業務", 70_979_000, "經常門"),
    "04": ("青年業務設施", 11_852_000, "資本門"),
}


def allocation_rows(codes=None):
    selected = tuple(codes or AMOUNTS)
    return [
        {
            "budget_year_roc": "116",
            "document_status": "proposed_budget",
            "row_type": "allocation",
            "metric_id": "budget_allocation_amount",
            "value": AMOUNTS[code][1],
            "unit": "TWD",
            "business_plan": "青年發展業務",
            "work_plan": AMOUNTS[code][0],
            "allocation_code": code,
            "allocation_name": AMOUNTS[code][0],
            "budget_section": AMOUNTS[code][2],
            "account_category": "設備及投資" if code == "04" else None,
            "source_pdf_sha256": "sha256:116",
        }
        for code in selected
    ]


def summary_row(amount=159_521):
    return {
        "budget_year_roc": "116",
        "document_status": "proposed_budget",
        "row_type": "detail",
        "metric_id": "budget_amount",
        "budget_amount": amount,
        "value": amount,
        "unit": "TWD_thousand",
        "business_plan": "青年發展業務",
        "work_plan": "青年發展業務",
    }


class TestBudgetAllocationAnalytics(unittest.TestCase):
    def test_calculates_roc_116_total_and_rounded_shares(self):
        result = calculate_budget_allocation(
            [*allocation_rows(), summary_row()], reference_year_roc=116
        )

        self.assertEqual(result["metric_id"], "youthBudgetAllocation")
        self.assertEqual(result["budget_year_roc"], 116)
        self.assertEqual(result["document_status"], "proposed_budget")
        self.assertEqual(result["total_amount"], 159_521_000)
        self.assertEqual(result["unit"], "TWD")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["source_datasets"], ["youth_budgets"])
        self.assertEqual(result["source_period"], ["116"])
        self.assertEqual(
            [(item["code"], item["name"], item["amount"], item["share_percent"])
             for item in result["items"]],
            [
                ("01", "綜合規劃業務", 38_960_000, 24.42),
                ("02", "職涯發展業務", 37_730_000, 23.65),
                ("03", "創業資源業務", 70_979_000, 44.50),
                ("04", "青年業務設施", 11_852_000, 7.43),
            ],
        )
        self.assertEqual(
            sum(item["share_percent"] for item in result["items"]), 100.0
        )

    def test_incomplete_allocations_are_partial_with_reason(self):
        result = calculate_budget_allocation(
            [*allocation_rows(("01", "02", "03")), summary_row()],
            reference_year_roc=116,
        )

        self.assertEqual(result["status"], "partial")
        self.assertIn("04", result["coverage"]["missing_codes"])
        self.assertIn("budget_allocation_rows_incomplete", result["blocking_reasons"])
        self.assertNotEqual(result["status"], "observed")

    def test_source_total_mismatch_is_not_observed(self):
        result = calculate_budget_allocation(
            [*allocation_rows(), summary_row(amount=159_520)],
            reference_year_roc=116,
        )

        self.assertEqual(result["status"], "partial")
        self.assertIn("budget_allocation_total_mismatch", result["blocking_reasons"])
        self.assertEqual(result["coverage"]["source_total_amount"], 159_520_000)
        self.assertEqual(result["coverage"]["calculated_total_amount"], 159_521_000)


if __name__ == "__main__":
    unittest.main()
