import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors.population_collector import (  # noqa: E402
    PopulationCollectorError,
    fetch_population,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def success_page(total_page, records):
    return {
        "responseCode": "OD-0101-S",
        "responseMessage": "處理完成",
        "totalPage": str(total_page),
        "responseData": records,
    }


def fake_open_url(responses, requests=None):
    def open_url(request, timeout):
        if requests is not None:
            requests.append(request)

        page = parse_qs(urlparse(request.full_url).query)["PAGE"][0]
        return FakeResponse(responses[int(page)])

    return open_url


class TestFetchPopulation(unittest.TestCase):
    def test_merges_all_pages_for_new_taipei(self):
        responses = {
            1: success_page(
                total_page=2,
                records=[{"site_id": "新北市板橋區", "village": "留侯里"}],
            ),
            2: success_page(
                total_page=2,
                records=[{"site_id": "新北市板橋區", "village": "流芳里"}],
            ),
        }

        records = fetch_population("11507", open_url=fake_open_url(responses))

        self.assertEqual(
            records,
            [
                {"site_id": "新北市板橋區", "village": "留侯里"},
                {"site_id": "新北市板橋區", "village": "流芳里"},
            ],
        )

    def test_sends_county_and_optional_town_query_parameters(self):
        requests = []
        responses = {1: success_page(total_page=1, records=[])}

        records = fetch_population(
            "11507",
            county="新北市",
            town="板橋區",
            open_url=fake_open_url(responses, requests),
        )

        params = parse_qs(urlparse(requests[0].full_url).query)
        self.assertEqual(records, [])
        self.assertEqual(params["PAGE"], ["1"])
        self.assertEqual(params["COUNTY"], ["新北市"])
        self.assertEqual(params["TOWN"], ["板橋區"])

    def test_omits_county_to_fetch_nationwide_records(self):
        requests = []
        responses = {
            1: success_page(
                total_page=1,
                records=[{"site_id": "臺北市中正區", "village": "龍興里"}],
            )
        }

        records = fetch_population(
            "11507",
            county=None,
            open_url=fake_open_url(responses, requests),
        )

        params = parse_qs(urlparse(requests[0].full_url).query)
        self.assertEqual(records, [{"site_id": "臺北市中正區", "village": "龍興里"}])
        self.assertEqual(params["PAGE"], ["1"])
        self.assertNotIn("COUNTY", params)

    def test_rejects_invalid_roc_month(self):
        for yyyymm in ("202607", "11500", "11513"):
            with self.subTest(yyyymm=yyyymm):
                with self.assertRaises(PopulationCollectorError):
                    fetch_population(yyyymm, open_url=fake_open_url({}))

    def test_raises_for_unsuccessful_api_response(self):
        responses = {
            1: {
                "responseCode": "OD-0102-S",
                "responseMessage": "查無資料",
            }
        }

        with self.assertRaises(PopulationCollectorError):
            fetch_population("11507", open_url=fake_open_url(responses))

    def test_raises_when_response_data_is_not_a_list(self):
        responses = {
            1: {
                "responseCode": "OD-0101-S",
                "totalPage": "1",
                "responseData": {},
            }
        }

        with self.assertRaises(PopulationCollectorError):
            fetch_population("11507", open_url=fake_open_url(responses))


if __name__ == "__main__":
    unittest.main()
