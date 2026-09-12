"""Normalize CEC candidate rows while preserving election-area grain."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Iterable, Mapping

from .common import (
    TransformValueError,
    build_common_metadata,
    build_source_record_id,
    clean_text,
    parse_int,
    parse_roc_date,
)
from .contracts import TransformResult
from .geography import DistrictResolver
from .quality import QualityCollector


_ELECTION_TYPES = frozenset({"city_councilor", "borough_chief"})


def transform_elections(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    """Create one curated record per selected T1/V1 candidate.

    T1 records intentionally keep ``district_id`` null because a city-council
    electoral district is not guaranteed to equal one of New Taipei's 29
    administrative districts. V1 records are resolved through their source
    administrative district name when available.
    """

    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []

    for index, raw in enumerate(raw_rows):
        try:
            election_term = _required(raw, "election_term")
            election_year = _election_year(raw)
            election_type = _required(raw, "election_type")
            if election_type not in _ELECTION_TYPES:
                raise TransformValueError(f"unsupported election_type: {election_type!r}")
            candidate_name = _required(raw, "candidate_name")
            election_date = _iso_date(raw.get("election_date"))
            birth_date = _safe_roc_date(raw.get("birth_date_roc"), quality)
            source_age_numeric = parse_int(raw.get("source_age"), field="source_age")
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue

        source_code = clean_text(raw.get("source_code"))
        district_source_name = clean_text(raw.get("district_name"))
        district_match = resolver.resolve_name(district_source_name)
        flags: list[str] = []
        if election_type == "borough_chief" and district_match is None:
            quality.record_unmapped_district()
            quality.warn("unmapped_district:elections_v1")
            flags.append("unmapped_district")
        district_id, district_name = district_match or (None, district_source_name)
        source_record_id = clean_text(raw.get("source_record_id")) or build_source_record_id(
            "elections", index, raw
        )
        curated = build_common_metadata(
            dataset="elections",
            source="cec_election_candidate_roster",
            source_record_id=source_record_id,
            geo_level="district",
            district_id=district_id,
            district_name=district_name,
            period_start=election_date,
            period_end=election_date,
            period_type="snapshot" if election_date else None,
            metric_id="candidate_record",
            value=1,
            unit="candidate",
            age_scope="all_ages",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=fetched_at,
            quality_flags=flags,
        )
        curated.update(
            {
                "election_term": election_term,
                "election_year": election_year,
                "election_roc_year": clean_text(raw.get("election_roc_year")),
                "election_date": election_date,
                "election_type": election_type,
                "election_type_label": clean_text(raw.get("election_type_label")),
                "source_code": source_code,
                "office_name": clean_text(raw.get("office_name")),
                "candidate_number": clean_text(raw.get("candidate_number")),
                "candidate_name": candidate_name,
                "party_code": clean_text(raw.get("party_code")),
                "sex_code": clean_text(raw.get("sex_code")),
                "birth_date_roc": clean_text(raw.get("birth_date_roc")),
                "birth_year_roc": clean_text(raw.get("birth_year_roc")),
                "birth_date": birth_date,
                "source_age": clean_text(raw.get("source_age")),
                "source_age_numeric": source_age_numeric,
                "birthplace": clean_text(raw.get("birthplace")),
                "education": clean_text(raw.get("education")),
                "current_mark": clean_text(raw.get("current_mark")),
                "elected_mark": clean_text(raw.get("elected_mark")),
                "current": clean_text(raw.get("current_mark")) == "Y",
                "elected": clean_text(raw.get("elected_mark")) == "*",
                "deputy_name": clean_text(raw.get("deputy_name")),
                "city_code": clean_text(raw.get("city_code")),
                "county_code": clean_text(raw.get("county_code")),
                "election_district_code": clean_text(raw.get("election_district_code")),
                "election_district_name": clean_text(raw.get("election_district_name")),
                "township_code": clean_text(raw.get("township_code")),
                "village_code": clean_text(raw.get("village_code")),
                "village_name": clean_text(raw.get("village_name")),
                "geography_type": clean_text(raw.get("geography_type")),
                "source_zip_sha256": clean_text(raw.get("source_zip_sha256")),
                "source_zip_member": clean_text(raw.get("source_zip_member")),
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()

    return TransformResult(output, quality.finish(), quality.quarantine)


def _election_year(raw: Mapping[str, Any]) -> int:
    term = clean_text(raw.get("election_term"))
    if term and term.isdigit() and len(term) == 4:
        return int(term)
    roc_year = clean_text(raw.get("election_roc_year"))
    if roc_year and roc_year.isdigit() and len(roc_year) in {2, 3}:
        return int(roc_year) + 1911
    raise TransformValueError("election_term must be a Gregorian or ROC year")


def _safe_roc_date(value: Any, quality: QualityCollector) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return parse_roc_date(text, field="birth_date_roc")
    except TransformValueError:
        quality.record_missing("birth_date")
        quality.warn("invalid_birth_date_preserved_raw")
        return None


def _iso_date(value: Any) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise TransformValueError("election_date must be ISO date") from exc


def _required(record: Mapping[str, Any], field: str) -> str:
    value = clean_text(record.get(field))
    if value is None:
        raise TransformValueError(f"{field} is required")
    return value
