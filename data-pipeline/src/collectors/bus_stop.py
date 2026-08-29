"""Collect TDX bus stop records for a city."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


TOKEN_URL = (
    "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
)
API_URL_TEMPLATE = "https://tdx.transportdata.tw/api/basic/{version}/Bus/{resource}/City/{city}"
DEFAULT_CITY = "NewTaipei"
DEFAULT_VERSION = "v2"
DEFAULT_PAGE_SIZE = 1000
REQUEST_TIMEOUT_SECONDS = 30
SUPPORTED_VERSIONS = frozenset({"v2", "v3"})

OpenURL = Callable[..., Any]


class BusStopCollectorError(RuntimeError):
    """Raised when TDX bus stop data cannot be fetched or validated."""


def fetch_bus_stops(
    city: str = DEFAULT_CITY,
    version: str = DEFAULT_VERSION,
    client_id: str | None = None,
    client_secret: str | None = None,
    *,
    access_token: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    open_url: OpenURL = urlopen,
) -> list[dict[str, Any]]:
    """Fetch city bus stops and attach operators from route-stop data.

    Credentials are read from the explicit arguments first, then from
    ``TDX_CLIENT_ID`` and ``TDX_CLIENT_SECRET``. An existing ``access_token``
    can be supplied to reuse a token across pipeline calls.

    The returned records preserve the TDX stop fields and add ``Operators``
    as a list collected from ``StopOfRoute`` records, keyed by ``StopUID``.
    Point-in-polygon assignment is intentionally left to the transform layer.
    """

    _validate_inputs(city=city, version=version, page_size=page_size)
    token = access_token or _get_access_token(
        client_id=client_id,
        client_secret=client_secret,
        open_url=open_url,
    )

    stop_records = _fetch_all(
        resource="Stop",
        city=city,
        version=version,
        access_token=token,
        page_size=page_size,
        open_url=open_url,
    )
    route_records = _fetch_all(
        resource="StopOfRoute",
        city=city,
        version=version,
        access_token=token,
        page_size=page_size,
        open_url=open_url,
    )

    operators_by_stop = _build_operator_index(route_records)
    enriched_records = []
    for record in stop_records:
        _validate_stop_record(record)
        enriched = dict(record)
        enriched["Operators"] = [
            dict(operator)
            for operator in operators_by_stop.get(record["StopUID"], [])
        ]
        enriched_records.append(enriched)

    return enriched_records


def _validate_inputs(*, city: str, version: str, page_size: int) -> None:
    if not isinstance(city, str) or not city.strip():
        raise BusStopCollectorError("city must be a non-empty string")
    if version not in SUPPORTED_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_VERSIONS))
        raise BusStopCollectorError(f"version must be one of: {supported}")
    if not isinstance(page_size, int) or isinstance(page_size, bool) or page_size < 1:
        raise BusStopCollectorError("page_size must be a positive integer")


def _get_access_token(
    *,
    client_id: str | None,
    client_secret: str | None,
    open_url: OpenURL,
) -> str:
    resolved_client_id = client_id or os.getenv("TDX_CLIENT_ID")
    resolved_client_secret = client_secret or os.getenv("TDX_CLIENT_SECRET")
    if not resolved_client_id or not resolved_client_secret:
        raise BusStopCollectorError(
            "TDX credentials are required; pass client_id/client_secret or set "
            "TDX_CLIENT_ID and TDX_CLIENT_SECRET"
        )

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

    payload = _request_json(
        request,
        open_url=open_url,
        context="TDX access token",
    )
    if not isinstance(payload, dict) or not isinstance(
        payload.get("access_token"), str
    ):
        raise BusStopCollectorError("TDX token response has no access_token")
    return payload["access_token"]


def _fetch_all(
    *,
    resource: str,
    city: str,
    version: str,
    access_token: str,
    page_size: int,
    open_url: OpenURL,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    skip = 0

    while True:
        query = urlencode(
            {
                "$top": page_size,
                "$skip": skip,
                "$format": "JSON",
            }
        )
        url = API_URL_TEMPLATE.format(
            version=version,
            resource=resource,
            city=quote(city, safe=""),
        )
        request = Request(
            f"{url}?{query}",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )
        payload = _request_json(
            request,
            open_url=open_url,
            context=f"TDX {version} Bus/{resource}/City/{city} skip={skip}",
        )
        page_records, total_count = _parse_items(
            payload,
            version=version,
            context=f"Bus/{resource}/City/{city} skip={skip}",
        )
        records.extend(page_records)

        if not page_records:
            break
        skip += len(page_records)
        if total_count is not None and skip >= total_count:
            break
        if len(page_records) < page_size:
            break

    return records


def _request_json(
    request: Request,
    *,
    open_url: OpenURL,
    context: str,
) -> Any:
    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise BusStopCollectorError(f"{context} HTTP error: {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise BusStopCollectorError(f"{context} request failed: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BusStopCollectorError(f"{context} returned invalid JSON") from exc


def _parse_items(
    payload: Any,
    *,
    version: str,
    context: str,
) -> tuple[list[dict[str, Any]], int | None]:
    if version == "v2":
        if not isinstance(payload, list):
            raise BusStopCollectorError(f"{context} v2 response must be a list")
        records = payload
        total_count = None
    else:
        if not isinstance(payload, dict):
            raise BusStopCollectorError(f"{context} v3 response must be an object")
        records = payload.get("Items")
        if not isinstance(records, list):
            raise BusStopCollectorError(f"{context} v3 Items must be a list")
        total_count = _parse_optional_count(payload.get("Count"), context=context)

    if not all(isinstance(record, dict) for record in records):
        raise BusStopCollectorError(f"{context} records must be objects")
    return records, total_count


def _parse_optional_count(value: Any, *, context: str) -> int | None:
    if value is None:
        return None
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise BusStopCollectorError(f"{context} Count must be an integer") from exc
    if count < 0:
        raise BusStopCollectorError(f"{context} Count must not be negative")
    return count


def _validate_stop_record(record: dict[str, Any]) -> None:
    if not isinstance(record.get("StopUID"), str) or not record["StopUID"]:
        raise BusStopCollectorError("TDX stop record is missing StopUID")
    position = record.get("StopPosition")
    if not isinstance(position, dict):
        raise BusStopCollectorError(
            f"TDX stop {record['StopUID']} is missing StopPosition"
        )
    if not all(
        isinstance(position.get(field), (int, float))
        for field in ("PositionLat", "PositionLon")
    ):
        raise BusStopCollectorError(
            f"TDX stop {record['StopUID']} has invalid PositionLat/PositionLon"
        )


def _build_operator_index(
    route_records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    operators_by_stop: dict[str, list[dict[str, Any]]] = {}
    seen_by_stop: dict[str, set[str]] = {}

    for route in route_records:
        operators = route.get("Operators") or []
        stops = route.get("Stops") or []
        if not isinstance(operators, list) or not isinstance(stops, list):
            continue

        for stop in stops:
            if not isinstance(stop, dict) or not isinstance(stop.get("StopUID"), str):
                continue
            stop_uid = stop["StopUID"]
            for operator in operators:
                if not isinstance(operator, dict):
                    continue
                key = _operator_key(operator)
                if key in seen_by_stop.setdefault(stop_uid, set()):
                    continue
                seen_by_stop[stop_uid].add(key)
                operators_by_stop.setdefault(stop_uid, []).append(operator)

    return operators_by_stop


def _operator_key(operator: dict[str, Any]) -> str:
    identity = operator.get("OperatorCode") or operator.get("OperatorNo")
    if identity:
        return str(identity)
    return json.dumps(operator, ensure_ascii=False, sort_keys=True)
