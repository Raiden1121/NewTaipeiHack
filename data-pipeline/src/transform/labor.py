"""Current vacancy snapshots and official grouped wage observations."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from typing import Any, Iterable, Mapping

from .common import (
    TransformValueError,
    build_common_metadata,
    build_source_record_id,
    clean_text,
    parse_decimal,
    parse_int,
    parse_roc_date,
    parse_roc_year,
)
from .contracts import TransformResult
from .geography import DistrictResolver
from .housing import _coerce_number
from .quality import QualityCollector


def transform_job_vacancies(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    return _transform_job_vacancy_records(
        records,
        resolver=resolver,
        fetched_at=fetched_at,
        dataset="job_vacancies",
    )


def transform_job_vacancy_salaries(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    return _transform_job_vacancy_records(
        records,
        resolver=resolver,
        fetched_at=fetched_at,
        dataset="job_vacancy_salaries",
    )


def _transform_job_vacancy_records(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None,
    dataset: str,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        geo_scope = clean_text(raw.get("geo_scope")) or "district"
        match = None
        if geo_scope == "district":
            match = resolver.resolve_name(raw.get("district")) or resolver.resolve_zip(raw.get("query_zipno"))
        if geo_scope == "district" and match is None:
            quality.record_unmapped_district()
            quality.reject(index, raw, "unmapped_district")
            continue
        try:
            positions = parse_int(_source_value(raw, "JOB_PERSON"), field="JOB_PERSON", allow_none=False)
            salary_lower = parse_decimal(raw.get("salary_lower", _source_value(raw, "NT_L")), field="salary_lower")
            salary_upper = parse_decimal(raw.get("salary_upper", _source_value(raw, "NT_U")), field="salary_upper")
            midpoint = parse_decimal(raw.get("salary_midpoint"), field="salary_midpoint")
            closing_raw = _source_value(raw, "CJOB_STOP_DATE") or _source_value(raw, "JOB_STOP_DATE") or raw.get("截止日期")
            closing_date = _parse_source_date(closing_raw)
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        snapshot = clean_text(raw.get("snapshot_fetched_at")) or fetched_at
        snapshot_day = _iso_day(snapshot)
        truncated = bool(raw.get("query_truncated", False))
        flags = ["query_truncated"] if truncated else []
        query_warnings = raw.get("query_warnings", [])
        if isinstance(query_warnings, (list, tuple)):
            for warning in query_warnings:
                normalized_warning = clean_text(warning)
                if normalized_warning and normalized_warning not in flags:
                    flags.append(normalized_warning)
                    quality.warn(normalized_warning)
        if truncated:
            quality.warn("query_truncated")
        if snapshot_day is None:
            quality.record_missing("snapshot_fetched_at")
            quality.warn("missing_snapshot")
            flags.append("missing_snapshot")
        if salary_lower is None:
            quality.record_missing("salary_lower")
        if salary_upper is None:
            quality.record_missing("salary_upper")
        if closing_date is None:
            quality.record_missing("closing_date")
        district_id, district_name = match if match is not None else (None, None)
        curated = build_common_metadata(
            dataset=dataset,
            source="taiwanjobs",
            source_record_id=build_source_record_id(dataset, index, raw),
            geo_level=geo_scope,
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
        if midpoint is None and salary_lower is not None and salary_upper is not None:
            midpoint = (salary_lower + salary_upper) / 2
        estimate_type = clean_text(raw.get("salary_estimate_type")) or _salary_estimate_type(salary_lower, salary_upper)
        curated.update(
            {
                "position_count": positions,
                "position_count_unit": "positions",
                "closing_date": closing_date,
                "salary_type": clean_text(raw.get("salary_type") or _source_value(raw, "SALARYCD")),
                "salary_lower": _coerce_number(salary_lower),
                "salary_upper": _coerce_number(salary_upper),
                "salary_midpoint": _coerce_number(midpoint),
                "salary_unit": "TWD_per_month" if clean_text(raw.get("salary_type") or _source_value(raw, "SALARYCD")) == "月薪" else None,
                "salary_estimate_type": estimate_type,
                "snapshot_fetched_at": snapshot,
                "query_truncated": truncated,
                "raw_record": deepcopy(raw),
            }
        )
        if geo_scope == "county":
            curated["county_name"] = "新北市"
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def transform_wages(
    records: Iterable[Mapping[str, Any]],
    *,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        try:
            roc_year = clean_text(raw.get("資料年度"))
            year = parse_roc_year(roc_year[:-1] if roc_year and roc_year.endswith("年") else roc_year, field="資料年度")
            wage = parse_decimal(raw.get("薪資"), field="薪資")
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        county = clean_text(raw.get("縣市別"))
        age_group = clean_text(raw.get("年齡別"))
        age_min, age_max = _closed_age_range(age_group)
        measure = clean_text(raw.get("統計方式"))
        metric_by_measure = {"平均數": "official_wage_average", "中位數": "official_wage_median"}
        if measure not in metric_by_measure:
            quality.reject(index, raw, "unsupported_statistic_method")
            continue
        curated = build_common_metadata(
            dataset="wages",
            source="dgbas_table_6",
            source_record_id=build_source_record_id("wages", index, raw),
            geo_level="county",
            district_id=None,
            district_name=None,
            period_start=f"{year}-01-01",
            period_end=f"{year}-12-31",
            period_type="year",
            metric_id=metric_by_measure[measure],
            value=_coerce_number(wage),
            unit=clean_text(raw.get("單位")),
            age_scope="official_age_group_proxy",
            age_min=age_min,
            age_max=age_max,
            youth_eligibility="proxy_only",
            fetched_at=fetched_at,
        )
        curated.update(
            {
                "county_name": county,
                "official_age_group": age_group,
                "statistic_method": measure,
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _source_value(record: Mapping[str, Any], canonical: str) -> Any:
    for key, value in record.items():
        normalized = re.split(r"[（(]", str(key), maxsplit=1)[0].strip()
        if normalized == canonical:
            return value
    return None


def _iso_day(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _parse_source_date(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    iso = _iso_day(text)
    return iso if iso else parse_roc_date(text, field="closing_date")


def _salary_estimate_type(lower: float | None, upper: float | None) -> str:
    if lower is not None and upper is not None:
        return "range_midpoint"
    if lower is not None:
        return "lower_bound"
    if upper is not None:
        return "upper_bound"
    return "missing"


def _closed_age_range(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    match = re.fullmatch(r"(\d{1,2})-(\d{1,2})歲", value)
    return (int(match.group(1)), int(match.group(2))) if match else (None, None)
