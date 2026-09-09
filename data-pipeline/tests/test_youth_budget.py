import hashlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors import youth_budget  # noqa: E402
from collectors.contracts import CollectedPayload  # noqa: E402


LIST_URL = "https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?module=youth0008&id=108"
PAGE_TEXT_115 = """
計畫及預算統計表
單位：新臺幣千元、%
業務計畫 工作計畫 本年度預算數 比率
新北市政府青年局合計 213,022 100.00
一般行政 一般行政 56,819 26.67
青年發展業務 青年發展業務 155,903 73.19
第一預備金 第一預備金 300 0.14
"""
PAGE_TEXT_116 = PAGE_TEXT_115.replace("213,022", "220,101").replace(
    "56,819", "60,280"
).replace("26.67", "27.39").replace("155,903", "159,521").replace("73.19", "72.47")
LISTING_HTML = """
<html><body>
  <div class="item">公告日期：114/09/30 更新日期：115/02/09
    <a href="/youth/ch/app/data/doc/115">新北市政府青年局主管115年度單位預算(法定預算)</a>
  </div>
  <div class="item">公告日期：115/09/01
    <a href="/youth/ch/app/data/doc/116">新北市政府青年局主管116年度單位預算（預算案）</a>
  </div>
</body></html>
"""
DETAIL_HTML = {
    "/youth/ch/app/data/doc/115": '<a href="/files/115-budget.pdf">下載 PDF</a>',
    "/youth/ch/app/data/doc/116": '<a href="/files/116-budget.pdf">預算文件 PDF</a>',
}
PDF_115 = b"%PDF-1.7\n115 budget"
PDF_116 = b"%PDF-1.7\n116 budget"


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False


def _fake_open_url(request, *, timeout):
    del timeout
    url = request.full_url
    if url == LIST_URL:
        return _FakeResponse(LISTING_HTML.encode("utf-8"))
    for path, html in DETAIL_HTML.items():
        if url.endswith(path):
            return _FakeResponse(html.encode("utf-8"))
    if url.endswith("/files/115-budget.pdf"):
        return _FakeResponse(PDF_115)
    if url.endswith("/files/116-budget.pdf"):
        return _FakeResponse(PDF_116)
    raise AssertionError(f"unexpected URL: {url}")


class TestYouthBudgetCollector(unittest.TestCase):
    def test_listing_parser_discovers_year_status_and_relative_detail_url(self):
        documents = youth_budget._parse_listing_page(LISTING_HTML, page_url=LIST_URL)

        self.assertEqual([document.budget_year_roc for document in documents], ["115", "116"])
        self.assertEqual(
            [document.document_status for document in documents],
            ["legal_budget", "proposed_budget"],
        )
        self.assertEqual(documents[0].detail_url, f"{LIST_URL.rsplit('/', 1)[0]}/doc/115")
        self.assertEqual(documents[0].published_date, "114/09/30")
        self.assertEqual(documents[0].updated_date, "115/02/09")

    def test_status_mapping_rejects_unknown_label(self):
        self.assertEqual(youth_budget._parse_document_status("預算案"), ("proposed_budget", "預算案"))
        self.assertEqual(youth_budget._parse_document_status("法定版"), ("legal_budget", "法定版"))
        self.assertEqual(youth_budget._parse_document_status("法定預算"), ("legal_budget", "法定預算"))
        with self.assertRaises(youth_budget.BudgetCollectorError):
            youth_budget._parse_document_status("執行報告")

    def test_target_table_extracts_total_and_three_detail_rows(self):
        document = youth_budget.BudgetDocument(
            budget_year_roc="115",
            document_status="legal_budget",
            document_status_label="法定預算",
            title="新北市政府青年局主管115年度單位預算(法定預算)",
            detail_url="https://example.test/detail/115",
            pdf_url="https://example.test/115.pdf",
            published_date=None,
            updated_date=None,
        )

        rows = youth_budget._extract_budget_table(PAGE_TEXT_115, document=document, page_number=28)

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["row_type"], "total")
        self.assertIsNone(rows[0]["work_plan"])
        self.assertEqual(rows[0]["budget_amount"], "213,022")
        self.assertEqual(rows[1]["business_plan"], "一般行政")
        self.assertEqual(rows[1]["work_plan"], "一般行政")
        self.assertEqual(rows[-1]["ratio_percent"], "0.14")
        self.assertEqual(rows[0]["source_page_number"], 28)

    def test_fetch_returns_both_versions_raw_rows_metadata_and_artifacts(self):
        with patch.object(
            youth_budget,
            "_extract_pdf_pages",
            side_effect=[[PAGE_TEXT_115], [PAGE_TEXT_116]],
        ):
            payload = youth_budget.fetch_youth_budgets(
                list_url=LIST_URL,
                open_url=_fake_open_url,
                years=("115", "116"),
            )

        self.assertIsInstance(payload, CollectedPayload)
        self.assertEqual(len(payload.records), 8)
        self.assertEqual(
            {record["budget_year_roc"] for record in payload.records}, {"115", "116"}
        )
        self.assertEqual(
            {record["document_status"] for record in payload.records},
            {"legal_budget", "proposed_budget"},
        )
        self.assertEqual(
            [record["budget_amount"] for record in payload.records[:4]],
            ["213,022", "56,819", "155,903", "300"],
        )
        self.assertEqual(len(payload.metadata["documents"]), 2)
        self.assertEqual(len(payload.artifacts), 2)
        self.assertTrue(payload.artifacts[0].filename.startswith("115_legal_budget_"))
        self.assertEqual(
            payload.artifacts[0].sha256,
            "sha256:" + hashlib.sha256(PDF_115).hexdigest(),
        )
        self.assertTrue(all(record["document_id"] for record in payload.records))

    def test_fetch_accepts_detail_url_that_returns_pdf_directly(self):
        html = '<a href="/direct.pdf">新北市政府青年局主管115年度單位預算(法定預算)</a>'

        def open_direct(request, *, timeout):
            del timeout
            if request.full_url == LIST_URL:
                return _FakeResponse(html.encode())
            if request.full_url.endswith("/direct.pdf"):
                return _FakeResponse(PDF_115)
            raise AssertionError(f"unexpected URL: {request.full_url}")

        with patch.object(youth_budget, "_extract_pdf_pages", return_value=[PAGE_TEXT_115]):
            payload = youth_budget.fetch_youth_budgets(
                list_url=LIST_URL,
                open_url=open_direct,
                years=("115",),
            )

        self.assertEqual(len(payload.records), 4)
        self.assertEqual(payload.metadata["documents"][0]["pdf_url"], "https://www.youth.ntpc.gov.tw/direct.pdf")

    def test_same_pdf_bytes_have_stable_hash_and_filename(self):
        document = youth_budget.BudgetDocument(
            budget_year_roc="115",
            document_status="legal_budget",
            document_status_label="法定預算",
            title="title",
            detail_url="https://example.test/detail/115",
            pdf_url="https://example.test/115.pdf",
            published_date=None,
            updated_date=None,
        )

        first = youth_budget._build_source_artifact(document, PDF_115)
        second = youth_budget._build_source_artifact(document, PDF_115)

        self.assertEqual(first.filename, second.filename)
        self.assertEqual(first.sha256, second.sha256)

    def test_invalid_pdf_bytes_are_rejected(self):
        html = '<a href="/detail">新北市政府青年局主管115年度單位預算(法定預算)</a>'

        def open_invalid(request, *, timeout):
            del timeout
            if request.full_url == LIST_URL:
                return _FakeResponse(html.encode())
            if request.full_url.endswith("/detail"):
                return _FakeResponse(b'<a href="/files/bad.pdf">PDF</a>')
            return _FakeResponse(b"not a pdf")

        with self.assertRaisesRegex(youth_budget.BudgetCollectorError, "PDF"):
            youth_budget.fetch_youth_budgets(
                list_url=LIST_URL,
                open_url=open_invalid,
                years=("115",),
            )

    def test_missing_target_table_header_duplicate_total_and_bad_number_are_rejected(self):
        document = youth_budget.BudgetDocument(
            budget_year_roc="115",
            document_status="legal_budget",
            document_status_label="法定預算",
            title="title",
            detail_url="https://example.test/detail/115",
            pdf_url="https://example.test/115.pdf",
            published_date=None,
            updated_date=None,
        )
        invalid_pages = (
            "業務計畫 工作計畫 本年度預算數 比率\n一般行政 一般行政 1 1.00",
            PAGE_TEXT_115.replace(
                "新北市政府青年局合計 213,022 100.00",
                "新北市政府青年局合計 213,022 100.00\n新北市政府青年局合計 1 0.01",
            ),
            PAGE_TEXT_115.replace("213,022", "bad"),
        )

        for page_text in invalid_pages:
            with self.subTest(page_text=page_text):
                with self.assertRaises(youth_budget.BudgetCollectorError):
                    youth_budget._extract_budget_table(page_text, document=document, page_number=1)


if __name__ == "__main__":
    unittest.main()
