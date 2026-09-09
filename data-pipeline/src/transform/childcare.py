"""Normalize New Taipei public and private childcare facility rosters."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Iterable, Mapping

from .common import (
    TransformValueError,
    build_common_metadata,
    build_source_record_id,
    clean_text,
    parse_int,
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
) -> TransformResult:
    """Create one curated record per public or private childcare facility."""

    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    snapshot_day = _snapshot_day(fetched_at)

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
                "source_district_name": clean_text(raw.get("area") or raw.get("town")),
                "source_district_code": clean_text(raw.get("areacode")),
                "address": clean_text(raw.get("address")),
                "phone": clean_text(raw.get("localcallservice")),
                "capacity": capacity,
                "capacity_unit": "child_slots" if capacity is not None else None,
                "source_dataset_id": source_dataset_id,
                "source_row_id": source_row_id,
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()

    return TransformResult(output, quality.finish(), quality.quarantine)


def _snapshot_day(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None
