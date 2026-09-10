"""Normalize join.gov proposal rows without calculating analytics scores."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Iterable, Mapping

from analytics.config import YouthTopicRules

from .common import (
    TransformValueError,
    build_common_metadata,
    build_source_record_id,
    clean_text,
    parse_int,
)
from .contracts import TransformResult
from .quality import QualityCollector


def transform_join_proposals(
    records: Iterable[Mapping[str, Any]],
    *,
    fetched_at: str | None = None,
    rules: YouthTopicRules,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        try:
            proposal_id = _required_text(raw, "proposal_id")
            year_roc, gregorian_year = _record_year(raw)
            submitted_at = clean_text(raw.get("submitted_at"))
            title = clean_text(raw.get("title"))
            content = clean_text(raw.get("content"))
            endorsement_count = parse_int(
                raw.get("endorsement_count"), field="endorsement_count"
            )
        except TransformValueError as exc:
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue

        proxy, reasons = _youth_proxy(raw, rules)
        curated = build_common_metadata(
            dataset="join_proposals",
            source="join_gov_public_policy_platform",
            source_record_id=f"join_proposals:{proposal_id}",
            geo_level="national",
            district_id=None,
            district_name=None,
            period_start=f"{gregorian_year}-01-01",
            period_end=f"{gregorian_year}-12-31",
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
                "proposal_id": proposal_id,
                "proposal_url": clean_text(raw.get("proposal_url")),
                "title": title,
                "content": content,
                "interest_impact": clean_text(raw.get("interest_impact")),
                "endorsement_count": endorsement_count,
                "endorsement_threshold": _optional_int(raw.get("endorsement_threshold")),
                "submitted_at": submitted_at,
                "published_at": clean_text(raw.get("published_at")),
                "status": clean_text(raw.get("status")),
                "agency": clean_text(raw.get("agency")),
                "category": clean_text(raw.get("category")),
                "year_roc": year_roc,
                "youth_topic_proxy": proxy,
                "proxy_reasons": reasons,
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _youth_proxy(raw: Mapping[str, Any], rules: YouthTopicRules) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    agency = clean_text(raw.get("agency")) or ""
    combined = " ".join(
        value
        for value in (
            clean_text(raw.get("title")),
            clean_text(raw.get("content")),
            clean_text(raw.get("category")),
        )
        if value
    )
    for agency_name in rules.proxy_agencies:
        if agency_name in agency and f"agency:{agency_name}" not in reasons:
            reasons.append(f"agency:{agency_name}")
    for keyword in rules.proxy_keywords:
        if keyword in combined and f"keyword:{keyword}" not in reasons:
            reasons.append(f"keyword:{keyword}")
    return bool(reasons), reasons


def _record_year(raw: Mapping[str, Any]) -> tuple[str, int]:
    raw_year = clean_text(raw.get("year_roc"))
    if raw_year:
        return _coerce_year(raw_year)
    date_value = clean_text(raw.get("submitted_at"))
    if not date_value:
        raise TransformValueError("submitted_at/year_roc is required")
    match = re.search(r"(\d{3})\d{4}", date_value)
    if match:
        return _coerce_year(match.group(1))
    match = re.search(r"(\d{2,3})\s*[年./-]", date_value)
    if match:
        return _coerce_year(match.group(1))
    try:
        year = datetime.fromisoformat(date_value.replace("Z", "+00:00")).year
    except ValueError as exc:
        raise TransformValueError("submitted_at is not a supported date") from exc
    return str(year - 1911), year


def _coerce_year(value: str) -> tuple[str, int]:
    if not value.isdigit():
        raise TransformValueError("year_roc must be numeric")
    number = int(value)
    if number > 1911:
        return str(number - 1911), number
    if number <= 0:
        raise TransformValueError("year_roc must be positive")
    return str(number), number + 1911


def _required_text(raw: Mapping[str, Any], field: str) -> str:
    value = clean_text(raw.get(field))
    if value is None:
        raise TransformValueError(f"{field} is required")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    match = re.search(r"\d[\d,]*", str(value))
    return int(match.group(0).replace(",", "")) if match else None

