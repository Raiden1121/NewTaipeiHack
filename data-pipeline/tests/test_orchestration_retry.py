import socket
import sys
import unittest
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import URLError


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from orchestration.retry import (  # noqa: E402
    collect_with_retry,
    is_timeout_error,
)
from collectors.errors import CollectorNoDataError  # noqa: E402
from collectors.population_collector import PopulationCollectorError  # noqa: E402
from collectors.wage import WageCollectorError  # noqa: E402


class TestCollectWithRetry(unittest.TestCase):
    def test_retries_incomplete_read_then_succeeds(self):
        calls = 0

        def operation():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise IncompleteRead(b"partial")
            return ["record"]

        result = collect_with_retry(operation, sleep=lambda _: None)

        self.assertEqual(result.value, ["record"])
        self.assertEqual(result.attempts, 3)

    def test_does_not_retry_collector_validation_error(self):
        calls = 0

        def operation():
            nonlocal calls
            calls += 1
            raise ValueError("invalid source schema")

        with self.assertRaises(ValueError):
            collect_with_retry(operation, sleep=lambda _: None)

        self.assertEqual(calls, 1)

    def test_retries_two_timeouts_then_returns_success(self):
        attempts = 0
        delays = []

        def operation():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                try:
                    raise TimeoutError("read timed out")
                except TimeoutError as exc:
                    raise RuntimeError("collector request failed") from exc
            return ["record"]

        result = collect_with_retry(operation, sleep=delays.append)

        self.assertEqual(result.value, ["record"])
        self.assertEqual(result.attempts, 3)
        self.assertEqual(delays, [1.0, 2.0])

    def test_does_not_retry_validation_error(self):
        attempts = 0

        def operation():
            nonlocal attempts
            attempts += 1
            raise ValueError("schema mismatch")

        with self.assertRaises(ValueError):
            collect_with_retry(operation, sleep=lambda _: None)

        self.assertEqual(attempts, 1)

    def test_caps_requested_attempts_at_three(self):
        attempts = 0
        delays = []

        def operation():
            nonlocal attempts
            attempts += 1
            raise TimeoutError("read timed out")

        with self.assertRaises(TimeoutError):
            collect_with_retry(operation, max_attempts=4, sleep=delays.append)

        self.assertEqual(attempts, 3)
        self.assertEqual(delays, [1.0, 2.0])

    def test_reraises_final_wrapped_timeout_after_exhausting_attempts(self):
        attempts = 0
        delays = []
        final_error = RuntimeError("collector request failed")

        def operation():
            nonlocal attempts
            attempts += 1
            try:
                raise TimeoutError(f"read timed out on attempt {attempts}")
            except TimeoutError as exc:
                raise final_error from exc

        with self.assertRaises(RuntimeError) as raised:
            collect_with_retry(operation, sleep=delays.append)

        self.assertIs(raised.exception, final_error)
        self.assertEqual(attempts, 3)
        self.assertEqual(delays, [1.0, 2.0])

    def test_calls_on_retry_with_next_attempt_and_wrapped_error(self):
        retry_events = []

        def operation():
            try:
                raise socket.timeout("socket timed out")
            except socket.timeout as exc:
                raise RuntimeError("collector request failed") from exc

        with self.assertRaises(RuntimeError):
            collect_with_retry(
                operation,
                sleep=lambda _: None,
                on_retry=lambda attempt, exc: retry_events.append((attempt, exc)),
                max_attempts=2,
            )

        self.assertEqual([attempt for attempt, _ in retry_events], [2])
        self.assertIsInstance(retry_events[0][1], RuntimeError)


class TestIsTimeoutError(unittest.TestCase):
    def test_accepts_connection_reset_error(self):
        self.assertTrue(is_timeout_error(ConnectionResetError("connection reset")))

    def test_accepts_wrapped_incomplete_read_and_connection_reset_error(self):
        cause_wrapper = RuntimeError("collector request failed")
        cause_wrapper.__cause__ = IncompleteRead(b"partial")
        context_wrapper = RuntimeError("collector request interrupted")
        context_wrapper.__context__ = ConnectionResetError("connection reset")
        root = RuntimeError("root")
        root.__cause__ = cause_wrapper
        root.__context__ = context_wrapper

        self.assertTrue(is_timeout_error(root))

    def test_accepts_timeout_error(self):
        self.assertTrue(is_timeout_error(TimeoutError("timed out")))

    def test_accepts_url_error_with_timeout_reason(self):
        self.assertTrue(is_timeout_error(URLError(socket.timeout("timed out"))))

    def test_walks_both_cause_and_context_chains(self):
        cause_wrapper = RuntimeError("cause wrapper")
        cause_wrapper.__cause__ = TimeoutError("cause timeout")
        context_wrapper = RuntimeError("context wrapper")
        context_wrapper.__context__ = socket.timeout("context timeout")
        root = RuntimeError("root")
        root.__cause__ = cause_wrapper
        root.__context__ = context_wrapper

        self.assertTrue(is_timeout_error(root))

    def test_does_not_match_validation_error_message(self):
        self.assertFalse(is_timeout_error(ValueError("schema mismatch")))

    def test_does_not_match_schema_error_with_timeout_message(self):
        self.assertFalse(is_timeout_error(PopulationCollectorError("schema timeout")))

    def test_does_not_match_validation_error_with_timeout_message(self):
        self.assertFalse(is_timeout_error(PopulationCollectorError("validation timeout")))

    def test_does_not_match_no_data_error_with_timeout_message(self):
        self.assertFalse(is_timeout_error(CollectorNoDataError("no data timeout")))

    def test_does_not_match_unsupported_year_with_timeout_message(self):
        self.assertFalse(is_timeout_error(WageCollectorError("unsupported year timeout")))

    def test_accepts_legacy_network_wrapper_timeout_message(self):
        wrapper = RuntimeError("ODRP014 request failed: read timed out")
        wrapper.__cause__ = TimeoutError("read timed out")

        self.assertTrue(is_timeout_error(wrapper))

    def test_does_not_match_schema_error_with_request_failed_timeout_message(self):
        self.assertFalse(
            is_timeout_error(
                PopulationCollectorError("request failed: schema timeout")
            )
        )

    def test_does_not_match_validation_error_with_request_failed_timeout_message(self):
        self.assertFalse(
            is_timeout_error(
                PopulationCollectorError("request failed: validation timeout")
            )
        )

    def test_does_not_match_no_data_error_with_request_failed_timeout_message(self):
        self.assertFalse(
            is_timeout_error(CollectorNoDataError("request failed: no data timeout"))
        )

    def test_does_not_match_unsupported_year_with_request_failed_timeout_message(self):
        self.assertFalse(
            is_timeout_error(WageCollectorError("request failed: unsupported year timeout"))
        )


if __name__ == "__main__":
    unittest.main()
