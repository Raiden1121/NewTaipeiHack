"""College enrollment joins and national graduate-major observations."""

from __future__ import annotations

import re
import json
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable, Mapping

from .common import TransformValueError, build_common_metadata, build_source_record_id, clean_text, parse_int, parse_roc_year
from .contracts import TransformResult
from .quality import QualityCollector


_JOIN_FIELDS = ("學年度", "學校代碼", "科系代碼", "日間∕進修別", "等級別", "縣市名稱", "體系別")


def transform_college_majors(
    overview_records: Iterable[Mapping[str, Any]],
    detail_records: Iterable[Mapping[str, Any]] | None = None,
    *,
    fetched_at: str | None = None,
) -> TransformResult:
    overview_rows = [dict(record) for record in overview_records]
    detail_rows = [dict(record) for record in detail_records or []]
    quality = QualityCollector(rows_in=len(overview_rows) + len(detail_rows))
    details_by_key: dict[tuple[str, ...], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    seen_details: set[str] = set()
    for detail_index, detail in enumerate(detail_rows):
        fingerprint = json.dumps(detail, ensure_ascii=False, sort_keys=True)
        if fingerprint in seen_details:
            quality.record_duplicate()
            quality.reject(detail_index, detail, "duplicate_detail")
            continue
        seen_details.add(fingerprint)
        try:
            _parse_detail_counts(detail)
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(detail_index, detail, f"invalid_detail:{exc}")
            continue
        details_by_key[_college_key(detail)].append((detail_index, detail))
    matched_detail_keys: set[tuple[str, ...]] = set()
    output: list[dict[str, Any]] = []

    for index, overview in enumerate(overview_rows):
        key = _college_key(overview)
        detail_entries = details_by_key.get(key, [])
        details = [entry[1] for entry in detail_entries]
        flags = [] if details else ["unmatched_college_overview"]
        try:
            curated = _college_record(overview, details, index=index, fetched_at=fetched_at, flags=flags)
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, overview, f"invalid_overview:{exc}")
            continue
        if details:
            matched_detail_keys.add(key)
        else:
            quality.warn("unmatched_college_overview")
        output.append(curated)
        quality.accept()

    for key, detail_entries in details_by_key.items():
        if key in matched_detail_keys:
            continue
        quality.warn("unmatched_student_detail")
        detail_index = detail_entries[0][0]
        details = [entry[1] for entry in detail_entries]
        curated = _college_record(None, details, index=detail_index, fetched_at=fetched_at, flags=["unmatched_student_detail"])
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def transform_graduate_majors(
    records: Iterable[Mapping[str, Any]],
    *,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        try:
            year = parse_roc_year(raw.get("學年度"), field="學年度")
            male = parse_int(raw.get("上學年畢業生人數男"), field="上學年畢業生人數男")
            female = parse_int(raw.get("上學年畢業生人數女"), field="上學年畢業生人數女")
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        start, end = _academic_period(year)
        curated = build_common_metadata(
            dataset="graduate_majors",
            source="moe_9620",
            source_record_id=build_source_record_id("graduate_majors", index, raw),
            geo_level="national",
            district_id=None,
            district_name=None,
            period_start=start,
            period_end=end,
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
                "academic_year": clean_text(raw.get("學年度")),
                "classification_code": clean_text(raw.get("細學類")),
                "classification_name": clean_text(raw.get("細學類名稱")),
                "department_name": clean_text(raw.get("科系名稱")),
                "graduate_male_count": male,
                "graduate_female_count": female,
                "graduate_count": None if male is None or female is None else male + female,
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _college_record(
    overview: dict[str, Any] | None,
    details: list[dict[str, Any]],
    *,
    index: int,
    fetched_at: str | None,
    flags: list[str],
) -> dict[str, Any]:
    source = overview or (details[0] if details else {})
    year = parse_roc_year(source.get("學年度"), field="學年度")
    start, end = _academic_period(year)
    student_count = parse_int(overview.get("學生數"), field="學生數") if overview else None
    teacher_count = parse_int(overview.get("教師數"), field="教師數") if overview else None
    previous_graduates = parse_int(overview.get("上學年度畢業生數"), field="上學年度畢業生數") if overview else None
    detail_counts = _aggregate_detail_counts(details)
    detail_total = detail_counts.get("總計")
    male = detail_counts.get("男生計")
    female = detail_counts.get("女生計")
    county = _county_name(source.get("縣市名稱"))
    curated = build_common_metadata(
        dataset="college_majors",
        source="moe_9621_9622",
        source_record_id=build_source_record_id("college_majors", index, source),
        geo_level="county",
        district_id=None,
        district_name=None,
        period_start=start,
        period_end=end,
        period_type="year",
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
            "county_name": county,
            "academic_year": clean_text(source.get("學年度")),
            "school_code": clean_text(source.get("學校代碼")),
            "school_name": clean_text(source.get("學校名稱")),
            "department_code": clean_text(source.get("科系代碼")),
            "department_name": clean_text(source.get("科系名稱")),
            "student_count": student_count,
            "teacher_count": teacher_count,
            "previous_graduate_count": previous_graduates,
            "detail_student_count": detail_total,
            "male_student_count": male,
            "female_student_count": female,
            "detail_counts": detail_counts,
            "overview_raw_record": deepcopy(overview),
            "detail_raw_record": deepcopy(details[0]) if len(details) == 1 else None,
            "detail_raw_records": deepcopy(details),
        }
    )
    return curated


def _college_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for field in _JOIN_FIELDS:
        text = clean_text(record.get(field)) or ""
        if field in {"學校代碼", "科系代碼"} and text.isdigit():
            text = str(int(text))
        values.append(text)
    return tuple(values)


def _parse_detail_counts(record: Mapping[str, Any]) -> dict[str, int | None]:
    count_fields = {
        key
        for key in record
        if key in {"總計", "男生計", "女生計"} or re.search(r"(?:男生|女生|男|女)$", key)
    }
    return {field: parse_int(record.get(field), field=field) for field in sorted(count_fields)}


def _aggregate_detail_counts(records: list[dict[str, Any]]) -> dict[str, int | None]:
    if not records:
        return {}
    parsed = [_parse_detail_counts(record) for record in records]
    fields = sorted({field for counts in parsed for field in counts})
    return {
        field: _sum_optional([counts.get(field) for counts in parsed])
        for field in fields
    }


def _sum_optional(values: list[int | None]) -> int | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _county_name(value: Any) -> str | None:
    text = clean_text(value)
    return re.sub(r"^\d+\s*", "", text) if text else None


def _academic_period(start_year: str) -> tuple[str, str]:
    year = int(start_year)
    return f"{year}-08-01", f"{year + 1}-07-31"
