import json
import ssl
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import training_nums  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def training_record(course_code, *, people="20", county="新北市"):
    return {
        "訓練單位名稱": "測試訓練單位",
        "縣市別辦訓地": county,
        "課程代碼": course_code,
        "課程名稱": "測試課程",
        "訓練時數": "30",
        "訓練人次": people,
        "每人訓練費用": "5000",
        "開訓日期": "2026/01/01",
        "結訓日期": "2026/02/01",
    }


def page_payload(records, *, limit, offset, total=None, success=True):
    result = {
        "resource_id": "A17000000J-030190-lfV",
        "records": records,
    }
    if total is not None:
        result["total"] = total
    return {
        "success": success,
        "updateTime": "2026-08-31T10:00:00",
        "result": result,
    }


class TestFetchTrainingNums(unittest.TestCase):
    def _fetch(self, *args, **kwargs):
        self.assertTrue(
            hasattr(training_nums, "fetch_training_numbers"),
            "training_nums.fetch_training_numbers has not been implemented",
        )
        return training_nums.fetch_training_numbers(*args, **kwargs)

    def test_fetches_new_taipei_pages_with_server_filter(self):
        requests = []
        first_page = [training_record("1001"), training_record("1002")]
        second_page = [training_record("1003", people="15")]

        def open_url(request, timeout):
            requests.append(request)
            query = parse_qs(urlsplit(request.full_url).query)
            offset = int(query["offset"][0])
            records = first_page if offset == 0 else second_page
            return FakeResponse(
                page_payload(records, limit=2, offset=offset, total=3)
            )

        records = self._fetch(page_size=2, open_url=open_url)

        self.assertEqual(records, first_page + second_page)
        self.assertEqual(len(requests), 2)
        query = parse_qs(urlsplit(requests[0].full_url).query)
        self.assertEqual(
            json.loads(query["filters"][0]),
            {"縣市別辦訓地": "新北市"},
        )

    def test_county_none_returns_all_counties_without_county_filter(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse(
                page_payload(
                    [training_record("1001"), training_record("1002", county="臺北市")],
                    limit=100,
                    offset=0,
                )
            )

        records = self._fetch(county=None, open_url=open_url)

        self.assertEqual(len(records), 2)
        query = parse_qs(urlsplit(requests[0].full_url).query)
        self.assertNotIn("filters", query)

    def test_sums_training_people_as_integer_values(self):
        records = [
            training_record("1001", people="20"),
            training_record("1002", people="15"),
        ]

        self.assertEqual(training_nums.sum_training_people(records), 35)

    def test_rejects_invalid_training_people_value(self):
        with self.assertRaises(training_nums.TrainingNumsCollectorError):
            training_nums.sum_training_people(
                [training_record("1001", people="unknown")]
            )

    def test_rejects_unsuccessful_api_response(self):
        with self.assertRaisesRegex(
            training_nums.TrainingNumsCollectorError,
            "API error",
        ):
            self._fetch(
                open_url=lambda request, timeout: FakeResponse(
                    {"success": False, "error": {"message": "bad filter"}}
                )
            )

    def test_rejects_invalid_response_shape(self):
        with self.assertRaises(training_nums.TrainingNumsCollectorError):
            self._fetch(
                open_url=lambda request, timeout: FakeResponse(
                    {"success": True, "result": {"records": {}}}
                )
            )

    def test_uses_verified_ssl_context_with_compatible_strictness(self):
        context = training_nums._create_ssl_context()

        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            self.assertFalse(context.verify_flags & ssl.VERIFY_X509_STRICT)


if __name__ == "__main__":
    unittest.main()
