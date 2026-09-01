import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import marriage_nums  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def marriage_record(
    yyyymm,
    site_id="新北市板橋區",
    village="留侯里",
    *,
    marry_pair="2",
):
    return {
        "statistic_yyymm": yyyymm,
        "site_id": site_id,
        "village": village,
        "marry_pair": marry_pair,
    }


def page_payload(records, *, total_page, page, response_code="OD-0101-S"):
    return {
        "responseCode": response_code,
        "responseMessage": "處理完成",
        "totalPage": str(total_page),
        "totalDataSize": str(len(records)),
        "page": str(page),
        "pageDataSize": str(len(records)),
        "responseData": records,
    }


class TestFetchMarriageNumbers(unittest.TestCase):
    def _fetch(self, *args, **kwargs):
        self.assertTrue(
            hasattr(marriage_nums, "fetch_marriage_numbers"),
            "marriage_nums.fetch_marriage_numbers has not been implemented",
        )
        return marriage_nums.fetch_marriage_numbers(*args, **kwargs)

    def test_fetches_twelve_months_with_new_taipei_and_town_filters(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            query = parse_qs(urlsplit(request.full_url).query)
            yyyymm = urlsplit(request.full_url).path.rsplit("/", 1)[-1]
            return FakeResponse(
                page_payload(
                    [marriage_record(yyyymm)],
                    total_page=1,
                    page=int(query["PAGE"][0]),
                )
            )

        records = self._fetch("114", town="板橋區", open_url=open_url)

        self.assertEqual(len(records), 12)
        self.assertEqual(records[0]["statistic_yyymm"], "11401")
        self.assertEqual(records[-1]["statistic_yyymm"], "11412")
        self.assertEqual(len(requests), 12)
        first_query = parse_qs(urlsplit(requests[0].full_url).query)
        self.assertEqual(first_query["COUNTY"], ["新北市"])
        self.assertEqual(first_query["TOWN"], ["板橋區"])

    def test_fetches_all_pages_for_a_month(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            query = parse_qs(urlsplit(request.full_url).query)
            page = int(query["PAGE"][0])
            yyyymm = urlsplit(request.full_url).path.rsplit("/", 1)[-1]
            records = [marriage_record(yyyymm, village=f"里{page}")]
            total_page = 2 if yyyymm == "11401" else 1
            return FakeResponse(
                page_payload(records, total_page=total_page, page=page)
            )

        records = self._fetch("114", open_url=open_url)

        self.assertEqual(len(records), 13)
        self.assertEqual(
            [record["village"] for record in records[:2]],
            ["里1", "里2"],
        )
        self.assertEqual(len(requests), 13)

    def test_county_none_returns_all_counties_without_county_filter(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            yyyymm = urlsplit(request.full_url).path.rsplit("/", 1)[-1]
            return FakeResponse(
                page_payload(
                    [
                        marriage_record(yyyymm),
                        marriage_record(yyyymm, site_id="臺北市中正區"),
                    ],
                    total_page=1,
                    page=1,
                )
            )

        records = self._fetch("114", county=None, open_url=open_url)

        self.assertEqual(len(records), 24)
        self.assertNotIn("COUNTY", parse_qs(urlsplit(requests[0].full_url).query))

    def test_aggregates_monthly_village_rows_by_district(self):
        records = [
            marriage_record("11401", village="留侯里", marry_pair="2"),
            marriage_record("11401", village="流芳里", marry_pair="0"),
            marriage_record("11402", village="留侯里", marry_pair="3"),
            marriage_record("11402", village="流芳里", marry_pair="1"),
            marriage_record(
                "11401",
                site_id="新北市永和區",
                village="信義里",
                marry_pair="4",
            ),
        ]

        result = marriage_nums.aggregate_marriage_pairs(records)

        self.assertEqual(result, {"新北市板橋區": 6, "新北市永和區": 4})

    def test_rejects_duplicate_monthly_village_rows(self):
        records = [
            marriage_record("11401"),
            marriage_record("11401"),
        ]

        with self.assertRaisesRegex(
            marriage_nums.MarriageNumsCollectorError,
            "duplicate",
        ):
            marriage_nums.aggregate_marriage_pairs(records)

    def test_rejects_invalid_marriage_pair(self):
        with self.assertRaises(marriage_nums.MarriageNumsCollectorError):
            marriage_nums.aggregate_marriage_pairs(
                [marriage_record("11401", marry_pair="unknown")]
            )

    def test_rejects_invalid_year(self):
        with self.assertRaises(marriage_nums.MarriageNumsCollectorError):
            self._fetch("1140", open_url=lambda request, timeout: None)

    def test_rejects_unsuccessful_api_response(self):
        with self.assertRaisesRegex(
            marriage_nums.MarriageNumsCollectorError,
            "ODRP003",
        ):
            self._fetch(
                "114",
                open_url=lambda request, timeout: FakeResponse(
                    page_payload(
                        [],
                        total_page=1,
                        page=1,
                        response_code="OD-0101-F",
                    )
                ),
            )

    def test_rejects_record_with_mismatched_month(self):
        with self.assertRaisesRegex(
            marriage_nums.MarriageNumsCollectorError,
            "statistic_yyymm",
        ):
            self._fetch(
                "114",
                open_url=lambda request, timeout: FakeResponse(
                    page_payload(
                        [marriage_record("11312")],
                        total_page=1,
                        page=1,
                    )
                ),
            )


if __name__ == "__main__":
    unittest.main()
