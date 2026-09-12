"""Village-level population rows used by spatial homepage analytics."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from .common import (
    TransformValueError,
    build_common_metadata,
    get_source_value,
    parse_int,
    parse_roc_month,
)
from .contracts import TransformResult
from .geography import DistrictResolver
from .population import _YOUTH_AGES, _month_bounds, _sum_complete
from .quality import QualityCollector


def transform_population_villages(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    """Aggregate ODRP014 age columns to one row per village and month."""

    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(raw_rows):
        match = resolver.resolve_name(raw.get("site_id")) or resolver.resolve_code(raw.get("district_code"))
        village_code = str(get_source_value(raw, "district_code") or "").strip() or None
        village_name = str(get_source_value(raw, "village") or "").strip() or None
        if match is None:
            quality.record_unmapped_district()
            quality.reject(index, raw, "unmapped_district")
            continue
        if not village_code or not village_name:
            quality.reject(index, raw, "missing_village_identity")
            continue
        try:
            period = parse_roc_month(get_source_value(raw, "statistic_yyymm"), field="statistic_yyymm")
            people_total = parse_int(raw.get("people_total"), field="people_total")
            male_values = [
                parse_int(raw.get(f"people_age_{age:03d}_m"), field=f"people_age_{age:03d}_m")
                for age in _YOUTH_AGES
            ]
            female_values = [
                parse_int(raw.get(f"people_age_{age:03d}_f"), field=f"people_age_{age:03d}_f")
                for age in _YOUTH_AGES
            ]
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        district_id, district_name = match
        key = (village_code, period)
        group = groups.setdefault(
            key,
            {
                "village_name": village_name,
                "district_id": district_id,
                "district_name": district_name,
                "people_total": [],
                "youth_male": [],
                "youth_female": [],
                "raw_records": [],
            },
        )
        if group["village_name"] != village_name or group["district_id"] != district_id:
            quality.record_duplicate()
            quality.reject(index, raw, "conflicting_village_identity")
            continue
        group["people_total"].append(people_total)
        group["youth_male"].append(_sum_complete(male_values))
        group["youth_female"].append(_sum_complete(female_values))
        group["raw_records"].append(deepcopy(raw))

    output: list[dict[str, Any]] = []
    for (village_code, period), group in sorted(groups.items()):
        total = _sum_complete(group["people_total"])
        youth_male = _sum_complete(group["youth_male"])
        youth_female = _sum_complete(group["youth_female"])
        youth_total = None if youth_male is None or youth_female is None else youth_male + youth_female
        flags: list[str] = []
        if total is None:
            quality.record_missing("people_total")
            flags.append("missing_people_total")
        if youth_total is None:
            quality.record_missing("youth_18_35_total")
            quality.warn("incomplete_youth_age_fields")
            flags.append("incomplete_youth_age_fields")
        start, end = _month_bounds(period)
        curated = build_common_metadata(
            dataset="population_villages",
            source="moi_household_registration",
            source_record_id=f"population_villages:{village_code}:{period}",
            geo_level="village",
            district_id=group["district_id"],
            district_name=group["district_name"],
            period_start=start,
            period_end=end,
            period_type="month",
            metric_id="village_population",
            value=total,
            unit="people",
            age_scope="all_ages",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=fetched_at,
            quality_flags=flags,
        )
        curated.update(
            {
                "village_code": village_code,
                "village_name": group["village_name"],
                "people_total": total,
                "youth_18_35_male": youth_male,
                "youth_18_35_female": youth_female,
                "youth_18_35_total": youth_total,
                "source_period": period,
                "raw_records": deepcopy(group["raw_records"]),
            }
        )
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)
