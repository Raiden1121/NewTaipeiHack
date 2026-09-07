import importlib.util
import inspect
import json
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))


class TestTdxClient(unittest.TestCase):
    def test_shared_tdx_client_module_is_available(self):
        self.assertIsNotNone(importlib.util.find_spec("collectors.tdx_client"))

    def test_collectors_expose_bounded_sampling_options(self):
        from collectors.bike_stop import fetch_bike_stops
        from collectors.bus_stop import fetch_bus_stops
        from collectors.railway_stop import fetch_railway_stops

        self.assertIn("max_records", inspect.signature(fetch_bus_stops).parameters)
        self.assertIn("include_operators", inspect.signature(fetch_bus_stops).parameters)
        self.assertIn("max_records", inspect.signature(fetch_bike_stops).parameters)
        self.assertIn("max_records", inspect.signature(fetch_railway_stops).parameters)
        self.assertIn("include_lines", inspect.signature(fetch_railway_stops).parameters)

    def test_rate_limiter_waits_before_next_request(self):
        from collectors.tdx_client import TdxRateLimiter

        current_time = [0.0]
        sleeps = []

        limiter = TdxRateLimiter(
            min_interval_seconds=13.0,
            clock=lambda: current_time[0],
            sleeper=lambda seconds: (
                sleeps.append(seconds),
                current_time.__setitem__(0, current_time[0] + seconds),
            ),
        )

        limiter.wait()
        current_time[0] = 1.0
        limiter.wait()

        self.assertEqual(sleeps, [12.0])

    def test_reuses_unexpired_access_token(self):
        from collectors.tdx_client import TdxClient

        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"access_token": "cached-token", "expires_in": 86400}
                ).encode("utf-8")

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse()

        client = TdxClient(open_url=open_url, min_interval_seconds=0.0)
        first = client.get_access_token(
            client_id="client-id",
            client_secret="client-secret",
        )
        second = client.get_access_token(
            client_id="client-id",
            client_secret="client-secret",
        )

        self.assertEqual(first, "cached-token")
        self.assertEqual(second, "cached-token")
        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()
