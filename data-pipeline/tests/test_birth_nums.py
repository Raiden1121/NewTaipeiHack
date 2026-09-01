import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import birth_nums  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def birth_record(
    site_id,
    *,
    age="18歲",
    birth_sex="男",
    count="10",
):
    return {
        "statistic_yyy": "114",
        "according": "按發生日期分",
        "site_id": site_id,
        "mother_age": age,
        "birth_sex": birth_sex,
        "birth_count": count,
    }


def page_payload(records, *, total_page, page, response_code="OD-0101-S"):
    return {
        "responseCode": response_code,
        "responseMessage": "處理完成",
        "totalPage": str(total_page),
        "totalDataSize": "3",
        "page": str(page),
        "pageDataSize": str(len(records)),
        "responseData": records,
    }


class TestFetchBirthNumbers(unittest.TestCase):
    def _fetch(self, *args, **kwargs):
        self.assertTrue(
            hasattr(birth_nums, "fetch_birth_numbers"),
            "birth_nums.fetch_birth_numbers has not been implemented",
        )
        return birth_nums.fetch_birth_numbers(*args, **kwargs)

    def test_fetches_all_pages_and_filters_new_taipei_districts(self):
        requests = []
        pages = {
            1: [birth_record("新北市板橋區"), birth_record("臺北市中正區")],
            2: [birth_record("新北市永和區", age="19歲")],
        }

        def open_url(request, timeout):
            requests.append(request)
            query = parse_qs(urlsplit(request.full_url).query)
            page = int(query["PAGE"][0])
            records = pages[page]
            return FakeResponse(
                page_payload(records, total_page=2, page=page)
            )

        records = self._fetch("114", open_url=open_url)

        self.assertEqual(records, pages[1][:1] + pages[2])
        self.assertEqual(len(requests), 2)
        self.assertTrue(requests[0].full_url.endswith("/ODRP056/114?PAGE=1"))
        self.assertTrue(requests[1].full_url.endswith("/ODRP056/114?PAGE=2"))

    def test_county_none_returns_all_records_without_local_filter(self):
        all_records = [
            birth_record("新北市板橋區"),
            birth_record("臺北市中正區"),
        ]

        records = self._fetch(
            "114",
            county=None,
            open_url=lambda request, timeout: FakeResponse(
                page_payload(all_records, total_page=1, page=1)
            ),
        )

        self.assertEqual(records, all_records)

    def test_aggregates_exact_18_to_35_single_ages_by_district(self):
        records = [
            birth_record("新北市板橋區", age="18歲", birth_sex="男", count="2"),
            birth_record("新北市板橋區", age="18歲", birth_sex="女", count="1"),
            birth_record("新北市板橋區", age="19歲", birth_sex="男", count="3"),
            birth_record("新北市板橋區", age="35歲", birth_sex="女", count="4"),
            birth_record("新北市板橋區", age="36歲", birth_sex="男", count="100"),
            birth_record("新北市永和區", age="20歲", birth_sex="女", count="3"),
        ]

        result = birth_nums.aggregate_young_births(records)

        self.assertEqual(
            result,
            {"新北市板橋區": 10, "新北市永和區": 3},
        )

    def test_uses_total_sex_row_without_double_counting(self):
        records = [
            birth_record("新北市板橋區", age="18歲", birth_sex="總計", count="7"),
            birth_record("新北市板橋區", age="18歲", birth_sex="男", count="2"),
            birth_record("新北市板橋區", age="18歲", birth_sex="女", count="5"),
        ]

        result = birth_nums.aggregate_young_births(records)

        self.assertEqual(result, {"新北市板橋區": 7})

    def test_rejects_invalid_year(self):
        with self.assertRaises(birth_nums.BirthNumsCollectorError):
            self._fetch("1140", open_url=lambda request, timeout: None)

    def test_rejects_unsuccessful_api_response(self):
        with self.assertRaisesRegex(
            birth_nums.BirthNumsCollectorError,
            "ODRP056",
        ):
            self._fetch(
                "114",
                open_url=lambda request, timeout: FakeResponse(
                    page_payload([], total_page=1, page=1, response_code="OD-0101-F")
                ),
            )

    def test_rejects_invalid_response_shape(self):
        with self.assertRaises(birth_nums.BirthNumsCollectorError):
            self._fetch(
                "114",
                open_url=lambda request, timeout: FakeResponse(
                    {
                        "responseCode": "OD-0101-S",
                        "totalPage": "1",
                        "responseData": {},
                    }
                ),
            )

    def test_rejects_record_with_mismatched_year(self):
        record = birth_record("新北市板橋區")
        record["statistic_yyy"] = "113"

        with self.assertRaisesRegex(
            birth_nums.BirthNumsCollectorError,
            "statistic_yyy",
        ):
            self._fetch(
                "114",
                open_url=lambda request, timeout: FakeResponse(
                    page_payload([record], total_page=1, page=1)
                ),
            )

    def test_rejects_duplicate_selected_age_and_sex_rows(self):
        records = [
            birth_record("新北市板橋區", age="18歲", birth_sex="男"),
            birth_record("新北市板橋區", age="18歲", birth_sex="男"),
        ]

        with self.assertRaisesRegex(
            birth_nums.BirthNumsCollectorError,
            "duplicate",
        ):
            birth_nums.aggregate_young_births(records)


if __name__ == "__main__":
    unittest.main()
