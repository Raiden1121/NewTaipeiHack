"""Normalize New Taipei public and private childcare facility rosters."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .common import (
    TransformValueError,
    build_common_metadata,
    build_source_record_id,
    clean_text,
    parse_int,
    parse_decimal,
)
from .contracts import TransformResult
from .geography import DistrictResolver
from .quality import QualityCollector


VALID_CARE_TYPES = frozenset({"private", "public"})


def transform_babysitting_places(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
    location_reference: Mapping[str, Mapping[str, Any]] | None = None,
) -> TransformResult:
    """Create one curated record per public or private childcare facility."""

    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    snapshot_day = _snapshot_day(fetched_at)
    active_location_reference = location_reference or {}

    for index, raw in enumerate(raw_rows):
        care_type = clean_text(raw.get("care_type"))
        if care_type not in VALID_CARE_TYPES:
            quality.reject(index, raw, "invalid_care_type")
            continue

        facility_name = clean_text(raw.get("title")) or clean_text(raw.get("name"))
        if not facility_name:
            quality.reject(index, raw, "missing_facility_name")
            continue

        try:
            capacity = (
                parse_int(raw.get("person"), field="person")
                if care_type == "private"
                else None
            )
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_capacity:{exc}")
            continue

        district_match = resolver.resolve_code(raw.get("areacode"))
        if district_match is None:
            district_match = resolver.resolve_name(
                raw.get("area") or raw.get("town")
            )
        flags: list[str] = []
        if district_match is None:
            district_id = None
            district_name = None
            quality.record_unmapped_district()
            quality.warn("unmapped_district:babysitting_places")
            flags.append("unmapped_district")
        else:
            district_id, district_name = district_match

        source_dataset_id = clean_text(raw.get("source_dataset_id"))
        source_row_id = clean_text(raw.get("no"))
        source_record_id = (
            f"babysitting_places:{care_type}:{source_dataset_id}:{source_row_id}"
            if source_dataset_id and source_row_id
            else build_source_record_id("babysitting_places", index, raw)
        )
        reference = active_location_reference.get(source_record_id, {})
        if not isinstance(reference, Mapping):
            reference = {}
        try:
            x_3826 = parse_decimal(
                _reference_value(reference, raw, "x_3826"), field="x_3826"
            )
            y_3826 = parse_decimal(
                _reference_value(reference, raw, "y_3826"), field="y_3826"
            )
            latitude = parse_decimal(
                _reference_value(reference, raw, "latitude"), field="latitude"
            )
            longitude = parse_decimal(
                _reference_value(reference, raw, "longitude"), field="longitude"
            )
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_geocode_value:{exc}")
            continue

        address = clean_text(reference.get("address")) or clean_text(raw.get("address"))
        source_district_name = clean_text(reference.get("source_district_name")) or clean_text(
            raw.get("area") or raw.get("town")
        )
        geocode_status = clean_text(reference.get("geocode_status")) or clean_text(
            raw.get("geocode_status")
        )
        reference_has_coordinates = any(
            reference.get(field) is not None
            for field in ("x_3826", "y_3826", "latitude", "longitude")
        )
        if reference_has_coordinates:
            geocode_status = "matched"
        if (
            geocode_status == "matched"
            and (latitude is None or longitude is None)
            and x_3826 is not None
            and y_3826 is not None
        ):
            latitude, longitude = _to_wgs84(x_3826, y_3826)
        if latitude is None or longitude is None or geocode_status != "matched":
            geocode_status = "excluded_no_verified_coordinate"

        curated = build_common_metadata(
            dataset="babysitting_places",
            source="ntpc_social_affairs_babysitting",
            source_record_id=source_record_id,
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
            fetched_at=fetched_at,
            quality_flags=flags,
        )
        curated.update(
            {
                "care_type": care_type,
                "facility_name": facility_name,
                "operator_name": clean_text(raw.get("unit")),
                "county_name": clean_text(raw.get("county")),
                "county_code": clean_text(raw.get("countycode")),
                "source_district_name": source_district_name,
                "source_district_code": clean_text(raw.get("areacode")),
                "address": address,
                "phone": clean_text(raw.get("localcallservice")),
                "capacity": capacity,
                "capacity_unit": "child_slots" if capacity is not None else None,
                "source_dataset_id": source_dataset_id,
                "source_row_id": source_row_id,
                "latitude": latitude,
                "longitude": longitude,
                "geocode_status": geocode_status,
                "geocode_provider": clean_text(reference.get("geocode_provider"))
                or clean_text(raw.get("geocode_provider")),
                "geocode_crs": clean_text(reference.get("geocode_crs"))
                or clean_text(raw.get("geocode_crs")),
                "geocode_source_url": clean_text(reference.get("geocode_source_url"))
                or clean_text(raw.get("geocode_source_url")),
                "x_3826": x_3826,
                "y_3826": y_3826,
                "geocode_source_period": clean_text(reference.get("geocode_source_period"))
                or clean_text(raw.get("geocode_source_period")),
                "geocode_query": clean_text(reference.get("geocode_query")),
                "location_source_type": clean_text(reference.get("source_type")),
                "location_source_url": clean_text(reference.get("source_url")),
                "location_verified_at": clean_text(reference.get("verified_at")),
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()

    return TransformResult(output, quality.finish(), quality.quarantine)


def load_babysitting_place_location_reference(
    path: str | Path,
) -> dict[str, dict[str, Any]]:
    """Load versioned official coordinates keyed by curated source record ID."""

    reference_path = Path(path)
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("babysitting place location reference must be an object")
    rows = payload.get("records", [])
    if not isinstance(rows, list):
        raise ValueError("babysitting place location reference records must be an array")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("babysitting place location reference rows must be objects")
        source_record_id = clean_text(row.get("source_record_id"))
        if not source_record_id:
            raise ValueError("babysitting place location reference row is missing source_record_id")
        result[source_record_id] = dict(row)
    return result


def _reference_value(
    reference: Mapping[str, Any], raw: Mapping[str, Any], field: str
) -> Any:
    value = reference.get(field)
    return value if value is not None else raw.get(field)


def _to_wgs84(x_3826: float, y_3826: float) -> tuple[float, float]:
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise TransformValueError("pyproj is required to convert EPSG:3826 coordinates") from exc
    transformer = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)
    longitude, latitude = transformer.transform(x_3826, y_3826)
    return float(latitude), float(longitude)


def _snapshot_day(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None
