import json
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.join_proposals import (  # noqa: E402
    DATA_GOV_DATASET_URL,
    JOIN_OPENDATA_YEAR_URL,
    fetch_join_proposals,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {"Content-Type": "application/json"}

    def read(self, limit=None):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class TestJoinProposals(unittest.TestCase):
    def test_parses_canonical_and_chinese_resource_rows(self):
        payload = {
            "data": [
                {
                    "proposal_id": "p-1",
                    "title": "青年住宅",
                    "content": "提供社會住宅",
                    "endorsement_count": 12,
                    "submitted_at": "1140102",
                    "proposal_url": "https://join.gov.tw/p/p-1",
                },
                {
                    "提案編號": "p-2",
                    "提案主旨": "青年就業",
                    "提案內容": "增加實習機會",
                    "附議人數": "3",
                    "提案日期": "1131201",
                },
            ]
        }

        result = fetch_join_proposals(
            resource_urls=("https://example.test/resource.json",),
            open_url=lambda *_args, **_kwargs: FakeResponse(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
            ),
        )

        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0]["proposal_id"], "p-1")
        self.assertEqual(result.records[0]["year_roc"], "114")
        self.assertEqual(result.records[0]["endorsement_count"], 12)
        self.assertIsNone(result.records[1]["agency"])
        self.assertEqual(result.records[1]["source_payload"]["提案主旨"], "青年就業")

    def test_parses_live_open_data_field_names(self):
        payload = {
            "data": [
                {
                    "publishDate": "2024-01-14 00:01:18",
                    "網址": "https://join.gov.tw/idea/detail/live-1",
                    "標題": "青年租屋與學貸",
                    "提議內容": "改善青年租屋負擔與學貸問題",
                    "利益與影響": "減輕青年生活壓力",
                    "附議數量": "1,234",
                    "提送日期": "2024-01-14 00:01:23",
                }
            ]
        }

        result = fetch_join_proposals(
            resource_urls=("https://example.test/live.json",),
            open_url=lambda *_args, **_kwargs: FakeResponse(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
            ),
        )

        row = result.records[0]
        self.assertEqual(row["submitted_at"], "2024-01-14 00:01:23")
        self.assertEqual(row["year_roc"], "113")
        self.assertEqual(row["content"], "改善青年租屋負擔與學貸問題")
        self.assertEqual(row["interest_impact"], "減輕青年生活壓力")
        self.assertEqual(row["endorsement_count"], 1234)

    def test_fallback_listing_deduplicates_and_keeps_document_failures(self):
        pages = {
            "https://join.test/list": """
                <a href='/proposal/1'>第一案</a>
                <a href='/proposal/1'>第一案重複</a>
                <a href='/proposal/2'>第二案</a>
            """.encode("utf-8"),
            "https://join.test/proposal/1": """
                <h1>社會住宅</h1><div class='content'>提供青年社宅</div>
                <span data-field='endorsement_count'>8</span>
                <span data-field='submitted_at'>1140102</span>
            """.encode("utf-8"),
            "https://join.test/proposal/2": b"not found",
        }

        def open_url(url, **_kwargs):
            if url.endswith("/proposal/2"):
                raise OSError("detail unavailable")
            return FakeResponse(pages[url])

        result = fetch_join_proposals(
            resource_urls=(), listing_url="https://join.test/list", open_url=open_url
        )

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["proposal_id"], "1")
        self.assertEqual(result.metadata["discovered_count"], 2)
        self.assertEqual(len(result.metadata["failures"]), 1)

    def test_falls_back_past_empty_sentinel_to_a_later_alias(self):
        # The platform writes 無 rather than omitting 提送日期, which must not
        # shadow publishDate and leave the proposal without a year.
        payload = [
            {
                "publishDate": "2025-03-04 09:15:00",
                "標題": "青年政策",
                "提議內容": "內容",
                "提送日期": "無",
                "附議數量": "0",
            }
        ]

        result = fetch_join_proposals(
            resource_urls=("https://example.test/live.json",),
            open_url=lambda *_args, **_kwargs: FakeResponse(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
            ),
        )

        row = result.records[0]
        self.assertEqual(row["submitted_at"], "2025-03-04 09:15:00")
        self.assertEqual(row["year_roc"], "114")

    def test_requests_recent_year_resources_before_catalogued_ones(self):
        requested = []

        def open_url(url, **_kwargs):
            requested.append(url)
            if url == DATA_GOV_DATASET_URL:
                return FakeResponse(
                    "<a href='https://join.gov.tw/toOpenData/v2/ey/idea?year=2024'>JSON</a>".encode(
                        "utf-8"
                    )
                )
            year = url.rsplit("=", 1)[-1]
            return FakeResponse(
                json.dumps(
                    [
                        {
                            "publishDate": f"{year}-05-05 00:00:00",
                            "標題": f"{year} 提案",
                            "提議內容": "內容",
                        }
                    ],
                    ensure_ascii=False,
                ).encode("utf-8")
            )

        result = fetch_join_proposals(years=[2026, 2025], open_url=open_url)

        resource_requests = [url for url in requested if url != DATA_GOV_DATASET_URL]
        self.assertEqual(
            resource_requests[:2],
            [
                JOIN_OPENDATA_YEAR_URL.format(year=2026),
                JOIN_OPENDATA_YEAR_URL.format(year=2025),
            ],
        )
        # The catalogued 2024 resource is still fetched as a backstop.
        self.assertIn(JOIN_OPENDATA_YEAR_URL.format(year=2024), resource_requests)
        self.assertEqual(
            sorted(row["year_roc"] for row in result.records), ["113", "114", "115"]
        )

    def test_single_year_resource_failure_does_not_stop_the_rest(self):
        def open_url(url, **_kwargs):
            if url == DATA_GOV_DATASET_URL:
                return FakeResponse(b"<html></html>")
            if url.endswith("year=2026"):
                raise OSError("resource unavailable")
            return FakeResponse(
                json.dumps(
                    [{"publishDate": "2025-05-05 00:00:00", "標題": "提案", "提議內容": "內容"}],
                    ensure_ascii=False,
                ).encode("utf-8")
            )

        result = fetch_join_proposals(years=[2026, 2025], open_url=open_url)

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["year_roc"], "114")
        self.assertEqual(
            [failure["url"] for failure in result.metadata["failures"]],
            [JOIN_OPENDATA_YEAR_URL.format(year=2026)],
        )


if __name__ == "__main__":
    unittest.main()
