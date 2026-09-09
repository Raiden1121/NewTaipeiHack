"""Retry transient collection timeouts with bounded exponential backoff."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Iterator
from http.client import IncompleteRead
from urllib.error import URLError
from typing import Any

from .contracts import RetryResult


MAX_ATTEMPTS = 3


def collect_with_retry(
    operation: Callable[[], Any],
    *,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> RetryResult:
    attempt_limit = min(max_attempts, MAX_ATTEMPTS)
    for attempt in range(1, attempt_limit + 1):
        try:
            return RetryResult(operation(), attempt)
        except Exception as exc:
            if not is_timeout_error(exc) or attempt == attempt_limit:
                raise
            if on_retry is not None:
                on_retry(attempt + 1, exc)
            sleep(float(2 ** (attempt - 1)))
    raise AssertionError("unreachable")


def is_timeout_error(exc: BaseException) -> bool:
    exceptions = list(_walk_exception_graph(exc))

    if any(
        isinstance(
            item,
            (TimeoutError, socket.timeout, IncompleteRead, ConnectionResetError),
        )
        for item in exceptions
    ):
        return True

    for item in exceptions:
        if (
            isinstance(item, URLError)
            and not isinstance(item.reason, BaseException)
            and _timeout_message(item.reason)
        ):
            return True

    return False


def _walk_exception_graph(exc: BaseException) -> Iterator[BaseException]:
    pending = [exc]
    visited: set[int] = set()

    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        yield current

        if isinstance(current, URLError) and isinstance(current.reason, BaseException):
            pending.append(current.reason)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)


def _timeout_message(value: object) -> bool:
    message = str(value).lower()
    return "timed out" in message or "timeout" in message
