"""District-month population metrics, including exact 18–35 aggregation."""

from __future__ import annotations

import calendar
from collections import defaultdict
from copy import deepcopy
from datetime import date
from typing import Any, Iterable, Mapping

from .common import TransformValueError, build_common_metadata, get_source_value, parse_int, parse_roc_month
from .contracts import TransformResult
from .geography import DistrictResolver
from .quality import QualityCollector


_YOUTH_AGES = range(18, 36)


def transform_population(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for index, raw in enumerate(raw_rows):
        match = resolver.resolve_name(raw.get("site_id")) or resolver.resolve_code(raw.get("district_code"))
        if match is None:
            quality.record_unmapped_district()
            quality.reject(index, raw, "unmapped_district")
            continue
        try:
            period = parse_roc_month(get_source_value(raw, "statistic_yyymm"), field="statistic_yyymm")
            people_total = parse_int(raw.get("people_total"), field="people_total")
            male_values = [parse_int(raw.get(f"people_age_{age:03d}_m"), field=f"people_age_{age:03d}_m") for age in _YOUTH_AGES]
            female_values = [parse_int(raw.get(f"people_age_{age:03d}_f"), field=f"people_age_{age:03d}_f") for age in _YOUTH_AGES]
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue

        district_id, district_name = match
        key = (district_id, period)
        group = groups.setdefault(
            key,
            {
                "district_name": district_name,
                "people_total": [],
                "youth_male": [],
                "youth_female": [],
                "source_record_ids": [],
                "raw_records": [],
            },
        )
        group["people_total"].append(people_total)
        group["youth_male"].append(_sum_complete(male_values))
        group["youth_female"].append(_sum_complete(female_values))
        source_id = raw.get("district_code") or f"{raw.get('site_id', '')}:{raw.get('village', '')}"
        group["source_record_ids"].append(str(source_id))
        group["raw_records"].append(deepcopy(raw))

    output: list[dict[str, Any]] = []
    for (district_id, period), group in sorted(groups.items()):
        total = _sum_complete(group["people_total"])
        youth_male = _sum_complete(group["youth_male"])
        youth_female = _sum_complete(group["youth_female"])
        youth_total = None if youth_male is None or youth_female is None else youth_male + youth_female
        if total is None:
            quality.record_missing("people_total")
        if youth_total is None:
            quality.record_missing("youth_18_35_total")
            quality.warn("incomplete_youth_age_fields")
        metric_values = (
            ("people_total", total, "all_ages", None, None, "context_only"),
            ("youth_18_35_male", youth_male, "derived_18_35", 18, 35, "eligible"),
            ("youth_18_35_female", youth_female, "derived_18_35", 18, 35, "eligible"),
            ("youth_18_35_total", youth_total, "derived_18_35", 18, 35, "eligible"),
        )
        start, end = _month_bounds(period)
        source_record_id = f"population:{district_id}:{period}"
        for metric_id, value, age_scope, age_min, age_max, eligibility in metric_values:
            curated = build_common_metadata(
                dataset="population",
                source="moi_household_registration",
                source_record_id=source_record_id,
                geo_level="district",
                district_id=district_id,
                district_name=group["district_name"],
                period_start=start,
                period_end=end,
                period_type="month",
                metric_id=metric_id,
                value=value,
                unit="people",
                age_scope=age_scope,
                age_min=age_min,
                age_max=age_max,
                youth_eligibility=eligibility,
                fetched_at=fetched_at,
            )
            curated["source_record_ids"] = list(group["source_record_ids"])
            curated["raw_records"] = deepcopy(group["raw_records"])
            output.append(curated)
            quality.accept()

    return TransformResult(output, quality.finish(), quality.quarantine)


def _sum_complete(values: list[int | None]) -> int | None:
    return None if any(value is None for value in values) else sum(value for value in values if value is not None)


def _month_bounds(period: str) -> tuple[str, str]:
    year, month = (int(part) for part in period.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1).isoformat(), date(year, month, last_day).isoformat()
