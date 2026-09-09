"""Primitive cleaners and canonical metadata validation."""

from __future__ import annotations

import math
import re
import unicodedata
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


MISSING_TOKENS = frozenset({"", "-", "—", "－", "NA", "N/A", "無", "面議"})
GEO_LEVELS = frozenset({"district", "county", "national", "organization"})
PERIOD_TYPES = frozenset({"day", "month", "year", "snapshot"})
AGE_SCOPES = frozenset(
    {
        "exact_18_35",
        "derived_18_35",
        "official_age_group_proxy",
        "all_ages",
        "not_age_specific",
    }
)
YOUTH_ELIGIBILITY = frozenset({"eligible", "proxy_only", "context_only"})
_ELIGIBILITY_BY_AGE_SCOPE = {
    "exact_18_35": "eligible",
    "derived_18_35": "eligible",
    "official_age_group_proxy": "proxy_only",
    "all_ages": "context_only",
    "not_age_specific": "context_only",
}


class TransformValueError(ValueError):
    """A source value cannot be represented by the curated contract."""


def get_source_value(record: Mapping[str, Any], key: str) -> Any:
    """Read a source field that may have a UTF-8 BOM on its first key."""

    if key in record:
        return record[key]
    return record.get(f"\ufeff{key}")


def build_source_record_id(dataset: str, index: int, record: dict[str, Any]) -> str:
    """Create a stable local ID without assuming a source-specific primary key."""

    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"{dataset}:{digest}"


def clean_text(value: Any) -> str | None:
    """Normalize text while preserving missing source values as ``None``."""

    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if text.upper() in MISSING_TOKENS:
        return None
    return text


def parse_int(value: Any, *, field: str, allow_none: bool = True) -> int | None:
    """Parse a non-negative integer without silently rounding decimals."""

    text = clean_text(value)
    if text is None:
        if allow_none:
            return None
        raise TransformValueError(f"{field} is required")
    if isinstance(value, bool):
        raise TransformValueError(f"{field} must be an integer")
    normalized = text.replace(",", "")
    if not re.fullmatch(r"\+?\d+", normalized):
        raise TransformValueError(f"{field} must be a non-negative integer: {value!r}")
    parsed = int(normalized)
    if parsed < 0:
        raise TransformValueError(f"{field} must be non-negative")
    return parsed


def parse_decimal(value: Any, *, field: str, allow_none: bool = True) -> float | None:
    """Parse a finite, non-negative decimal number."""

    text = clean_text(value)
    if text is None:
        if allow_none:
            return None
        raise TransformValueError(f"{field} is required")
    if isinstance(value, bool):
        raise TransformValueError(f"{field} must be numeric")
    try:
        parsed = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise TransformValueError(f"{field} must be numeric: {value!r}") from exc
    if not parsed.is_finite() or parsed < 0:
        raise TransformValueError(f"{field} must be a finite non-negative number")
    result = float(parsed)
    if not math.isfinite(result):
        raise TransformValueError(f"{field} must be finite")
    return result


def parse_roc_year(value: Any, *, field: str) -> str:
    text = clean_text(value)
    if text is None or not re.fullmatch(r"\d{2,3}", text):
        raise TransformValueError(f"{field} must be a ROC year")
    roc_year = int(text)
    if roc_year <= 0:
        raise TransformValueError(f"{field} must be a positive ROC year")
    return str(roc_year + 1911)


def parse_roc_month(value: Any, *, field: str) -> str:
    text = clean_text(value)
    if text is None or not re.fullmatch(r"\d{5}", text):
        raise TransformValueError(f"{field} must be a five-digit ROC month")
    year = int(text[:3]) + 1911
    month = int(text[3:])
    if not 1 <= month <= 12:
        raise TransformValueError(f"{field} contains an invalid month")
    return f"{year:04d}-{month:02d}"


def parse_roc_date(value: Any, *, field: str) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    if not re.fullmatch(r"\d{7}", text):
        return None
    try:
        parsed = date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:7]))
    except ValueError as exc:
        raise TransformValueError(f"{field} contains an invalid ROC date") from exc
    return parsed.isoformat()


def build_common_metadata(
    *,
    dataset: str,
    source: str,
    source_record_id: str | None,
    geo_level: str,
    district_id: str | None,
    district_name: str | None,
    period_start: str | None,
    period_end: str | None,
    period_type: str | None,
    metric_id: str | None,
    value: int | float | None,
    unit: str | None,
    age_scope: str,
    age_min: int | None,
    age_max: int | None,
    youth_eligibility: str,
    fetched_at: str | None,
    quality_flags: list[str] | None = None,
) -> dict[str, Any]:
    """Build and validate the fields shared by every curated record."""

    if geo_level not in GEO_LEVELS:
        raise TransformValueError(f"unsupported geo_level: {geo_level}")
    if period_type is not None and period_type not in PERIOD_TYPES:
        raise TransformValueError(f"unsupported period_type: {period_type}")
    if age_scope not in AGE_SCOPES:
        raise TransformValueError(f"unsupported age_scope: {age_scope}")
    if youth_eligibility not in YOUTH_ELIGIBILITY:
        raise TransformValueError(f"unsupported youth_eligibility: {youth_eligibility}")
    expected = _ELIGIBILITY_BY_AGE_SCOPE[age_scope]
    if youth_eligibility != expected:
        raise TransformValueError(
            f"{age_scope} requires youth_eligibility={expected}, got {youth_eligibility}"
        )
    if (age_min is None) != (age_max is None):
        raise TransformValueError("age_min and age_max must be provided together")
    if age_min is not None and age_min > age_max:
        raise TransformValueError("age_min cannot exceed age_max")
    if age_scope in {"exact_18_35", "derived_18_35"} and (age_min, age_max) != (18, 35):
        raise TransformValueError(f"{age_scope} requires inclusive ages 18 through 35")

    return {
        "dataset": dataset,
        "source": source,
        "source_record_id": source_record_id,
        "geo_level": geo_level,
        "district_id": district_id,
        "district_name": district_name,
        "period_start": period_start,
        "period_end": period_end,
        "period_type": period_type,
        "metric_id": metric_id,
        "value": value,
        "unit": unit,
        "age_scope": age_scope,
        "age_min": age_min,
        "age_max": age_max,
        "youth_eligibility": youth_eligibility,
        "fetched_at": fetched_at,
        "quality_flags": list(quality_flags or []),
    }
