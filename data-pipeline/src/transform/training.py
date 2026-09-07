"""Vocational courses, training observations, and national talent demand."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from .common import TransformValueError, build_common_metadata, build_source_record_id, clean_text, parse_decimal, parse_int, parse_roc_year
from .contracts import TransformResult
from .geography import DistrictResolver
from .housing import _coerce_number
from .quality import QualityCollector


def transform_vt_courses(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    groups: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_rows):
        match = resolver.resolve_name(raw.get("訓練區域")) or resolver.resolve_zip(raw.get("郵遞區號前三碼"))
        if match is None:
            quality.record_unmapped_district()
            quality.reject(index, raw, "unmapped_district")
            continue
        course_id = clean_text(raw.get("課程編號"))
        if not course_id:
            quality.reject(index, raw, "missing_course_id")
            continue
        district_id, district_name = match
        group = groups.setdefault(district_id, {"district_name": district_name, "course_ids": set(), "raw_records": []})
        group["course_ids"].add(course_id)
        group["raw_records"].append(deepcopy(raw))
    output: list[dict[str, Any]] = []
    for district_id, group in sorted(groups.items()):
        curated = build_common_metadata(
            dataset="vt_courses",
            source="mol_vocational_courses",
            source_record_id=f"vt_courses:{district_id}",
            geo_level="district",
            district_id=district_id,
            district_name=group["district_name"],
            period_start=None,
            period_end=None,
            period_type=None,
            metric_id="distinct_course_count",
            value=len(group["course_ids"]),
            unit="courses",
            age_scope="not_age_specific",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=fetched_at,
        )
        curated["course_ids"] = sorted(group["course_ids"])
        curated["raw_records"] = group["raw_records"]
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def transform_training_numbers(
    records: Iterable[Mapping[str, Any]],
    *,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        try:
            people = parse_int(raw.get("訓練人次"), field="訓練人次")
            hours = parse_decimal(raw.get("訓練時數"), field="訓練時數")
            fee = parse_decimal(raw.get("每人訓練費用"), field="每人訓練費用")
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        try:
            start = _calendar_date(raw.get("開訓日期"))
            end = _calendar_date(raw.get("結訓日期"))
        except TransformValueError:
            quality.reject(index, raw, "invalid_date")
            continue
        curated = build_common_metadata(
            dataset="training_numbers",
            source="mol_training_numbers",
            source_record_id=build_source_record_id("training_numbers", index, raw),
            geo_level="county",
            district_id=None,
            district_name=None,
            period_start=start,
            period_end=end,
            period_type="day" if start or end else None,
            metric_id=None,
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
                "county_name": clean_text(raw.get("縣市別辦訓地")),
                "course_code": clean_text(raw.get("課程代碼")),
                "course_name": clean_text(raw.get("課程名稱")),
                "training_hours": _coerce_number(hours),
                "training_hours_unit": "hours",
                "training_people": people,
                "training_people_unit": "person_times",
                "fee_per_person": _coerce_number(fee),
                "fee_per_person_unit": "TWD_per_person",
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def transform_talent_demand(
    records: Iterable[Mapping[str, Any]],
    *,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        try:
            period = clean_text(raw.get("統計期"))
            year = parse_roc_year(period[:-1] if period and period.endswith("年") else period, field="統計期")
            demand = parse_int(raw.get("新登記求才人數（人次）"), field="新登記求才人數")
            new_hired = parse_int(raw.get("新登記求才僱用人數（人次）"), field="新登記求才僱用人數")
            valid_hired = parse_int(raw.get("有效求才僱用人數（人次）"), field="有效求才僱用人數")
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        curated = build_common_metadata(
            dataset="talent_demand",
            source="mol_talent_demand",
            source_record_id=build_source_record_id("talent_demand", index, raw),
            geo_level="national",
            district_id=None,
            district_name=None,
            period_start=f"{year}-01-01",
            period_end=f"{year}-12-31",
            period_type="year",
            metric_id=None,
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
                "occupation": clean_text(raw.get("職業別")),
                "new_demand_count": demand,
                "new_hired_count": new_hired,
                "valid_hired_count": valid_hired,
                "count_unit": "person_times",
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _calendar_date(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    for pattern in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    raise TransformValueError(f"invalid calendar date: {value!r}")
