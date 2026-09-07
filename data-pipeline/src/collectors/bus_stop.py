"""Collect TDX bus stop records for a city."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .tdx_client import (
    TOKEN_URL,
    TdxClient,
    TdxClientError,
    resolve_tdx_client,
)


API_URL_TEMPLATE = "https://tdx.transportdata.tw/api/basic/{version}/Bus/{resource}/City/{city}"
DEFAULT_CITY = "NewTaipei"
DEFAULT_VERSION = "v2"
DEFAULT_PAGE_SIZE = 1000
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
    max_records: int | None = None,
    include_operators: bool = True,
    open_url: OpenURL = urlopen,
    tdx_client: TdxClient | None = None,
) -> list[dict[str, Any]]:
    """Fetch city bus stops and attach operators from route-stop data.

    Credentials are read from the explicit arguments first, then from
    ``TDX_CLIENT_ID`` and ``TDX_CLIENT_SECRET``. An existing ``access_token``
    can be supplied to reuse a token across pipeline calls.

    The returned records preserve the TDX stop fields and add ``Operators``
    as a list collected from ``StopOfRoute`` records, keyed by ``StopUID``.
    Point-in-polygon assignment is intentionally left to the transform layer.
    """

    _validate_inputs(
        city=city,
        version=version,
        page_size=page_size,
        max_records=max_records,
        include_operators=include_operators,
    )
    client = resolve_tdx_client(open_url=open_url, tdx_client=tdx_client)
    token = access_token or _get_access_token(
        client_id=client_id,
        client_secret=client_secret,
        open_url=open_url,
        tdx_client=client,
    )

    stop_records = _fetch_all(
        resource="Stop",
        city=city,
        version=version,
        access_token=token,
        page_size=page_size,
        max_records=max_records,
        tdx_client=client,
        open_url=open_url,
    )
    route_records = (
        _fetch_all(
            resource="StopOfRoute",
            city=city,
            version=version,
            access_token=token,
            page_size=page_size,
            max_records=None,
            tdx_client=client,
            open_url=open_url,
        )
        if include_operators
        else []
    )

    operators_by_stop = _build_operator_index(route_records)
    enriched_records = []
    for record in stop_records:
        _validate_stop_record(record)
        enriched = dict(record)
        if include_operators:
            enriched["Operators"] = [
                dict(operator)
                for operator in operators_by_stop.get(record["StopUID"], [])
            ]
        enriched_records.append(enriched)

    return enriched_records


def _validate_inputs(
    *,
    city: str,
    version: str,
    page_size: int,
    max_records: int | None,
    include_operators: bool,
) -> None:
    if not isinstance(city, str) or not city.strip():
        raise BusStopCollectorError("city must be a non-empty string")
    if version not in SUPPORTED_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_VERSIONS))
        raise BusStopCollectorError(f"version must be one of: {supported}")
    if not isinstance(page_size, int) or isinstance(page_size, bool) or page_size < 1:
        raise BusStopCollectorError("page_size must be a positive integer")
    if max_records is not None and (
        not isinstance(max_records, int)
        or isinstance(max_records, bool)
        or max_records < 1
    ):
        raise BusStopCollectorError("max_records must be a positive integer or None")
    if not isinstance(include_operators, bool):
        raise BusStopCollectorError("include_operators must be a boolean")


def _get_access_token(
    *,
    client_id: str | None,
    client_secret: str | None,
    open_url: OpenURL,
    tdx_client: TdxClient | None = None,
) -> str:
    client = resolve_tdx_client(open_url=open_url, tdx_client=tdx_client)
    try:
        return client.get_access_token(
            client_id=client_id,
            client_secret=client_secret,
        )
    except TdxClientError as exc:
        raise BusStopCollectorError(str(exc)) from exc


def _fetch_all(
    *,
    resource: str,
    city: str,
    version: str,
    access_token: str,
    page_size: int,
    max_records: int | None,
    tdx_client: TdxClient,
    open_url: OpenURL,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    skip = 0

    while True:
        remaining = None if max_records is None else max_records - len(records)
        if remaining == 0:
            break
        request_page_size = (
            page_size if remaining is None else min(page_size, remaining)
        )
        query = urlencode(
            {
                "$top": request_page_size,
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
            tdx_client=tdx_client,
        )
        page_records, total_count = _parse_items(
            payload,
            version=version,
            context=f"Bus/{resource}/City/{city} skip={skip}",
        )
        if remaining is None:
            records.extend(page_records)
        else:
            records.extend(page_records[:remaining])

        if not page_records or (max_records is not None and len(records) >= max_records):
            break
        skip += len(page_records)
        if total_count is not None and skip >= total_count:
            break
        if len(page_records) < request_page_size:
            break

    return records


def _request_json(
    request: Request,
    *,
    open_url: OpenURL,
    context: str,
    tdx_client: TdxClient | None = None,
) -> Any:
    client = resolve_tdx_client(open_url=open_url, tdx_client=tdx_client)
    try:
        return client.request_json(request, context=context)
    except TdxClientError as exc:
        raise BusStopCollectorError(str(exc)) from exc


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
