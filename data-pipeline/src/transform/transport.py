"""TDX bus, railway, and bike station normalization."""

from __future__ import annotations

import math
from copy import deepcopy
from datetime import date
from typing import Any, Iterable, Mapping

from .common import TransformValueError, build_common_metadata, build_source_record_id, clean_text, parse_int
from .contracts import TransformResult
from .geography import DistrictResolver
from .quality import QualityCollector


def transform_bus_stops(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    return _transform_stations(records, resolver=resolver, fetched_at=fetched_at, dataset="bus_stops", position_field="StopPosition", id_fields=("StopUID", "StopID"), name_field="StopName")


def transform_railway_stops(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    return _transform_stations(records, resolver=resolver, fetched_at=fetched_at, dataset="railway_stops", position_field="StationPosition", id_fields=("StationUID", "StationID"), name_field="StationName")


def transform_bike_stops(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    return _transform_stations(records, resolver=resolver, fetched_at=fetched_at, dataset="bike_stops", position_field="StationPosition", id_fields=("StationUID", "StationID"), name_field="StationName")


def _transform_stations(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None,
    dataset: str,
    position_field: str,
    id_fields: tuple[str, str],
    name_field: str,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        coordinates = _coordinates(raw.get(position_field))
        if coordinates is None:
            quality.reject(index, raw, "invalid_coordinates")
            continue
        latitude, longitude = coordinates
        availability = raw.get("Availability") if isinstance(raw.get("Availability"), Mapping) else None
        if dataset == "bike_stops":
            try:
                capacity = parse_int(raw.get("BikesCapacity"), field="BikesCapacity")
                available_rent = parse_int(availability.get("AvailableRentBikes"), field="AvailableRentBikes") if availability else None
                available_return = parse_int(availability.get("AvailableReturnBikes"), field="AvailableReturnBikes") if availability else None
            except TransformValueError as exc:
                quality.record_numeric_error()
                quality.reject(index, raw, f"invalid_value:{exc}")
                continue
        match = resolver.resolve_point(latitude, longitude)
        flags: list[str] = []
        if match is None:
            district_id = None
            district_name = None
            quality.record_unmapped_district()
            quality.warn(f"unmapped_district:{dataset}")
            flags.append("unmapped_district")
        else:
            district_id, district_name = match
        station_id = clean_text(raw.get(id_fields[0])) or clean_text(raw.get(id_fields[1]))
        if station_id is None:
            quality.reject(index, raw, "missing_station_id")
            continue
        names = raw.get(name_field) if isinstance(raw.get(name_field), Mapping) else {}
        snapshot = _station_snapshot(raw, fetched_at)
        snapshot_day = _snapshot_day(snapshot)
        curated = build_common_metadata(
            dataset=dataset,
            source="tdx",
            source_record_id=station_id or build_source_record_id(dataset, index, raw),
            geo_level="district",
            district_id=district_id,
            district_name=district_name,
            period_start=snapshot_day,
            period_end=snapshot_day,
            period_type="snapshot",
            metric_id=None,
            value=None,
            unit=None,
            age_scope="not_age_specific",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=fetched_at or snapshot,
            quality_flags=flags,
        )
        curated.update(
            {
                "station_id": station_id,
                "source_station_id": clean_text(raw.get(id_fields[1])),
                "name_zh": clean_text(names.get("Zh_tw")),
                "name_en": clean_text(names.get("En")),
                "latitude": latitude,
                "longitude": longitude,
                "raw_record": deepcopy(raw),
            }
        )
        if dataset == "bus_stops":
            curated["operators"] = deepcopy(raw.get("Operators")) if isinstance(raw.get("Operators"), list) else None
        elif dataset == "railway_stops":
            curated.update(
                {
                    "rail_system": clean_text(raw.get("rail_system")),
                    "transport_type": clean_text(raw.get("transport_type")),
                    "line_ids": deepcopy(raw.get("line_ids")) if isinstance(raw.get("line_ids"), list) else None,
                    "line_nos": deepcopy(raw.get("line_nos")) if isinstance(raw.get("line_nos"), list) else None,
                }
            )
        else:
            static_data = deepcopy(raw)
            static_data.pop("Availability", None)
            curated.update(
                {
                    "capacity": capacity,
                    "availability": deepcopy(dict(availability)) if availability is not None else None,
                    "available_rent_bikes": available_rent,
                    "available_return_bikes": available_return,
                    "static_data": static_data,
                }
            )
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _coordinates(position: Any) -> tuple[float, float] | None:
    if not isinstance(position, Mapping):
        return None
    latitude = position.get("PositionLat")
    longitude = position.get("PositionLon")
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return None
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def _station_snapshot(raw: Mapping[str, Any], fallback: str | None) -> str | None:
    availability = raw.get("Availability")
    if isinstance(availability, Mapping):
        return clean_text(availability.get("UpdateTime")) or clean_text(raw.get("UpdateTime")) or fallback
    return clean_text(raw.get("UpdateTime")) or fallback


def _snapshot_day(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None
