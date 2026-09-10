import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors import college_school  # noqa: E402


class FakeResponse:
    def __init__(self, payload: str):
        self._payload = payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._payload


class TestFetchCollegeSchoolLocations(unittest.TestCase):
    def test_parses_official_directory_and_normalizes_multiline_headers(self):
        payload = (
            '\ufeff序號,"學校\n代碼",公私立,體制,學校名稱,學校英文名稱,職稱,姓名,'
            '縣市別,"第三級\n行政區","郵遞\n區號",學校地址,學校總機,學校傳真,網址\n'
            '1,0001,公立,一般大學,測試大學,Test University,校長,測試校長,'
            '新北市,板橋區,220,新北市板橋區測試路1號,02-1234-5678,02-1234-5679,'
            'https://example.edu.tw\n'
        )

        requests = []

        def open_url(request, timeout):
            requests.append((request, timeout))
            return FakeResponse(payload)

        records = college_school.fetch_college_school_locations(open_url=open_url)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["school_code"], "0001")
        self.assertEqual(records[0]["school_name"], "測試大學")
        self.assertEqual(records[0]["county_name"], "新北市")
        self.assertEqual(records[0]["district_name"], "板橋區")
        self.assertEqual(records[0]["postal_code"], "220")
        self.assertEqual(records[0]["school_address"], "新北市板橋區測試路1號")
        self.assertEqual(records[0]["source"], college_school.SOURCE_NAME)
        self.assertEqual(records[0]["raw_record"]["學校\n代碼"], "0001")
        self.assertEqual(requests[0][0].full_url, college_school.SCHOOL_DIRECTORY_URL)
        self.assertEqual(requests[0][0].get_header("Accept"), "*/*")

    def test_adds_official_school_code_aliases_for_changed_school_codes(self):
        payload = (
            '序號,"學校\n代碼",公私立,體制,學校名稱,學校英文名稱,職稱,姓名,'
            '縣市別,"第三級\n行政區","郵遞\n區號",學校地址,學校總機,學校傳真,網址\n'
            '1,1166,私立,技專校院,亞東技術學院,Old AEUST,校長,測試校長,'
            '新北市,板橋區,220,新北市板橋區四川路二段58號,02-1234-5678,02-1234-5679,'
            'https://example.edu.tw\n'
        )

        records = college_school.fetch_college_school_locations(
            open_url=lambda request, timeout: FakeResponse(payload)
        )

        aliases = {record["school_code"]: record for record in records}
        self.assertIn("1166", aliases)
        self.assertIn("1084", aliases)
        self.assertEqual(aliases["1084"]["school_code_alias_of"], "1166")
        self.assertEqual(aliases["1084"]["district_name"], "板橋區")


if __name__ == "__main__":
    unittest.main()
