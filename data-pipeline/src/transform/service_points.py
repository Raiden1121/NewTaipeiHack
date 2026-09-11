"""Normalize Youth Bureau startup-base point snapshots."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from .common import (
    TransformValueError,
    build_common_metadata,
    build_source_record_id,
    clean_text,
    parse_decimal,
    parse_roc_date,
)
from .contracts import TransformResult
from .geography import DistrictResolver
from .quality import QualityCollector


_DISTRICT_PATTERN = re.compile(r"新北市(?P<district>[^\s,，]+區)")


def transform_youth_service_points(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
    location_reference: Mapping[str, Mapping[str, Any]] | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    snapshot_day = _snapshot_day(fetched_at)
    active_location_reference = location_reference or {}

    for index, raw in enumerate(raw_rows):
        point_id = clean_text(raw.get("point_id"))
        name = clean_text(raw.get("name"))
        point_type = clean_text(raw.get("point_type"))
        if not point_id:
            quality.reject(index, raw, "missing_point_id")
            continue
        if not name:
            quality.reject(index, raw, "missing_point_name")
            continue
        if point_type != "startup_base":
            quality.reject(index, raw, "unsupported_point_type")
            continue

        reference = active_location_reference.get(point_id, {})
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
            published_date = _parse_source_date(raw.get("published_date_roc"))
            updated_date = _parse_source_date(raw.get("updated_date_roc"))
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue

        address = clean_text(reference.get("address")) or clean_text(raw.get("address"))
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
        source_district_name = clean_text(reference.get("source_district_name")) or clean_text(
            raw.get("source_district_name")
        )
        if source_district_name is None and address:
            match = _DISTRICT_PATTERN.search(address)
            source_district_name = match.group("district") if match else None
        district_match = resolver.resolve_name(source_district_name)
        flags: list[str] = []
        if district_match is None:
            quality.record_unmapped_district()
            quality.warn("unmapped_district:youth_service_points")
            flags.append("unmapped_district")
        district_id, district_name = district_match or (None, source_district_name)
        period = updated_date or published_date or snapshot_day
        curated = build_common_metadata(
            dataset="youth_service_points",
            source="ntpc_youth_bureau_startup_base",
            source_record_id=clean_text(raw.get("source_record_id"))
            or build_source_record_id("youth_service_points", index, raw),
            geo_level="district",
            district_id=district_id,
            district_name=district_name,
            period_start=period,
            period_end=period,
            period_type="snapshot" if period else None,
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
                "point_id": point_id,
                "point_type": point_type,
                "name": name,
                "address": address,
                "source_district_name": source_district_name,
                "phone": clean_text(raw.get("phone")),
                "email": clean_text(raw.get("email")),
                "published_date": published_date,
                "published_date_raw": clean_text(raw.get("published_date_raw")),
                "updated_date": updated_date,
                "updated_date_raw": clean_text(raw.get("updated_date_raw")),
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
                "address_alternatives": _clean_text_list(reference.get("address_alternatives")),
                "location_source_type": clean_text(reference.get("source_type")),
                "location_source_url": clean_text(reference.get("source_url")),
                "location_verified_at": clean_text(reference.get("verified_at")),
                "detail_url": clean_text(raw.get("detail_url")),
                "source_html_sha256": clean_text(raw.get("source_html_sha256")),
                "artifact_filename": clean_text(raw.get("artifact_filename")),
                "content_text": clean_text(raw.get("content_text")),
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()

    return TransformResult(output, quality.finish(), quality.quarantine)


def load_youth_service_point_location_reference(
    path: str | Path,
) -> dict[str, dict[str, Any]]:
    """Load versioned manual locations keyed by the stable service-point ID."""

    reference_path = Path(path)
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("youth service point location reference must be a JSON object")
    rows = payload.get("records", [])
    if not isinstance(rows, list):
        raise ValueError("youth service point location reference records must be an array")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("youth service point location reference rows must be objects")
        point_id = clean_text(row.get("point_id"))
        if not point_id:
            raise ValueError("youth service point location reference row is missing point_id")
        result[point_id] = dict(row)
    return result


def _reference_value(
    reference: Mapping[str, Any], raw: Mapping[str, Any], field: str
) -> Any:
    value = reference.get(field)
    return value if value is not None else raw.get(field)


def _clean_text_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [text for item in value if (text := clean_text(item)) is not None]


def _to_wgs84(x_3826: float, y_3826: float) -> tuple[float, float]:
    try:
        from pyproj import Transformer  # type: ignore
    except ImportError as exc:
        raise TransformValueError("pyproj is required to convert EPSG:3826 coordinates") from exc
    transformer = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)
    longitude, latitude = transformer.transform(x_3826, y_3826)
    return float(latitude), float(longitude)


def _parse_source_date(value: Any) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    return parse_roc_date(text, field="source_date")


def _snapshot_day(fetched_at: str | None) -> str | None:
    if not fetched_at:
        return None
    try:
        return date.fromisoformat(fetched_at[:10]).isoformat()
    except ValueError:
        return None
