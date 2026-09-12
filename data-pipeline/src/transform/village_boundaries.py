"""Normalize official village-boundary geometry for spatial analytics."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Iterable, Mapping

from .common import build_common_metadata, clean_text
from .contracts import TransformResult
from .quality import QualityCollector


def transform_village_boundaries(
    records: Iterable[Mapping[str, Any]], *, fetched_at: str | None = None
) -> TransformResult:
    """Keep valid New Taipei polygons with stable village and district IDs."""

    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    seen_villages: set[str] = set()
    period = _snapshot_day(fetched_at)
    for index, raw in enumerate(raw_rows):
        properties = raw.get("properties") if isinstance(raw.get("properties"), Mapping) else raw
        geometry = raw.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            quality.reject(index, raw, "missing_geometry_or_properties")
            continue
        county_code = _first(properties, "COUNTYCODE", "COUNTY_CODE", "COUNTY_ID", "COUNTY")
        village_code = _first(
            properties,
            "ADMIV_ID",
            "ADMIVID",
            "VILLAGE_ID",
            "VILLAGECODE",
            "VILLCODE",
        )
        district_id = _first(properties, "ADMIT_ID", "ADMITID", "TOWN_ID", "TOWNCODE")
        village_name = _first(
            properties, "VILLAGE", "VILLNAME", "ADMIV_NA", "VILLAGE_N", "VILNAME"
        )
        district_name = _first(
            properties, "ADMIT_NA", "TOWNNAME", "TOWN_NA", "DISTRICT", "TOWNNAME"
        )
        if not _is_new_taipei(county_code, district_id, village_code):
            quality.reject(index, raw, "outside_new_taipei")
            continue
        if not village_code or not district_id or not village_name:
            quality.reject(index, raw, "missing_boundary_identity")
            continue
        if village_code in seen_villages:
            quality.record_duplicate()
            quality.reject(index, raw, "duplicate_village_code")
            continue
        if not _valid_geometry(geometry):
            quality.reject(index, raw, "invalid_geometry")
            continue
        seen_villages.add(village_code)
        curated = build_common_metadata(
            dataset="village_boundaries",
            source="nlsc_village_boundaries",
            source_record_id=f"village_boundaries:{village_code}",
            geo_level="village",
            district_id=district_id,
            district_name=district_name,
            period_start=period,
            period_end=period,
            period_type="snapshot" if period else None,
            metric_id="village_boundary",
            value=None,
            unit=None,
            age_scope="not_age_specific",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=fetched_at,
        )
        curated.update(
            {
                "village_code": village_code,
                "village_name": village_name,
                "district_id": district_id,
                "district_name": district_name,
                "geometry": deepcopy(dict(geometry)),
                "crs": "EPSG:3826",
                "source_properties": deepcopy(dict(properties)),
            }
        )
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _first(properties: Mapping[str, Any], *names: str) -> str | None:
    normalized = {str(key).upper().replace("\ufeff", ""): value for key, value in properties.items()}
    for name in names:
        value = clean_text(normalized.get(name))
        if value:
            return value
    return None


def _is_new_taipei(county_code: str | None, district_id: str | None, village_code: str | None) -> bool:
    return (
        (county_code is not None and county_code in {"65", "65000"})
        or (district_id is not None and district_id.startswith("65"))
        or (village_code is not None and village_code.startswith("65"))
    )


def _valid_geometry(geometry: Mapping[str, Any]) -> bool:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    return geometry_type in {"Polygon", "MultiPolygon"} and bool(coordinates)


def _snapshot_day(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


__all__ = ["transform_village_boundaries"]
