"""Birth and marriage transforms with explicit youth eligibility."""

from __future__ import annotations

import re
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable, Mapping

from .common import TransformValueError, build_common_metadata, clean_text, parse_int, parse_roc_month, parse_roc_year
from .contracts import TransformResult
from .geography import DistrictResolver
from .quality import QualityCollector


def transform_births(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    selected: dict[tuple[str, str], dict[int, dict[str, tuple[int, dict[str, Any]]]]] = defaultdict(lambda: defaultdict(dict))
    district_names: dict[str, str] = {}

    for index, raw in enumerate(raw_rows):
        age = _mother_age(raw.get("mother_age"))
        if age is None or not 18 <= age <= 35:
            continue
        match = resolver.resolve_name(raw.get("site_id"))
        if match is None:
            quality.record_unmapped_district()
            quality.reject(index, raw, "unmapped_district")
            continue
        sex = clean_text(raw.get("birth_sex"))
        if sex not in {"男", "女", "總計", "合計"}:
            quality.reject(index, raw, "invalid_birth_sex")
            continue
        canonical_sex = "total" if sex in {"總計", "合計"} else sex
        try:
            year = parse_roc_year(raw.get("statistic_yyy"), field="statistic_yyy")
            count = parse_int(raw.get("birth_count"), field="birth_count", allow_none=False)
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        district_id, district_name = match
        age_rows = selected[(district_id, year)][age]
        if canonical_sex in age_rows:
            quality.record_duplicate()
            quality.reject(index, raw, "duplicate_record")
            continue
        age_rows[canonical_sex] = (count, deepcopy(raw))
        district_names[district_id] = district_name

    output: list[dict[str, Any]] = []
    for (district_id, year), ages in sorted(selected.items()):
        total = 0
        provenance: list[dict[str, Any]] = []
        according: set[str] = set()
        for age_rows in ages.values():
            for _count, raw in age_rows.values():
                provenance.append(raw)
                according_value = clean_text(raw.get("according"))
                if according_value:
                    according.add(according_value)
            if "total" in age_rows:
                count, _raw = age_rows["total"]
                total += count
            else:
                for count, _raw in age_rows.values():
                    total += count
        curated = build_common_metadata(
            dataset="births",
            source="moi_household_registration",
            source_record_id=f"births:{district_id}:{year}",
            geo_level="district",
            district_id=district_id,
            district_name=district_names[district_id],
            period_start=f"{year}-01-01",
            period_end=f"{year}-12-31",
            period_type="year",
            metric_id="births_mother_age_18_35",
            value=total,
            unit="births",
            age_scope="exact_18_35",
            age_min=18,
            age_max=35,
            youth_eligibility="eligible",
            fetched_at=fetched_at,
        )
        curated["according"] = sorted(according)
        curated["raw_records"] = provenance
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def transform_marriages(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    seen: set[tuple[str, str, str]] = set()
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(raw_rows):
        duplicate_key = (str(raw.get("statistic_yyymm")), str(raw.get("site_id")), str(raw.get("village")))
        if duplicate_key in seen:
            quality.record_duplicate()
            quality.reject(index, raw, "duplicate_record")
            continue
        seen.add(duplicate_key)
        match = resolver.resolve_name(raw.get("site_id"))
        if match is None:
            quality.record_unmapped_district()
            quality.reject(index, raw, "unmapped_district")
            continue
        try:
            period = parse_roc_month(raw.get("statistic_yyymm"), field="statistic_yyymm")
            count = parse_int(raw.get("marry_pair"), field="marry_pair", allow_none=False)
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        district_id, district_name = match
        year = period[:4]
        group = groups.setdefault((district_id, year), {"district_name": district_name, "value": 0, "raw_records": []})
        group["value"] += count
        group["raw_records"].append(deepcopy(raw))

    output: list[dict[str, Any]] = []
    for (district_id, year), group in sorted(groups.items()):
        curated = build_common_metadata(
            dataset="marriages",
            source="moi_household_registration",
            source_record_id=f"marriages:{district_id}:{year}",
            geo_level="district",
            district_id=district_id,
            district_name=group["district_name"],
            period_start=f"{year}-01-01",
            period_end=f"{year}-12-31",
            period_type="year",
            metric_id="marriage_pairs_total",
            value=group["value"],
            unit="pairs",
            age_scope="all_ages",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=fetched_at,
        )
        curated["raw_records"] = group["raw_records"]
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _mother_age(value: Any) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    match = re.fullmatch(r"(\d{1,3})歲", text)
    return int(match.group(1)) if match else None
