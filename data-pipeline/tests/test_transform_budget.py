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


def settlement_row():
    return {
        "document_id": "youth_budgets:113:final_settlement:abc",
        "budget_year_roc": "113",
        "document_status": "final_settlement",
        "document_status_label": "單位決算",
        "row_type": "total",
        "business_plan": "合計",
        "work_plan": None,
        "budget_amount": "161,758,908",
        "original_budget_amount": "161,758,908",
        "budget_adjustment_amount": "-",
        "realized_amount": "138,627,956",
        "payable_amount": "1,253,506",
        "reserved_amount": "11,794,731",
        "settlement_amount": "151,676,193",
        "surplus_amount": "-10,082,715",
        "source_execution_ratio_percent": "93.77",
        "unit_label": "新臺幣元",
        "table_title": "歲出機關別決算表",
        "source_page_number": 13,
        "source_pdf_sha256": "sha256:abc",
    }


def allocation_rows():
    return [
        {
            "document_id": "youth_budgets:116:proposed_budget:abc",
            "budget_year_roc": "116",
            "document_status": "proposed_budget",
            "document_status_label": "預算案",
            "row_type": "allocation",
            "business_plan": "青年發展業務",
            "work_plan": "綜合規劃業務",
            "allocation_code": "01",
            "allocation_name": "綜合規劃業務",
            "budget_section": "經常門",
            "account_category": None,
            "budget_amount": "38,960,000",
            "ratio_percent": None,
            "unit_label": "新臺幣元",
            "table_title": "歲出計畫說明提要與各項費用明細表",
            "source_page_number": 41,
            "source_document_url": "https://example.test/116",
            "source_row_text": "01綜合規劃業務 38,960,000市庫負擔38,960,000元",
            "source_pdf_sha256": "sha256:abc",
        }
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

    def test_transforms_final_settlement_with_source_amounts_and_twd_unit(self):
        result = transform_youth_budgets(
            [settlement_row()], fetched_at="2026-09-11T00:00:00+00:00"
        )

        row = result.records[0]
        self.assertEqual(row["document_status"], "final_settlement")
        self.assertEqual(row["metric_id"], "settlement_amount")
        self.assertEqual(row["value"], 151676193)
        self.assertEqual(row["unit"], "TWD")
        self.assertEqual(row["budget_amount"], 161758908)
        self.assertEqual(row["realized_amount"], 138627956)
        self.assertEqual(row["payable_amount"], 1253506)
        self.assertEqual(row["reserved_amount"], 11794731)
        self.assertEqual(row["surplus_amount"], -10082715)
        self.assertEqual(row["source_execution_ratio_percent"], 93.77)

    def test_transforms_budget_allocation_to_twd_and_preserves_identity(self):
        result = transform_youth_budgets(
            allocation_rows(), fetched_at="2026-09-12T00:00:00+00:00"
        )

        self.assertEqual(result.quality["rows_out"], 1)
        row = result.records[0]
        self.assertEqual(row["row_type"], "allocation")
        self.assertEqual(row["metric_id"], "budget_allocation_amount")
        self.assertEqual(row["value"], 38_960_000)
        self.assertEqual(row["unit"], "TWD")
        self.assertEqual(row["budget_amount"], 38_960_000)
        self.assertIsNone(row["budget_ratio_percent"])
        self.assertEqual(row["allocation_code"], "01")
        self.assertEqual(row["allocation_name"], "綜合規劃業務")
        self.assertEqual(row["budget_section"], "經常門")
        self.assertIsNone(row["account_category"])
        self.assertEqual(row["raw_record"]["unit_label"], "新臺幣元")

    def test_pipeline_dispatches_youth_budget_mapping_envelope(self):
        result = run_transform(
            "youth_budgets",
            {"records": budget_rows(), "fetched_at": "2026-09-09T00:00:00+00:00"},
        )

        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[1]["dataset"], "youth_budgets")


if __name__ == "__main__":
    unittest.main()
