import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.youth_grants import (  # noqa: E402
    GrantDocument,
    _parse_grant_pages,
    _parse_listing_page,
)
from transform.geography import DistrictResolver  # noqa: E402
from transform.youth_grants import transform_youth_grants  # noqa: E402


class TestYouthGrants(unittest.TestCase):
    def test_listing_discovers_roc_year_documents(self):
        html = (
            '<a href="/detail/113">新北市政府113年度對民間團體補助經費明細表</a>'
            '<a href="/detail/114">新北市政府114年度對民間團體補助經費明細表</a>'
        )

        documents = _parse_listing_page(html, page_url="https://example.test/list")

        self.assertEqual([item.year_roc for item in documents], ["113", "114"])
        self.assertEqual(documents[0].detail_url, "https://example.test/detail/113")

    def test_pdf_text_rows_preserve_amount_and_recipient(self):
        pages = [
            """表4 單位：新臺幣千元
新北市政府113年度對民間團體補助經費明細表
工作計畫
青年發展業務
青年創業活動
新北市板橋區青年協會
新北市政府
青年局 25 無 V
"""
        ]

        rows = _parse_grant_pages(
            pages,
            document=GrantDocument("113", "grant", "https://example.test/detail"),
            source_pdf_sha256="sha256:" + "a" * 64,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount_twd_thousand"], "25")
        self.assertEqual(rows[0]["recipient_name"], "新北市板橋區青年協會")

    def test_transform_prefers_project_location_then_recipient_address(self):
        resolver = DistrictResolver(
            [
                {
                    "district_id": "65000010",
                    "district_name": "板橋區",
                    "aliases": [],
                },
                {
                    "district_id": "65000020",
                    "district_name": "三重區",
                    "aliases": [],
                },
            ]
        )
        result = transform_youth_grants(
            [
                {
                    "grant_id": "g1",
                    "year_roc": "113",
                    "recipient_name": "A",
                    "project_location": "新北市板橋區某處",
                    "recipient_address": "新北市三重區某處",
                    "amount_twd_thousand": "10",
                },
                {
                    "grant_id": "g2",
                    "year_roc": "113",
                    "recipient_name": "B",
                    "project_location": None,
                    "recipient_address": "新北市三重區某處",
                    "amount_twd_thousand": "5",
                },
            ],
            resolver=resolver,
        )

        self.assertEqual(result.quality["rows_out"], 2)
        self.assertEqual(result.records[0]["district_id"], "65000010")
        self.assertEqual(result.records[0]["geo_basis"], "project_location")
        self.assertEqual(result.records[1]["district_id"], "65000020")
        self.assertEqual(result.records[1]["geo_basis"], "recipient_address")


if __name__ == "__main__":
    unittest.main()
