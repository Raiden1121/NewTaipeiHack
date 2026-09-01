import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import bike_stop  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def station(station_uid, station_id):
    return {
        "StationUID": station_uid,
        "StationID": station_id,
        "AuthorityID": "NWT",
        "StationName": {"Zh_tw": f"測試站 {station_id}"},
        "StationPosition": {
            "PositionLat": 25.01,
            "PositionLon": 121.46,
        },
        "BikesCapacity": 30,
        "ServiceType": 2,
        "UpdateTime": "2026-08-30T00:00:00+08:00",
    }


def availability(station_uid, station_id):
    return {
        "StationUID": station_uid,
        "StationID": station_id,
        "ServiceStatus": 1,
        "ServiceType": 2,
        "AvailableRentBikes": 12,
        "AvailableReturnBikes": 18,
        "UpdateTime": "2026-08-30T00:01:00+08:00",
    }


class TestFetchBikeStops(unittest.TestCase):
    def _fetch(self, *args, **kwargs):
        self.assertTrue(
            hasattr(bike_stop, "fetch_bike_stops"),
            "bike_stop.fetch_bike_stops has not been implemented",
        )
        return bike_stop.fetch_bike_stops(*args, **kwargs)

    def test_fetches_v2_static_station_pages(self):
        requests = []
        responses = {
            ("Station", 0): [station("NWT-1", "001")],
            ("Station", 1): [station("NWT-2", "002")],
            ("Station", 2): [],
        }

        def open_url(request, timeout):
            requests.append(request)
            parsed = urlparse(request.full_url)
            params = parse_qs(parsed.query)
            resource = parsed.path.split("/")[5]
            skip = int(params["$skip"][0])
            return FakeResponse(responses[(resource, skip)])

        records = self._fetch(
            access_token="existing-token",
            page_size=1,
            open_url=open_url,
        )

        self.assertEqual([record["StationID"] for record in records], ["001", "002"])
        self.assertEqual(records[0]["StationPosition"]["PositionLat"], 25.01)
        self.assertNotIn("Availability", records[0])
        self.assertEqual(len(requests), 3)
        self.assertTrue(
            all(
                request.get_header("Authorization") == "Bearer existing-token"
                for request in requests
            )
        )
        query = parse_qs(urlparse(requests[0].full_url).query)
        self.assertEqual(query["$top"], ["1"])
        self.assertEqual(query["$skip"], ["0"])
        self.assertEqual(query["$format"], ["JSON"])

    def test_optionally_merges_realtime_availability_by_station_uid(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            parsed = urlparse(request.full_url)
            resource = parsed.path.split("/")[5]
            if resource == "Station":
                return FakeResponse([station("NWT-1", "001")])
            if resource == "Availability":
                return FakeResponse([availability("NWT-1", "001")])
            raise AssertionError(f"unexpected request: {request.full_url}")

        records = self._fetch(
            include_availability=True,
            access_token="existing-token",
            open_url=open_url,
        )

        self.assertEqual(records[0]["Availability"]["StationUID"], "NWT-1")
        self.assertEqual(records[0]["Availability"]["AvailableRentBikes"], 12)
        self.assertEqual(records[0]["Availability"]["AvailableReturnBikes"], 18)
        self.assertEqual(len(requests), 2)
        self.assertIn("/v2/Bike/Station/City/NewTaipei?", requests[0].full_url)
        self.assertIn("/v2/Bike/Availability/City/NewTaipei?", requests[1].full_url)

    def test_fetches_bounded_sample_without_availability_endpoint(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse(
                [station("NWT-1", "001"), station("NWT-2", "002")]
            )

        records = self._fetch(
            max_records=1,
            access_token="existing-token",
            open_url=open_url,
        )

        self.assertEqual(len(records), 1)
        self.assertNotIn("Availability", records[0])
        self.assertEqual(len(requests), 1)
        self.assertEqual(parse_qs(urlparse(requests[0].full_url).query)["$top"], ["1"])

    def test_rejects_invalid_city(self):
        self.assertTrue(hasattr(bike_stop, "BikeStopCollectorError"))
        with self.assertRaises(bike_stop.BikeStopCollectorError):
            self._fetch(city="UnknownCity", access_token="existing-token")


if __name__ == "__main__":
    unittest.main()
