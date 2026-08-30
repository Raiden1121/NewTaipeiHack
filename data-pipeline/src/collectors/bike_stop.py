"""Collect TDX public bicycle station records."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .tdx_client import (
    TdxClient,
    TdxClientError,
    resolve_tdx_client,
)


API_URL_TEMPLATE = (
    "https://tdx.transportdata.tw/api/basic/v2/Bike/{resource}/City/{city}"
)
DEFAULT_CITY = "NewTaipei"
DEFAULT_PAGE_SIZE = 1000

SUPPORTED_CITIES = frozenset(
    {
        "Taichung",
        "Hsinchu",
        "MiaoliCounty",
        "ChanghuaCounty",
        "NewTaipei",
        "YunlinCounty",
        "ChiayiCounty",
        "PingtungCounty",
        "TaitungCounty",
        "Taoyuan",
        "Taipei",
        "Kaohsiung",
        "Tainan",
        "Chiayi",
        "HsinchuCounty",
    }
)

OpenURL = Callable[..., Any]


class BikeStopCollectorError(RuntimeError):
    """Raised when TDX bicycle station data cannot be fetched or validated."""


def fetch_bike_stops(
    city: str = DEFAULT_CITY,
    include_availability: bool = False,
    client_id: str | None = None,
    client_secret: str | None = None,
    *,
    access_token: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_records: int | None = None,
    open_url: OpenURL = urlopen,
    tdx_client: TdxClient | None = None,
) -> list[dict[str, Any]]:
    """Fetch static bicycle stations and optionally merge live availability.

    The static ``Station`` endpoint is always called. When
    ``include_availability`` is true, the ``Availability`` endpoint is called
    and its original record is attached as ``Availability`` by StationUID (or
    StationID when StationUID is unavailable). Static station fields remain
    unchanged. Point-in-polygon assignment and station-count calculations are
    left to the transform layer.
    """

    _validate_inputs(
        city=city,
        include_availability=include_availability,
        page_size=page_size,
        max_records=max_records,
    )
    client = resolve_tdx_client(open_url=open_url, tdx_client=tdx_client)
    token = access_token or _get_access_token(
        client_id=client_id,
        client_secret=client_secret,
        open_url=open_url,
        tdx_client=client,
    )

    station_records = _fetch_all(
        resource="Station",
        city=city,
        access_token=token,
        page_size=page_size,
        max_records=max_records,
        tdx_client=client,
        open_url=open_url,
    )
    availability_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    if include_availability:
        availability_records = _fetch_all(
            resource="Availability",
            city=city,
            access_token=token,
            page_size=page_size,
            max_records=max_records,
            tdx_client=client,
            open_url=open_url,
        )
        availability_by_key = _build_availability_index(availability_records)

    enriched_records: list[dict[str, Any]] = []
    for record in station_records:
        _validate_station_record(record)
        enriched = dict(record)
        if include_availability:
            enriched["Availability"] = _find_availability(
                record,
                availability_by_key,
            )
        enriched_records.append(enriched)

    return enriched_records


def _validate_inputs(
    *,
    city: str,
    include_availability: bool,
    page_size: int,
    max_records: int | None,
) -> None:
    if city not in SUPPORTED_CITIES:
        supported = ", ".join(sorted(SUPPORTED_CITIES))
        raise BikeStopCollectorError(
            f"city must be one of: {supported}"
        )
    if not isinstance(include_availability, bool):
        raise BikeStopCollectorError("include_availability must be a boolean")
    if not isinstance(page_size, int) or isinstance(page_size, bool) or page_size < 1:
        raise BikeStopCollectorError("page_size must be a positive integer")
    if max_records is not None and (
        not isinstance(max_records, int)
        or isinstance(max_records, bool)
        or max_records < 1
    ):
        raise BikeStopCollectorError("max_records must be a positive integer or None")


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
        raise BikeStopCollectorError(str(exc)) from exc


def _fetch_all(
    *,
    resource: str,
    city: str,
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
            context=f"TDX v2 Bike/{resource}/City/{city} skip={skip}",
            tdx_client=tdx_client,
        )
        page_records = _parse_page(
            payload,
            context=f"Bike/{resource}/City/{city} skip={skip}",
        )
        if remaining is None:
            records.extend(page_records)
        else:
            records.extend(page_records[:remaining])

        if not page_records or (
            max_records is not None and len(records) >= max_records
        ):
            break
        if len(page_records) < request_page_size:
            break
        skip += len(page_records)

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
        raise BikeStopCollectorError(str(exc)) from exc


def _parse_page(payload: Any, *, context: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise BikeStopCollectorError(f"{context} v2 response must be a list")
    if not all(isinstance(record, dict) for record in payload):
        raise BikeStopCollectorError(f"{context} records must be objects")
    return payload


def _validate_station_record(record: dict[str, Any]) -> None:
    for field in ("StationUID", "StationID"):
        if not isinstance(record.get(field), str) or not record[field]:
            raise BikeStopCollectorError(f"TDX bike station is missing {field}")
    if not isinstance(record.get("StationName"), dict):
        raise BikeStopCollectorError(
            f"TDX bike station {record['StationUID']} is missing StationName"
        )

    position = record.get("StationPosition")
    if not isinstance(position, dict):
        raise BikeStopCollectorError(
            f"TDX bike station {record['StationUID']} is missing StationPosition"
        )
    for field in ("PositionLat", "PositionLon"):
        value = position.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BikeStopCollectorError(
                f"TDX bike station {record['StationUID']} has invalid {field}"
            )
        if not math.isfinite(value):
            raise BikeStopCollectorError(
                f"TDX bike station {record['StationUID']} has non-finite {field}"
            )
    if not isinstance(record.get("UpdateTime"), str) or not record["UpdateTime"]:
        raise BikeStopCollectorError(
            f"TDX bike station {record['StationUID']} is missing UpdateTime"
        )


def _build_availability_index(
    records: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        _validate_availability_record(record)
        for field in ("StationUID", "StationID"):
            value = record.get(field)
            if isinstance(value, str) and value:
                index[(field, value)] = record
    return index


def _find_availability(
    station: dict[str, Any],
    availability_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    for field in ("StationUID", "StationID"):
        value = station.get(field)
        if isinstance(value, str):
            record = availability_by_key.get((field, value))
            if record is not None:
                return dict(record)
    return None


def _validate_availability_record(record: dict[str, Any]) -> None:
    if not any(
        isinstance(record.get(field), str) and record[field]
        for field in ("StationUID", "StationID")
    ):
        raise BikeStopCollectorError(
            "TDX bike availability is missing StationUID and StationID"
        )
    if not isinstance(record.get("UpdateTime"), str) or not record["UpdateTime"]:
        raise BikeStopCollectorError("TDX bike availability is missing UpdateTime")
    for field in (
        "ServiceStatus",
        "AvailableRentBikes",
        "AvailableReturnBikes",
    ):
        value = record.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise BikeStopCollectorError(
                f"TDX bike availability has invalid {field}"
            )
