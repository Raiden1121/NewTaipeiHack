import json
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_PATH = PROJECT_DIR / "data-pipeline" / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.Babysitting_place import (  # noqa: E402
    PRIVATE_API_URL,
    PUBLIC_API_URL,
    fetch_babysitting_places,
)
from orchestration.contracts import PeriodStrategy  # noqa: E402
from run_pipeline import DEFAULT_COLLECTOR_SPECS  # noqa: E402
from transform.childcare import transform_babysitting_places  # noqa: E402
from transform.geography import DistrictResolver  # noqa: E402
from transform.pipeline import canonicalize_dataset, run_transform  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


class TestBabysittingPlaceCollector(unittest.TestCase):
    def test_fetches_private_and_public_json_and_marks_care_type(self):
        requests = []
        responses = {
            f"{PRIVATE_API_URL}?page=0&size=1000": [
                {
                    "no": "1",
                    "title": "私立測試托嬰中心",
                    "county": "新北市",
                    "countycode": "65000",
                    "area": "板橋區",
                    "areacode": "65000010",
                    "address": "新北市板橋區測試路1號",
                    "localcallservice": "02-12345678",
                    "person": "60",
                }
            ],
            f"{PUBLIC_API_URL}?page=0&size=1000": [
                {
                    "no": "2",
                    "name": "公共測試托育中心",
                    "unit": "測試委辦單位",
                    "county": "新北市",
                    "countycode": "65000",
                    "town": "板橋區",
                    "areacode": "65000010",
                    "address": "新北市板橋區測試街2號",
                    "localcallservice": "02-87654321",
                }
            ],
        }

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse(responses[request.full_url])

        payload = fetch_babysitting_places(open_url=open_url)

        self.assertEqual(
            [request.full_url for request in requests],
            [
                f"{PRIVATE_API_URL}?page=0&size=1000",
                f"{PUBLIC_API_URL}?page=0&size=1000",
            ],
        )
        self.assertEqual(len(payload.records), 2)
        self.assertEqual(payload.records[0]["care_type"], "private")
        self.assertEqual(payload.records[0]["source_dataset_id"], "69cecdb0-7796-48df-84e5-99e4f1274245")
        self.assertEqual(payload.records[1]["care_type"], "public")
        self.assertEqual(payload.records[1]["name"], "公共測試托育中心")
        self.assertEqual(payload.metadata["update_frequency"], "annual")

    def test_fetches_all_pages_when_a_source_exceeds_page_size(self):
        requests = []
        private_page_0 = [
            {"no": "1", "title": "私托一", "area": "板橋區"},
            {"no": "2", "title": "私托二", "area": "板橋區"},
        ]
        private_page_1 = [{"no": "3", "title": "私托三", "area": "板橋區"}]
        responses = {
            f"{PRIVATE_API_URL}?page=0&size=2": private_page_0,
            f"{PRIVATE_API_URL}?page=1&size=2": private_page_1,
            f"{PUBLIC_API_URL}?page=0&size=2": [
                {"no": "4", "name": "公托一", "town": "板橋區"}
            ],
        }

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse(responses[request.full_url])

        payload = fetch_babysitting_places(page_size=2, open_url=open_url)

        self.assertEqual(len(payload.records), 4)
        self.assertEqual(
            [request.full_url for request in requests],
            [
                f"{PRIVATE_API_URL}?page=0&size=2",
                f"{PRIVATE_API_URL}?page=1&size=2",
                f"{PUBLIC_API_URL}?page=0&size=2",
            ],
        )

    def test_empty_both_sources_is_reported_as_no_data(self):
        from collectors.errors import CollectorNoDataError

        def open_url(request, timeout):
            return FakeResponse([])

        with self.assertRaises(CollectorNoDataError):
            fetch_babysitting_places(open_url=open_url)


class TestBabysittingPlaceTransform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_normalizes_private_and_public_records(self):
        records = [
            {
                "no": "1",
                "title": "私立測試托嬰中心",
                "county": "新北市",
                "area": "板橋區",
                "areacode": "65000010",
                "address": "新北市板橋區測試路1號",
                "localcallservice": "02-12345678",
                "person": "60",
                "care_type": "private",
                "source_dataset_id": "private-source",
            },
            {
                "no": "2",
                "name": "公共測試托育中心",
                "unit": "測試委辦單位",
                "county": "新北市",
                "town": "板橋區",
                "areacode": "65000010",
                "address": "新北市板橋區測試街2號",
                "localcallservice": "02-87654321",
                "care_type": "public",
                "source_dataset_id": "public-source",
            },
        ]

        result = transform_babysitting_places(
            records,
            resolver=self.resolver,
            fetched_at="2026-09-09T00:00:00+00:00",
        )

        private, public = result.records
        self.assertEqual(private["facility_name"], "私立測試托嬰中心")
        self.assertEqual(private["capacity"], 60)
        self.assertEqual(private["district_id"], "65000010")
        self.assertEqual(private["period_type"], "snapshot")
        self.assertEqual(private["youth_eligibility"], "context_only")
        self.assertEqual(public["facility_name"], "公共測試托育中心")
        self.assertEqual(public["operator_name"], "測試委辦單位")
        self.assertIsNone(public["capacity"])
        self.assertEqual(public["care_type"], "public")
        self.assertIn("raw_record", public)

    def test_registers_canonical_dataset_and_snapshot_schedule(self):
        self.assertEqual(canonicalize_dataset("babysitting_place"), "babysitting_places")
        self.assertEqual(canonicalize_dataset("Babysitting_place"), "babysitting_places")
        result = run_transform(
            "babysitting_places",
            [
                {
                    "no": "1",
                    "title": "測試托嬰中心",
                    "area": "板橋區",
                    "areacode": "65000010",
                    "care_type": "private",
                    "person": "1",
                }
            ],
            resolver=self.resolver,
            fetched_at="2026-09-09T00:00:00+00:00",
        )
        self.assertEqual(result.records[0]["dataset"], "babysitting_places")

        spec = next(spec for spec in DEFAULT_COLLECTOR_SPECS if spec.dataset == "babysitting_places")
        self.assertIs(spec.period_strategy, PeriodStrategy.SNAPSHOT)


if __name__ == "__main__":
    unittest.main()
