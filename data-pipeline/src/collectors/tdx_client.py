"""Shared TDX authentication, request throttling, and token reuse."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .tdx_env import load_dotenv


TOKEN_URL = (
    "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
)
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_MIN_INTERVAL_SECONDS = 13.0

OpenURL = Callable[..., Any]


class TdxClientError(RuntimeError):
    """Raised when a shared TDX request or authentication operation fails."""


class TdxRateLimiter:
    """Serialize requests with a minimum interval between HTTP calls."""

    def __init__(
        self,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")
        self.min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last_request_at is not None:
                remaining = self.min_interval_seconds - (
                    now - self._last_request_at
                )
                if remaining > 0:
                    self._sleeper(remaining)
            self._last_request_at = self._clock()


class TdxClient:
    """TDX HTTP client with shared request throttling and token caching."""

    def __init__(
        self,
        *,
        open_url: OpenURL = urlopen,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.open_url = open_url
        self.rate_limiter = TdxRateLimiter(
            min_interval_seconds,
            clock=clock,
            sleeper=sleeper,
        )
        self._clock = clock
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._token_credentials: tuple[str, str] | None = None

    def get_access_token(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> str:
        load_dotenv()
        resolved_client_id = client_id or os.getenv("TDX_CLIENT_ID")
        resolved_client_secret = client_secret or os.getenv("TDX_CLIENT_SECRET")
        if not resolved_client_id or not resolved_client_secret:
            raise TdxClientError(
                "TDX credentials are required; pass client_id/client_secret or set "
                "TDX_CLIENT_ID and TDX_CLIENT_SECRET"
            )

        credentials = (resolved_client_id, resolved_client_secret)
        if (
            self._access_token
            and self._token_credentials == credentials
            and self._clock() < self._token_expires_at
        ):
            return self._access_token

        body = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": resolved_client_id,
                "client_secret": resolved_client_secret,
            }
        ).encode("utf-8")
        request = Request(
            TOKEN_URL,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        payload = self.request_json(request, context="TDX access token")
        if not isinstance(payload, dict) or not isinstance(
            payload.get("access_token"), str
        ):
            raise TdxClientError("TDX token response has no access_token")

        try:
            expires_in = int(payload.get("expires_in", 86400))
        except (TypeError, ValueError) as exc:
            raise TdxClientError("TDX token response has invalid expires_in") from exc
        self._access_token = payload["access_token"]
        self._token_credentials = credentials
        self._token_expires_at = self._clock() + max(0, expires_in - 60)
        return self._access_token

    def request_json(self, request: Request, *, context: str) -> Any:
        self.rate_limiter.wait()
        try:
            with self.open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise TdxClientError(f"{context} HTTP error: {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise TdxClientError(f"{context} request failed: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TdxClientError(f"{context} returned invalid JSON") from exc


DEFAULT_TDX_CLIENT = TdxClient()


def resolve_tdx_client(
    *,
    open_url: OpenURL,
    tdx_client: TdxClient | None,
) -> TdxClient:
    """Use the shared production client, or a no-wait client for test doubles."""

    if tdx_client is not None:
        return tdx_client
    if open_url is urlopen:
        return DEFAULT_TDX_CLIENT
    return TdxClient(open_url=open_url, min_interval_seconds=0.0)
