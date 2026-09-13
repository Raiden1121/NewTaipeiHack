"""Nationwide month totals from ODRP014 village rows, for the national youth KPI."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .common import TransformValueError, build_common_metadata, get_source_value, parse_int, parse_roc_month
from .contracts import TransformResult
from .population import _YOUTH_AGES, _month_bounds
from .quality import QualityCollector


INCOMPLETE_COVERAGE_FLAG = "incomplete_coverage"


def transform_national_population(
    records: Iterable[Mapping[str, Any]],
    *,
    fetched_at: str | None = None,
) -> TransformResult:
    """Sum every village in Taiwan into one national record set per month.

    A national total missing even one village is not the national total, so any
    rejected row flags every output with ``incomplete_coverage``; analytics must
    not present flagged values as observed. Raw rows are not embedded (unlike the
    district transform) because a single month is ~7,700 villages.
    """

    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    totals: dict[str, dict[str, int]] = {}
    seen: dict[str, set[str]] = {}
    rejected = 0

    for index, raw in enumerate(raw_rows):
        try:
            period = parse_roc_month(get_source_value(raw, "statistic_yyymm"), field="statistic_yyymm")
            people_total = parse_int(raw.get("people_total"), field="people_total")
            male_values = [parse_int(raw.get(f"people_age_{age:03d}_m"), field=f"people_age_{age:03d}_m") for age in _YOUTH_AGES]
            female_values = [parse_int(raw.get(f"people_age_{age:03d}_f"), field=f"people_age_{age:03d}_f") for age in _YOUTH_AGES]
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            rejected += 1
            continue
        if people_total is None or None in male_values or None in female_values:
            quality.record_missing()
            quality.reject(index, raw, "missing_value")
            rejected += 1
            continue

        village_id = str(raw.get("district_code") or f"{raw.get('site_id', '')}:{raw.get('village', '')}")
        period_seen = seen.setdefault(period, set())
        if village_id in period_seen:
            quality.record_duplicate()
            continue
        period_seen.add(village_id)

        group = totals.setdefault(period, {"people_total": 0, "youth_male": 0, "youth_female": 0, "villages": 0})
        group["people_total"] += people_total
        group["youth_male"] += sum(male_values)
        group["youth_female"] += sum(female_values)
        group["villages"] += 1

    flags = [INCOMPLETE_COVERAGE_FLAG] if rejected else []
    if rejected:
        quality.warn("incomplete_national_coverage")

    output: list[dict[str, Any]] = []
    for period, group in sorted(totals.items()):
        start, end = _month_bounds(period)
        metric_values = (
            ("people_total", group["people_total"], "all_ages", None, None, "context_only"),
            ("youth_18_35_male", group["youth_male"], "derived_18_35", 18, 35, "eligible"),
            ("youth_18_35_female", group["youth_female"], "derived_18_35", 18, 35, "eligible"),
            ("youth_18_35_total", group["youth_male"] + group["youth_female"], "derived_18_35", 18, 35, "eligible"),
        )
        for metric_id, value, age_scope, age_min, age_max, eligibility in metric_values:
            curated = build_common_metadata(
                dataset="national_population",
                source="moi_household_registration",
                source_record_id=f"national_population:{period}",
                geo_level="national",
                district_id=None,
                district_name=None,
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
                quality_flags=list(flags),
            )
            curated["village_count"] = group["villages"]
            output.append(curated)
            quality.accept()

    return TransformResult(output, quality.finish(), quality.quarantine)
