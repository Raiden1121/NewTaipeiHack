import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import talent_demand  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def record(period="102年", occupation="專業人員", value="10"):
    return {
        "統計期": period,
        "職業別": occupation,
        "新登記求才人數（人次）": value,
        "新登記求才僱用人數（人次）": "2",
        "有效求才僱用人數（人次）": "5",
    }


def response(records, *, total=None):
    result = {
        "resource_id": "A17000000J-030281-nQF",
        "records": records,
    }
    if total is not None:
        result["total"] = total
    return {
        "success": True,
        "updateTime": "20260616T104021",
        "result": result,
    }


class TestTalentDemandCollector(unittest.TestCase):
    def test_fetches_all_pages_and_applies_period_filter(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            query = parse_qs(urlsplit(request.full_url).query)
            offset = query["offset"][0]
            if offset == "0":
                return FakeResponse(
                    response(
                        [
                            record("102年", "專業人員"),
                            record("102年", "事務支援人員"),
                        ]
                    )
                )
            return FakeResponse(response([record("102年", "服務及銷售工作人員")]))

        records = talent_demand.fetch_talent_demand(
            "102年",
            page_size=2,
            open_url=open_url,
        )

        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["統計期"], "102年")
        self.assertEqual(records[0]["新登記求才人數（人次）"], "10")
        self.assertEqual(
            [
                parse_qs(urlsplit(request.full_url).query)
                for request in requests
            ],
            [
                {
                    "filters": ['{"統計期": "102年"}'],
                    "limit": ["2"],
                    "offset": ["0"],
                },
                {
                    "filters": ['{"統計期": "102年"}'],
                    "limit": ["2"],
                    "offset": ["2"],
                },
            ],
        )

    def test_fetches_all_available_periods_when_period_is_omitted(self):
        def open_url(request, timeout):
            query = parse_qs(urlsplit(request.full_url).query)
            if query["offset"] == ["0"]:
                return FakeResponse(
                    response(
                        [record("102年"), record("103年")],
                        total=3,
                    )
                )
            return FakeResponse(response([record("104年")], total=3))

        records = talent_demand.fetch_talent_demand(
            page_size=2,
            open_url=open_url,
        )

        self.assertEqual([item["統計期"] for item in records], ["102年", "103年", "104年"])

    def test_rejects_invalid_json(self):
        class InvalidJsonResponse(FakeResponse):
            def read(self):
                return b"not-json"

        with self.assertRaises(talent_demand.TalentDemandCollectorError):
            talent_demand.fetch_talent_demand(
                open_url=lambda request, timeout: InvalidJsonResponse({}),
            )

    def test_rejects_records_missing_required_fields(self):
        with self.assertRaises(talent_demand.TalentDemandCollectorError):
            talent_demand.fetch_talent_demand(
                open_url=lambda request, timeout: FakeResponse(
                    response([{"統計期": "102年", "職業別": "專業人員"}])
                ),
            )

    def test_rejects_unsuccessful_api_response(self):
        with self.assertRaises(talent_demand.TalentDemandCollectorError):
            talent_demand.fetch_talent_demand(
                open_url=lambda request, timeout: FakeResponse(
                    {
                        "success": False,
                        "error": {"message": "resource unavailable"},
                    }
                ),
            )


if __name__ == "__main__":
    unittest.main()
