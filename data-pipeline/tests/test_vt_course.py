import json
import ssl
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import vt_course  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def course_record(course_id, *, district="板橋區", quantity="2"):
    return {
        "訓練縣市": "新北市",
        "訓練區域": district,
        "郵遞區號前三碼": "220",
        "郵遞區號後三碼": "41",
        "訓練地址": "測試路 1 號",
        "課程編號": course_id,
        "課程名稱": "測試職訓課程",
        "數量": quantity,
    }


def page_payload(records, *, total, limit, offset, success=True):
    return {
        "success": success,
        "updateTime": "2026-08-31 10:00:00",
        "result": {
            "resource_id": "A17000000J-000007-Hv9",
            "fields": [],
            "records": records,
            "limit": limit,
            "offset": offset,
            "total": total,
        },
    }


class TestFetchVtCourses(unittest.TestCase):
    def _fetch(self, *args, **kwargs):
        self.assertTrue(
            hasattr(vt_course, "fetch_vt_courses"),
            "vt_course.fetch_vt_courses has not been implemented",
        )
        return vt_course.fetch_vt_courses(*args, **kwargs)

    def test_fetches_new_taipei_pages_with_server_filter(self):
        requests = []
        first_page = [course_record("1001"), course_record("1002")]
        second_page = [course_record("1003")]

        def open_url(request, timeout):
            requests.append(request)
            query = parse_qs(urlsplit(request.full_url).query)
            offset = int(query["offset"][0])
            records = first_page if offset == 0 else second_page
            return FakeResponse(
                page_payload(records, total=3, limit=2, offset=offset)
            )

        records = self._fetch(page_size=2, open_url=open_url)

        self.assertEqual(records, first_page + second_page)
        self.assertEqual(len(requests), 2)
        first_query = parse_qs(urlsplit(requests[0].full_url).query)
        self.assertEqual(
            json.loads(first_query["filters"][0]),
            {"訓練縣市": "新北市"},
        )
        self.assertEqual(first_query["limit"], ["2"])
        self.assertEqual(first_query["offset"], ["0"])
        self.assertEqual(
            parse_qs(urlsplit(requests[1].full_url).query)["offset"],
            ["2"],
        )

    def test_supports_nationwide_and_district_filters(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse(
                page_payload([], total=0, limit=100, offset=0)
            )

        self._fetch(county=None, district="板橋區", open_url=open_url)

        query = parse_qs(urlsplit(requests[0].full_url).query)
        self.assertEqual(
            json.loads(query["filters"][0]),
            {"訓練區域": "板橋區"},
        )

    def test_accepts_real_response_without_total_and_uses_short_page(self):
        requests = []
        first_page = [course_record("1001"), course_record("1002")]
        second_page = [course_record("1003")]

        def open_url(request, timeout):
            requests.append(request)
            query = parse_qs(urlsplit(request.full_url).query)
            offset = int(query["offset"][0])
            records = first_page if offset == 0 else second_page
            payload = page_payload(records, total=3, limit=2, offset=offset)
            payload["result"].pop("total")
            return FakeResponse(payload)

        records = self._fetch(page_size=2, open_url=open_url)

        self.assertEqual(records, first_page + second_page)
        self.assertEqual(len(requests), 2)

    def test_counts_distinct_courses_without_summing_quantity(self):
        records = [
            course_record("1001", quantity="2"),
            course_record("1001", quantity="3"),
            course_record("1002", quantity="4"),
        ]

        self.assertEqual(vt_course.count_distinct_courses(records), 2)

    def test_rejects_unsuccessful_api_response(self):
        with self.assertRaisesRegex(vt_course.VtCourseCollectorError, "API error"):
            self._fetch(
                open_url=lambda request, timeout: FakeResponse(
                    {"success": False, "error": {"message": "bad filter"}}
                )
            )

    def test_rejects_invalid_response_shape(self):
        with self.assertRaises(vt_course.VtCourseCollectorError):
            self._fetch(
                open_url=lambda request, timeout: FakeResponse(
                    {"success": True, "result": {"records": {}}}
                )
            )

    def test_rejects_invalid_page_size(self):
        with self.assertRaises(vt_course.VtCourseCollectorError):
            self._fetch(page_size=0)

    def test_uses_verified_ssl_context_with_compatible_strictness(self):
        context = vt_course._create_ssl_context()

        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            self.assertFalse(context.verify_flags & ssl.VERIFY_X509_STRICT)


if __name__ == "__main__":
    unittest.main()
