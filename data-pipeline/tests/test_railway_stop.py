import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import railway_stop  # noqa: E402


TOKEN_URL = (
    "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
)


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
        "StationName": {"Zh_tw": f"測試站 {station_id}"},
        "StationPosition": {
            "PositionLat": 25.01,
            "PositionLon": 121.46,
        },
        "LocationCity": "新北市",
        "LocationTown": "板橋區",
    }


def line(line_id, line_no, station_id):
    return {
        "LineID": line_id,
        "LineNo": line_no,
        "Stations": [{"StationID": station_id, "Sequence": 1}],
    }


class TestFetchRailwayStops(unittest.TestCase):
    def _fetch(self, *args, **kwargs):
        self.assertTrue(
            hasattr(railway_stop, "fetch_railway_stops"),
            "railway_stop.fetch_railway_stops has not been implemented",
        )
        return railway_stop.fetch_railway_stops(*args, **kwargs)

    def test_fetches_v2_station_and_line_data_for_new_taipei_systems(self):
        requests = []
        responses = {
            ("TRA", "station", 0): [station("TRA-1", "1001")],
            ("TRA", "station", 1): [],
            ("TRA", "line", 0): [line("TRA-L1", "1", "1001")],
            ("TRA", "line", 1): [],
            ("NTDLRT", "station", 0): [station("NTDLRT-1", "A01")],
            ("NTDLRT", "station", 1): [],
            ("NTDLRT", "line", 0): [line("V-L1", "V", "A01")],
            ("NTDLRT", "line", 1): [],
        }

        def open_url(request, timeout):
            requests.append(request)
            if request.full_url == TOKEN_URL:
                return FakeResponse({"access_token": "token"})

            parsed = urlparse(request.full_url)
            params = parse_qs(parsed.query)
            skip = int(params["$skip"][0])
            parts = parsed.path.strip("/").split("/")
            system = parts[6] if parts[4] == "Metro" else parts[4]
            kind = "line" if "StationOfLine" in parts else "station"
            return FakeResponse(responses[(system, kind, skip)])

        records = self._fetch(
            version="v2",
            rail_systems=("TRA", "NTDLRT"),
            location_city="新北市",
            access_token="existing-token",
            page_size=1,
            open_url=open_url,
        )

        self.assertEqual(
            [(record["rail_system"], record["StationID"]) for record in records],
            [("TRA", "1001"), ("NTDLRT", "A01")],
        )
        self.assertEqual(records[0]["transport_type"], "TRA")
        self.assertEqual(records[0]["line_ids"], ["TRA-L1"])
        self.assertEqual(records[1]["transport_type"], "LRT")
        self.assertEqual(records[1]["line_nos"], ["V"])

        api_requests = requests
        self.assertEqual(len(api_requests), 8)
        self.assertTrue(
            all(
                request.get_header("Authorization") == "Bearer existing-token"
                for request in api_requests
            )
        )
        station_request = next(
            request
            for request in api_requests
            if "/v2/Rail/TRA/Station?" in request.full_url
        )
        station_params = parse_qs(urlparse(station_request.full_url).query)
        self.assertEqual(station_params["$filter"], ["LocationCity eq '新北市'"])

    def test_fetches_v3_wrapper_and_does_not_apply_v2_city_filter(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            parsed = urlparse(request.full_url)
            if parsed.path.endswith("/TRA/Station"):
                return FakeResponse(
                    {"Count": 1, "Stations": [station("TRA-1", "1001")]}
                )
            if parsed.path.endswith("/TRA/StationOfLine"):
                return FakeResponse(
                    {
                        "Count": 1,
                        "Stations": [line("TRA-L1", "1", "1001")],
                    }
                )
            raise AssertionError(f"unexpected request: {request.full_url}")

        records = self._fetch(
            version="v3",
            rail_systems=("TRA",),
            access_token="existing-token",
            open_url=open_url,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["line_ids"], ["TRA-L1"])
        self.assertEqual(len(requests), 2)
        station_request = requests[0]
        self.assertNotIn("%24filter", station_request.full_url)
        self.assertNotIn("$filter", station_request.full_url)

    def test_fetches_bounded_tra_sample_without_line_endpoint(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse(
                [station("TRA-1", "1001"), station("TRA-2", "1002")]
            )

        records = self._fetch(
            version="v2",
            rail_systems=("TRA",),
            max_records=1,
            include_lines=False,
            access_token="existing-token",
            open_url=open_url,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["transport_type"], "TRA")
        self.assertEqual(records[0]["line_ids"], [])
        self.assertEqual(len(requests), 1)
        self.assertEqual(parse_qs(urlparse(requests[0].full_url).query)["$top"], ["1"])

    def test_rejects_systems_not_available_in_selected_version(self):
        self.assertTrue(hasattr(railway_stop, "fetch_railway_stops"))
        with self.assertRaises(railway_stop.RailwayStopCollectorError):
            railway_stop.fetch_railway_stops(
                version="v3",
                rail_systems=("THSR",),
                access_token="existing-token",
            )


if __name__ == "__main__":
    unittest.main()
