"""Collect TDX railway station records for New Taipei analysis."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .tdx_client import (
    TdxClient,
    TdxClientError,
    resolve_tdx_client,
)


API_BASE_URL = "https://tdx.transportdata.tw/api/basic"
DEFAULT_VERSION = "v2"
DEFAULT_LOCATION_CITY = "新北市"
DEFAULT_PAGE_SIZE = 1000
SUPPORTED_VERSIONS = frozenset({"v2", "v3"})

V2_METRO_SYSTEMS = frozenset(
    {
        "TRTC",
        "KRTC",
        "TYMC",
        "TMRT",
        "KLRT",
        "NTDLRT",
        "TRTCMG",
        "NTMC",
        "NTALRT",
    }
)
V2_SYSTEMS = frozenset({"TRA", "THSR", *V2_METRO_SYSTEMS})
V3_SYSTEMS = frozenset({"TRA", "AFR"})
DEFAULT_V2_SYSTEMS = (
    "TRA",
    "THSR",
    "TRTC",
    "TYMC",
    "NTMC",
    "NTDLRT",
    "NTALRT",
)
DEFAULT_V3_SYSTEMS = ("TRA",)

OpenURL = Callable[..., Any]


class RailwayStopCollectorError(RuntimeError):
    """Raised when TDX railway station data cannot be fetched or validated."""


def fetch_railway_stops(
    version: str = DEFAULT_VERSION,
    rail_systems: Iterable[str] | None = None,
    location_city: str | None = DEFAULT_LOCATION_CITY,
    client_id: str | None = None,
    client_secret: str | None = None,
    *,
    access_token: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_records: int | None = None,
    include_lines: bool = True,
    open_url: OpenURL = urlopen,
    tdx_client: TdxClient | None = None,
) -> list[dict[str, Any]]:
    """Fetch stations and line memberships from the TDX Rail API.

    v2 is the default because its official OAS currently exposes TRA, THSR,
    Metro and light-rail station endpoints. v3 currently exposes TRA and AFR;
    pass ``rail_systems=("TRA",)`` or ``("AFR",)`` when using v3.

    TDX station fields are preserved. The collector adds ``rail_system``,
    ``transport_type``, ``line_ids`` and ``line_nos`` for downstream analysis.
    In v2, ``location_city`` is sent as an OData filter. v3 station records do
    not expose a city field, so New Taipei filtering and 29-district
    point-in-polygon assignment remain transform-layer responsibilities.
    """

    systems = tuple(
        _default_systems(version) if rail_systems is None else rail_systems
    )
    _validate_inputs(
        version=version,
        rail_systems=systems,
        location_city=location_city,
        page_size=page_size,
        max_records=max_records,
        include_lines=include_lines,
    )
    client = resolve_tdx_client(open_url=open_url, tdx_client=tdx_client)
    token = access_token or _get_access_token(
        client_id=client_id,
        client_secret=client_secret,
        open_url=open_url,
        tdx_client=client,
    )

    records: list[dict[str, Any]] = []
    for rail_system in systems:
        station_path, line_path = _paths_for_system(version, rail_system)
        station_records = _fetch_all(
            path=station_path,
            version=version,
            access_token=token,
            page_size=page_size,
            location_city=location_city,
            data_kind="station",
            max_records=max_records,
            tdx_client=client,
            open_url=open_url,
        )
        line_records = (
            _fetch_all(
                path=line_path,
                version=version,
                access_token=token,
                page_size=page_size,
                location_city=None,
                data_kind="line",
                max_records=None,
                tdx_client=client,
                open_url=open_url,
            )
            if include_lines
            else []
        )
        line_index = _build_line_index(line_records)

        for station_record in station_records:
            _validate_station_record(station_record)
            station_id = station_record["StationID"]
            station_lines = line_index.get(
                station_id,
                {"line_ids": set(), "line_nos": set()},
            )
            enriched = dict(station_record)
            enriched.update(
                {
                    "rail_system": rail_system,
                    "transport_type": _transport_type(rail_system),
                    "line_ids": sorted(station_lines["line_ids"]),
                    "line_nos": sorted(station_lines["line_nos"]),
                }
            )
            records.append(enriched)

    return records


def _default_systems(version: str) -> tuple[str, ...]:
    if version == "v3":
        return DEFAULT_V3_SYSTEMS
    return DEFAULT_V2_SYSTEMS


def _validate_inputs(
    *,
    version: str,
    rail_systems: tuple[str, ...],
    location_city: str | None,
    page_size: int,
    max_records: int | None,
    include_lines: bool,
) -> None:
    if version not in SUPPORTED_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_VERSIONS))
        raise RailwayStopCollectorError(f"version must be one of: {supported}")
    if not rail_systems:
        raise RailwayStopCollectorError("rail_systems must not be empty")

    supported_systems = V3_SYSTEMS if version == "v3" else V2_SYSTEMS
    unsupported = sorted(set(rail_systems) - supported_systems)
    if unsupported:
        supported = ", ".join(sorted(supported_systems))
        raise RailwayStopCollectorError(
            f"unsupported rail systems for {version}: {', '.join(unsupported)}; "
            f"supported systems are: {supported}"
        )
    if location_city is not None and (
        not isinstance(location_city, str) or not location_city.strip()
    ):
        raise RailwayStopCollectorError(
            "location_city must be a non-empty string or None"
        )
    if not isinstance(page_size, int) or isinstance(page_size, bool) or page_size < 1:
        raise RailwayStopCollectorError("page_size must be a positive integer")
    if max_records is not None and (
        not isinstance(max_records, int)
        or isinstance(max_records, bool)
        or max_records < 1
    ):
        raise RailwayStopCollectorError("max_records must be a positive integer or None")
    if not isinstance(include_lines, bool):
        raise RailwayStopCollectorError("include_lines must be a boolean")


def _paths_for_system(version: str, rail_system: str) -> tuple[str, str]:
    if version == "v3":
        return (
            f"/v3/Rail/{rail_system}/Station",
            f"/v3/Rail/{rail_system}/StationOfLine",
        )
    if rail_system in {"TRA", "THSR"}:
        return (
            f"/v2/Rail/{rail_system}/Station",
            f"/v2/Rail/{rail_system}/StationOfLine",
        )
    return (
        f"/v2/Rail/Metro/Station/{rail_system}",
        f"/v2/Rail/Metro/StationOfLine/{rail_system}",
    )


def _transport_type(rail_system: str) -> str:
    if rail_system == "TRA":
        return "TRA"
    if rail_system == "THSR":
        return "THSR"
    if rail_system in {"KLRT", "NTDLRT", "NTALRT"}:
        return "LRT"
    if rail_system in V2_METRO_SYSTEMS:
        return "METRO"
    if rail_system == "AFR":
        return "AFR"
    return "RAIL"


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
        raise RailwayStopCollectorError(str(exc)) from exc


def _fetch_all(
    *,
    path: str,
    version: str,
    access_token: str,
    page_size: int,
    location_city: str | None,
    data_kind: str,
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
        query: dict[str, Any] = {
            "$top": request_page_size,
            "$skip": skip,
            "$format": "JSON",
        }
        if version == "v3":
            query["$count"] = "true"
        if version == "v2" and data_kind == "station" and location_city:
            escaped_city = location_city.replace("'", "''")
            query["$filter"] = f"LocationCity eq '{escaped_city}'"

        request = Request(
            f"{API_BASE_URL}{path}?{urlencode(query)}",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )
        payload = _request_json(
            request,
            open_url=open_url,
            context=f"TDX {path} skip={skip}",
            tdx_client=tdx_client,
        )
        page_records, total_count = _parse_page(
            payload,
            version=version,
            context=f"TDX {path} skip={skip}",
        )
        if remaining is None:
            records.extend(page_records)
        else:
            records.extend(page_records[:remaining])

        if not page_records or (
            max_records is not None and len(records) >= max_records
        ):
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
        raise RailwayStopCollectorError(str(exc)) from exc


def _parse_page(
    payload: Any,
    *,
    version: str,
    context: str,
) -> tuple[list[dict[str, Any]], int | None]:
    if version == "v2":
        if not isinstance(payload, list):
            raise RailwayStopCollectorError(f"{context} v2 response must be a list")
        records = payload
        total_count = None
    else:
        if not isinstance(payload, dict):
            raise RailwayStopCollectorError(f"{context} v3 response must be an object")
        records = payload.get("Stations")
        if not isinstance(records, list):
            raise RailwayStopCollectorError(f"{context} v3 Stations must be a list")
        total_count = _parse_optional_count(payload.get("Count"), context=context)

    if not all(isinstance(record, dict) for record in records):
        raise RailwayStopCollectorError(f"{context} records must be objects")
    return records, total_count


def _parse_optional_count(value: Any, *, context: str) -> int | None:
    if value is None:
        return None
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise RailwayStopCollectorError(f"{context} Count must be an integer") from exc
    if count < 0:
        raise RailwayStopCollectorError(f"{context} Count must not be negative")
    return count


def _validate_station_record(record: dict[str, Any]) -> None:
    for field in ("StationUID", "StationID"):
        if not isinstance(record.get(field), str) or not record[field]:
            raise RailwayStopCollectorError(f"TDX station record is missing {field}")
    if not isinstance(record.get("StationName"), dict):
        raise RailwayStopCollectorError(
            f"TDX station {record['StationUID']} is missing StationName"
        )

    position = record.get("StationPosition")
    if not isinstance(position, dict):
        raise RailwayStopCollectorError(
            f"TDX station {record['StationUID']} is missing StationPosition"
        )
    for field in ("PositionLat", "PositionLon"):
        value = position.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RailwayStopCollectorError(
                f"TDX station {record['StationUID']} has invalid {field}"
            )
        if not math.isfinite(value):
            raise RailwayStopCollectorError(
                f"TDX station {record['StationUID']} has non-finite {field}"
            )


def _build_line_index(
    line_records: list[dict[str, Any]],
) -> dict[str, dict[str, set[str]]]:
    index: dict[str, dict[str, set[str]]] = {}
    for line_record in line_records:
        line_id = line_record.get("LineID")
        if not isinstance(line_id, str) or not line_id:
            raise RailwayStopCollectorError("TDX StationOfLine record is missing LineID")
        line_no = line_record.get("LineNo")
        if line_no is not None and not isinstance(line_no, str):
            raise RailwayStopCollectorError(
                f"TDX line {line_id} has invalid LineNo"
            )
        stations = line_record.get("Stations")
        if not isinstance(stations, list):
            raise RailwayStopCollectorError(
                f"TDX line {line_id} Stations must be a list"
            )

        for line_station in stations:
            station_id = (
                line_station.get("StationID")
                if isinstance(line_station, dict)
                else None
            )
            if not isinstance(station_id, str) or not station_id:
                raise RailwayStopCollectorError(
                    f"TDX line {line_id} has a station without StationID"
                )
            entry = index.setdefault(
                station_id,
                {"line_ids": set(), "line_nos": set()},
            )
            entry["line_ids"].add(line_id)
            if line_no:
                entry["line_nos"].add(line_no)

    return index
