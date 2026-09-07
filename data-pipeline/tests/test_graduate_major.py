import json
import ssl
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import graduate_major  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def graduate_record(year, county, *, school_code="0001", major_code="01111001"):
    return {
        "學年度": year,
        "學校代碼": school_code,
        "學校名稱": "測試大學",
        "科系代碼": major_code,
        "科系名稱": "測試科系",
        "日間∕進修別": "D 日",
        "等級別": "B 學士",
        "上學年畢業生人數男": "4",
        "上學年畢業生人數女": "6",
        "縣市名稱": county,
        "體系別": "1 一般",
    }


class TestFetchGraduateMajors(unittest.TestCase):
    def _fetch(self, *args, **kwargs):
        self.assertTrue(
            hasattr(graduate_major, "fetch_graduate_majors"),
            "graduate_major.fetch_graduate_majors has not been implemented",
        )
        return graduate_major.fetch_graduate_majors(*args, **kwargs)

    def test_fetches_9620_and_filters_new_taipei_and_academic_year(self):
        requests = []
        payload = [
            graduate_record("113", "01 新北市"),
            graduate_record("112", "01 新北市"),
            graduate_record("113", "30 臺北市", school_code="0002"),
        ]

        def open_url(request, timeout):
            requests.append((request, timeout))
            return FakeResponse(payload)

        records = self._fetch(academic_year="113", open_url=open_url)

        self.assertEqual(records, [payload[0]])
        self.assertEqual(requests[0][0].full_url, graduate_major.GRADUATE_URL)

    def test_county_none_returns_all_counties(self):
        payload = [
            graduate_record("113", "01 新北市"),
            graduate_record("113", "30 臺北市", school_code="0002"),
        ]

        records = self._fetch(
            academic_year="113",
            county=None,
            open_url=lambda request, timeout: FakeResponse(payload),
        )

        self.assertEqual(records, payload)

    def test_preserves_source_records_without_normalizing_fields(self):
        payload = [graduate_record("113", "01 新北市")]

        records = self._fetch(
            open_url=lambda request, timeout: FakeResponse(payload),
        )

        self.assertEqual(records[0], payload[0])
        self.assertEqual(records[0]["上學年畢業生人數男"], "4")

    def test_rejects_invalid_json_root(self):
        with self.assertRaises(graduate_major.GraduateMajorCollectorError):
            self._fetch(
                open_url=lambda request, timeout: FakeResponse({"Items": []}),
            )

    def test_rejects_county_filter_when_source_has_no_county_field(self):
        payload = [{
            "學年度": "113",
            "細學類": "1111",
            "細學類名稱": "綜合教育細學類",
            "科系名稱": "測試科系",
            "日間_進修別": "D 日",
            "等級別": "B 學士",
            "上學年畢業生人數男": "4",
            "上學年畢業生人數女": "6",
        }]

        with self.assertRaisesRegex(
            graduate_major.GraduateMajorCollectorError,
            "沒有縣市欄位",
        ):
            self._fetch(open_url=lambda request, timeout: FakeResponse(payload))

    def test_rejects_invalid_academic_year(self):
        with self.assertRaises(graduate_major.GraduateMajorCollectorError):
            self._fetch(academic_year="")

    def test_uses_verified_ssl_context_with_compatible_strictness(self):
        context = graduate_major._create_ssl_context()

        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            self.assertFalse(context.verify_flags & ssl.VERIFY_X509_STRICT)


if __name__ == "__main__":
    unittest.main()
