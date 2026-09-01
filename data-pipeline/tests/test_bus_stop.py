import json
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors.bus_stop import (  # noqa: E402
    TOKEN_URL,
    BusStopCollectorError,
    fetch_bus_stops,
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


def fake_open_url(version, responses, requests):
    def open_url(request, timeout):
        requests.append(request)

        if request.full_url == TOKEN_URL:
            return FakeResponse(
                {
                    "access_token": "test-access-token",
                    "expires_in": 86400,
                    "token_type": "Bearer",
                }
            )

        parsed = urlparse(request.full_url)
        params = parse_qs(parsed.query)
        skip = int(params["$skip"][0])
        endpoint = "route" if "/StopOfRoute/" in parsed.path else "stop"
        payload = responses[endpoint].get(skip)
        if payload is None:
            raise AssertionError(f"unexpected request: {request.full_url}")
        return FakeResponse(payload)

    return open_url


def v2_stop(stop_uid):
    return {
        "StopUID": stop_uid,
        "StopID": stop_uid.removeprefix("NWT-"),
        "StopName": {"Zh_tw": f"站牌 {stop_uid}"},
        "StopPosition": {"PositionLat": 25.0, "PositionLon": 121.4},
    }


def v2_route(stop_uid):
    return {
        "RouteUID": "NWT-R1",
        "RouteID": "R1",
        "RouteName": {"Zh_tw": "R1"},
        "Operators": [
            {
                "OperatorID": "OP1",
                "OperatorName": {"Zh_tw": "測試客運"},
                "OperatorCode": "TEST",
                "OperatorNo": "9999",
            }
        ],
        "Stops": [{"StopUID": stop_uid}],
    }


class TestFetchBusStops(unittest.TestCase):
    def test_fetches_v2_pages_and_attaches_route_operators(self):
        requests = []
        responses = {
            "stop": {
                0: [v2_stop("NWT-1")],
                1: [v2_stop("NWT-2")],
                2: [],
            },
            "route": {
                0: [v2_route("NWT-1")],
                1: [],
            },
        }

        records = fetch_bus_stops(
            city="NewTaipei",
            version="v2",
            client_id="client-id",
            client_secret="client-secret",
            page_size=1,
            open_url=fake_open_url("v2", responses, requests),
        )

        self.assertEqual([record["StopUID"] for record in records], ["NWT-1", "NWT-2"])
        self.assertEqual(records[0]["Operators"][0]["OperatorCode"], "TEST")
        self.assertEqual(records[1]["Operators"], [])
        self.assertEqual(requests[0].full_url, TOKEN_URL)
        self.assertEqual(requests[0].method, "POST")
        token_params = parse_qs(requests[0].data.decode("utf-8"))
        self.assertEqual(token_params["grant_type"], ["client_credentials"])
        self.assertEqual(token_params["client_id"], ["client-id"])
        self.assertEqual(token_params["client_secret"], ["client-secret"])
        self.assertEqual(requests[1].get_header("Authorization"), "Bearer test-access-token")

        stop_params = parse_qs(urlparse(requests[1].full_url).query)
        self.assertEqual(stop_params["$top"], ["1"])
        self.assertEqual(stop_params["$skip"], ["0"])
        self.assertEqual(stop_params["$format"], ["JSON"])

    def test_fetches_v3_items_with_existing_access_token(self):
        requests = []
        stop = {
            "StopUID": "NWT-1",
            "StopID": "1",
            "StopName": {"Zh_tw": "站牌 NWT-1"},
            "StopPosition": {"PositionLat": 25.0, "PositionLon": 121.4},
        }
        route = {
            "RouteUID": "NWT-R1",
            "RouteID": "R1",
            "RouteName": {"Zh_tw": "R1"},
            "Operators": [{"OperatorCode": "TEST", "OperatorNo": "9999"}],
            "Stops": [{"StopUID": "NWT-1"}],
        }
        responses = {
            "stop": {0: {"Count": 1, "Items": [stop]}},
            "route": {0: {"Count": 1, "Items": [route]}},
        }

        records = fetch_bus_stops(
            city="NewTaipei",
            version="v3",
            access_token="existing-token",
            open_url=fake_open_url("v3", responses, requests),
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Operators"], route["Operators"])
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(request.get_header("Authorization") == "Bearer existing-token" for request in requests))

    def test_fetches_bounded_sample_without_operator_endpoint(self):
        requests = []

        records = fetch_bus_stops(
            access_token="existing-token",
            max_records=1,
            include_operators=False,
            open_url=fake_open_url(
                "v2",
                {"stop": {0: [v2_stop("NWT-1")]}, "route": {}},
                requests,
            ),
        )

        self.assertEqual(len(records), 1)
        self.assertNotIn("Operators", records[0])
        self.assertEqual(len(requests), 1)
        self.assertEqual(parse_qs(urlparse(requests[0].full_url).query)["$top"], ["1"])

    def test_requires_credentials_when_access_token_is_missing(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TDX_CLIENT_ID", None)
            os.environ.pop("TDX_CLIENT_SECRET", None)
            with patch("collectors.tdx_client.load_dotenv"):
                with self.assertRaises(BusStopCollectorError):
                    fetch_bus_stops(open_url=lambda request, timeout: None)

    def test_rejects_invalid_version(self):
        with self.assertRaises(BusStopCollectorError):
            fetch_bus_stops(version="v1", access_token="existing-token")


if __name__ == "__main__":
    unittest.main()
