"""Normalize Youth Bureau grant detail rows and resolve their geography."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Iterable, Mapping

from .common import (
    TransformValueError,
    build_common_metadata,
    build_source_record_id,
    clean_text,
    parse_decimal,
)
from .contracts import TransformResult
from .geography import DistrictResolver
from .quality import QualityCollector


def transform_youth_grants(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver | None = None,
    fetched_at: str | None = None,
) -> TransformResult:
    """Preserve source grant fields while attaching deterministic geo basis."""

    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        try:
            grant_id = clean_text(raw.get("grant_id")) or build_source_record_id(
                "youth_grants", index, raw
            )
            year_roc = _required_year(raw.get("year_roc") or raw.get("grant_year_roc"))
            amount = parse_decimal(
                raw.get("amount_twd_thousand", raw.get("value")),
                field="amount_twd_thousand",
                allow_none=False,
            )
            recipient = _required_text(raw, "recipient_name")
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue

        project_location = clean_text(raw.get("project_location"))
        recipient_address = clean_text(raw.get("recipient_address"))
        district_id, district_name, geo_basis = _resolve_district(
            raw, resolver=resolver, project_location=project_location, recipient_address=recipient_address
        )
        if district_id is None:
            quality.record_unmapped_district()

        year = int(year_roc) + 1911
        curated = build_common_metadata(
            dataset="youth_grants",
            source="ntpc_youth_bureau_grant_detail",
            source_record_id=f"youth_grants:{grant_id}",
            geo_level="district",
            district_id=district_id,
            district_name=district_name,
            period_start=f"{year}-01-01",
            period_end=f"{year}-12-31",
            period_type="year",
            metric_id="grant_amount",
            value=amount,
            unit="TWD_thousand",
            age_scope="not_age_specific",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=fetched_at,
            quality_flags=["district_unresolved"] if district_id is None else [],
        )
        curated.update(
            {
                "grant_id": grant_id,
                "grant_year_roc": year_roc,
                "work_plan": clean_text(raw.get("work_plan")),
                "purpose": clean_text(raw.get("purpose")),
                "recipient_name": recipient,
                "recipient_address": recipient_address,
                "project_location": project_location,
                "agency": clean_text(raw.get("agency")),
                "amount_twd_thousand": amount,
                "geo_basis": geo_basis,
                "purchase_involved": raw.get("purchase_involved"),
                "source_page_number": raw.get("source_page_number"),
                "source_document_url": clean_text(raw.get("source_document_url")),
                "source_pdf_url": clean_text(raw.get("source_pdf_url")),
                "source_pdf_sha256": clean_text(raw.get("source_pdf_sha256")),
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _resolve_district(
    raw: Mapping[str, Any],
    *,
    resolver: DistrictResolver | None,
    project_location: str | None,
    recipient_address: str | None,
) -> tuple[str | None, str | None, str]:
    if resolver is None:
        return None, None, "unresolved"
    for basis, value in (
        ("project_location", project_location),
        ("recipient_address", recipient_address),
    ):
        match = _resolve_text(value, resolver)
        if match is not None:
            return match[0], match[1], basis
    for key in ("district_id", "district_code"):
        match = resolver.resolve_code(raw.get(key))
        if match is not None:
            return match[0], match[1], "source_district_code"
    return None, None, "unresolved"


def _resolve_text(value: str | None, resolver: DistrictResolver) -> tuple[str, str] | None:
    if not value:
        return None
    direct = resolver.resolve_name(value)
    if direct is not None:
        return direct
    for row in resolver.districts:
        candidates = [row.get("district_name"), *(row.get("aliases") or [])]
        if any(candidate and str(candidate) in value for candidate in candidates):
            return str(row["district_id"]), str(row["district_name"])
    return None


def _required_text(raw: Mapping[str, Any], field: str) -> str:
    value = clean_text(raw.get(field))
    if value is None:
        raise TransformValueError(f"{field} is required")
    return value


def _required_year(value: Any) -> str:
    text = clean_text(value)
    if text is None or not re.fullmatch(r"\d{2,3}", text):
        raise TransformValueError("year_roc must be a ROC year")
    year = int(text)
    if year <= 0:
        raise TransformValueError("year_roc must be positive")
    return str(year)


__all__ = ["transform_youth_grants"]
