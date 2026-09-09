import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.budget import transform_youth_budgets  # noqa: E402
from transform.pipeline import run_transform  # noqa: E402


def budget_rows():
    return [
        {
            "document_id": "youth_budgets:115:legal_budget:abc",
            "budget_year_roc": "115",
            "document_status": "legal_budget",
            "document_status_label": "法定預算",
            "row_type": "total",
            "business_plan": "新北市政府青年局合計",
            "work_plan": None,
            "budget_amount": "213,022",
            "ratio_percent": "100.00",
            "unit_label": "新臺幣千元",
            "table_title": "計畫及預算統計表",
            "source_page_number": 28,
            "source_document_url": "https://example.test/115",
            "source_pdf_sha256": "sha256:abc",
        },
        {
            "document_id": "youth_budgets:115:legal_budget:abc",
            "budget_year_roc": "115",
            "document_status": "legal_budget",
            "document_status_label": "法定預算",
            "row_type": "detail",
            "business_plan": "一般行政",
            "work_plan": "一般行政",
            "budget_amount": "56,819",
            "ratio_percent": "26.67",
            "unit_label": "新臺幣千元",
            "table_title": "計畫及預算統計表",
            "source_page_number": 28,
            "source_document_url": "https://example.test/115",
            "source_pdf_sha256": "sha256:abc",
        },
    ]


class TestTransformBudget(unittest.TestCase):
    def test_transforms_organization_budget_without_district_allocation(self):
        result = transform_youth_budgets(
            budget_rows(), fetched_at="2026-09-09T00:00:00+00:00"
        )

        total = result.records[0]
        self.assertEqual(total["dataset"], "youth_budgets")
        self.assertEqual(total["source"], "ntpc_youth_bureau_budget")
        self.assertEqual(total["organization_name"], "新北市青年局")
        self.assertEqual(total["geo_level"], "organization")
        self.assertIsNone(total["district_id"])
        self.assertIsNone(total["district_name"])
        self.assertEqual(total["value"], 213022)
        self.assertEqual(total["unit"], "TWD_thousand")
        self.assertEqual(total["period_start"], "2026-01-01")
        self.assertEqual(total["period_end"], "2026-12-31")
        self.assertEqual(total["period_type"], "year")
        self.assertEqual(total["youth_eligibility"], "context_only")
        self.assertEqual(total["budget_ratio_percent"], 100.0)
        self.assertEqual(total["raw_record"]["budget_amount"], "213,022")

    def test_quarantines_malformed_budget_rows_and_preserves_raw_record(self):
        malformed = budget_rows()[1] | {
            "document_status": "unknown",
            "budget_amount": "not-a-number",
            "business_plan": None,
            "unit_label": "元",
        }

        result = transform_youth_budgets([malformed])

        self.assertEqual(result.records, [])
        self.assertEqual(result.quality["rows_in"], 1)
        self.assertEqual(result.quality["rows_rejected"], 1)
        self.assertEqual(result.quarantine[0]["raw_record"], malformed)
        self.assertIn("invalid_value", result.quarantine[0]["reason"])

    def test_detail_row_requires_work_plan_and_supported_status(self):
        missing_work_plan = budget_rows()[1] | {"work_plan": None}
        result = transform_youth_budgets([missing_work_plan])

        self.assertEqual(result.quality["rows_rejected"], 1)
        self.assertIn("missing_work_plan", result.quarantine[0]["reason"])

    def test_pipeline_dispatches_youth_budget_mapping_envelope(self):
        result = run_transform(
            "youth_budgets",
            {"records": budget_rows(), "fetched_at": "2026-09-09T00:00:00+00:00"},
        )

        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[1]["dataset"], "youth_budgets")


if __name__ == "__main__":
    unittest.main()
