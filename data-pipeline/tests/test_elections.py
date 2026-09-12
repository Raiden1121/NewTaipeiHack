import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors import elections  # noqa: E402
from collectors.contracts import CollectedPayload  # noqa: E402
from transform.elections import transform_elections  # noqa: E402
from transform.geography import DistrictResolver  # noqa: E402


SOURCE_URL = elections.CEC_VOTEDATA_URL


def _zip_payload():
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "votedata/votedata/voteData/2022-111年地方公職人員選舉/T1/prv/elbase.csv",
            "65,000,01,000,0000,新北市\n65,000,01,000,0000,新北市第01選區\n",
        )
        archive.writestr(
            "votedata/votedata/voteData/2022-111年地方公職人員選舉/T1/prv/elcand.csv",
            "65,000,01,000,0000,1,議員甲,16,2,0710417,40,臺灣省,碩士,N,*, \n",
        )
        archive.writestr(
            "votedata/votedata/voteData/2022-111年地方公職人員選舉/V1/elbase.csv",
            "65,000,00,010,0000,板橋區\n65,000,00,010,0001,文化里\n",
        )
        archive.writestr(
            "votedata/votedata/voteData/2022-111年地方公職人員選舉/V1/elcand.csv",
            "65,000,00,010,0001,1,里長甲,1,1,0700105,41,臺灣省,大學,N,*, \n",
        )
    return buffer.getvalue()


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False


def _fake_open_url(request, *, timeout):
    del timeout
    if request.full_url == SOURCE_URL:
        return _FakeResponse(_zip_payload())
    raise AssertionError(f"unexpected URL: {request.full_url}")


class TestElectionCollector(unittest.TestCase):
    def test_encodes_non_ascii_cec_url_for_http_transport(self):
        encoded = elections._encoded_url(SOURCE_URL)

        self.assertNotIn("選舉資料庫", encoded)
        self.assertIn("%E9%81%B8%E8%88%89%E8%B3%87%E6%96%99%E5%BA%AB", encoded)

    def test_collects_new_taipei_t1_and_v1_from_cec_zip(self):
        payload = elections.fetch_elections(
            election_terms=("2022",),
            open_url=_fake_open_url,
        )

        self.assertIsInstance(payload, CollectedPayload)
        self.assertEqual(len(payload.records), 2)
        self.assertEqual(
            {record["election_type"] for record in payload.records},
            {"city_councilor", "borough_chief"},
        )
        councilor = next(row for row in payload.records if row["source_code"] == "T1")
        borough_chief = next(row for row in payload.records if row["source_code"] == "V1")
        self.assertEqual(councilor["election_district_name"], "新北市第01選區")
        self.assertIsNone(councilor["district_name"])
        self.assertEqual(borough_chief["district_name"], "板橋區")
        self.assertEqual(borough_chief["village_name"], "文化里")
        self.assertEqual(councilor["birth_date_roc"], "0710417")
        self.assertEqual(councilor["source_age"], "40")
        self.assertEqual(len(payload.artifacts), 1)
        self.assertEqual(payload.metadata["selected_terms"], ["2022"])


class TestElectionTransform(unittest.TestCase):
    def test_maps_only_v1_to_administrative_district_and_keeps_t1_unmapped(self):
        resolver = DistrictResolver(
            [{"district_id": "65000010", "district_name": "板橋區", "aliases": []}]
        )
        raw_rows = [
            {
                "source_record_id": "elections:2022:T1:1",
                "election_term": "2022",
                "election_date": "2022-11-26",
                "election_type": "city_councilor",
                "source_code": "T1",
                "candidate_name": "議員甲",
                "candidate_number": "1",
                "party_code": "16",
                "sex_code": "2",
                "birth_date_roc": "0710417",
                "source_age": "40",
                "election_district_code": "01",
                "election_district_name": "新北市第01選區",
                "district_name": None,
                "elected_mark": "*",
                "current_mark": "N",
            },
            {
                "source_record_id": "elections:2022:V1:1",
                "election_term": "2022",
                "election_date": "2022-11-26",
                "election_type": "borough_chief",
                "source_code": "V1",
                "candidate_name": "里長甲",
                "candidate_number": "1",
                "party_code": "1",
                "sex_code": "1",
                "birth_date_roc": "0700105",
                "source_age": "41",
                "election_district_code": "00",
                "election_district_name": None,
                "district_name": "板橋區",
                "village_name": "文化里",
                "elected_mark": "*",
                "current_mark": "N",
            },
        ]

        result = transform_elections(raw_rows, resolver=resolver)

        self.assertEqual(len(result.records), 2)
        t1 = next(row for row in result.records if row["source_code"] == "T1")
        v1 = next(row for row in result.records if row["source_code"] == "V1")
        self.assertIsNone(t1["district_id"])
        self.assertEqual(v1["district_id"], "65000010")
        self.assertEqual(v1["birth_date"], "1981-01-05")
        self.assertTrue(v1["elected"])


if __name__ == "__main__":
    unittest.main()
