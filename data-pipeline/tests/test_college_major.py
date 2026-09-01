import json
import ssl
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import college_major  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def overview_record(year, county, *, school_code="0001", major_code="01111001"):
    return {
        "學年度": year,
        "學校代碼": school_code,
        "學校名稱": "測試大學",
        "科系代碼": major_code,
        "科系名稱": "測試科系",
        "日間∕進修別": "D 日",
        "等級別": "B 學士",
        "學生數": "10",
        "教師數": "1",
        "上學年度畢業生數": "2",
        "縣市名稱": county,
        "體系別": "1 一般",
    }


def detail_record(year, county):
    return {
        "學年度": year,
        "學校代碼": "1",
        "學校名稱": "測試大學",
        "科系代碼": "1111001",
        "科系名稱": "測試科系",
        "日間∕進修別": "D 日",
        "等級別": "B 學士",
        "總計": "10",
        "男生計": "4",
        "女生計": "6",
        "一年級男生": "2",
        "一年級女生": "3",
        "縣市名稱": county,
        "體系別": "1 一般",
    }


class TestFetchCollegeMajors(unittest.TestCase):
    def _fetch(self, *args, **kwargs):
        self.assertTrue(
            hasattr(college_major, "fetch_college_majors"),
            "college_major.fetch_college_majors has not been implemented",
        )
        return college_major.fetch_college_majors(*args, **kwargs)

    def test_fetches_overview_and_filters_new_taipei_and_academic_year(self):
        requests = []
        payload = [
            overview_record("114", "01 新北市"),
            overview_record("113", "01 新北市"),
            overview_record("114", "30 臺北市", school_code="0002"),
        ]

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse(payload)

        records = self._fetch(academic_year="114", open_url=open_url)

        self.assertEqual(records, [payload[0]])
        self.assertEqual(requests[0].full_url, college_major.OVERVIEW_URL)

    def test_fetches_student_detail_source_without_merging(self):
        requests = []
        payload = [detail_record("114", "01 新北市")]

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse(payload)

        records = self._fetch(include_student_detail=True, open_url=open_url)

        self.assertEqual(records, payload)
        self.assertEqual(requests[0].full_url, college_major.STUDENT_DETAIL_URL)
        self.assertIn("總計", records[0])
        self.assertNotIn("學生數", records[0])

    def test_county_none_returns_all_counties(self):
        payload = [
            overview_record("114", "01 新北市"),
            overview_record("114", "30 臺北市", school_code="0002"),
        ]

        records = self._fetch(
            county=None,
            open_url=lambda request, timeout: FakeResponse(payload),
        )

        self.assertEqual(records, payload)

    def test_rejects_invalid_json_root(self):
        with self.assertRaises(college_major.CollegeMajorCollectorError):
            self._fetch(
                open_url=lambda request, timeout: FakeResponse({"Items": []}),
            )

    def test_rejects_invalid_academic_year(self):
        with self.assertRaises(college_major.CollegeMajorCollectorError):
            self._fetch(academic_year="")

    def test_uses_verified_ssl_context_with_compatible_strictness(self):
        context = college_major._create_ssl_context()

        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            self.assertFalse(context.verify_flags & ssl.VERIFY_X509_STRICT)


if __name__ == "__main__":
    unittest.main()
