"""Normalize TaiwanJobs posted salary data by New Taipei district.

The HTTP request remains owned by :mod:`job_vacancy`.  This module reuses its
29-district snapshot, keeps the source columns, and adds monthly salary
fields for downstream indicator calculations.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
import re
from statistics import median
from typing import Any

from .job_vacancy import (
    DEFAULT_COUNT,
    NEW_TAIPEI_ZIP_CODES,
    JobVacancyCollectorError,
    fetch_new_taipei_job_vacancies,
)


DEFAULT_SALARY_TYPE = "月薪"
SALARY_TYPE_FIELD = "SALARYCD"
SALARY_LOWER_FIELD = "NT_L"
SALARY_UPPER_FIELD = "NT_U"
NULL_NUMERIC_VALUES = frozenset({"", "-", "—", "－", "NA", "N/A"})

OpenURL = Callable[..., Any]


class JobVacancySalaryCollectorError(RuntimeError):
    """Raised when a posted salary record cannot be normalized safely."""


def fetch_job_posted_salaries(
    zip_codes: Mapping[str, str] = NEW_TAIPEI_ZIP_CODES,
    *,
    count: int = DEFAULT_COUNT,
    salary_type: str = DEFAULT_SALARY_TYPE,
    open_url: OpenURL | None = None,
) -> list[dict[str, Any]]:
    """Fetch and normalize current monthly salary vacancies.

    ``job_vacancy.fetch_new_taipei_job_vacancies`` performs the actual API
    calls.  Salary filtering happens locally, so this module does not issue a
    second request for the same district.
    """

    _validate_salary_type(salary_type)
    fetch_kwargs: dict[str, Any] = {"count": count}
    if open_url is not None:
        fetch_kwargs["open_url"] = open_url

    try:
        raw_records = fetch_new_taipei_job_vacancies(
            zip_codes=zip_codes,
            **fetch_kwargs,
        )
    except JobVacancyCollectorError as exc:
        raise JobVacancySalaryCollectorError(
            f"Unable to fetch TaiwanJobs salary vacancies: {exc}"
        ) from exc

    return normalize_posted_salary_records(
        raw_records,
        salary_type=salary_type,
    )


def normalize_posted_salary_records(
    records: Iterable[Mapping[str, Any]],
    *,
    salary_type: str = DEFAULT_SALARY_TYPE,
    snapshot_fetched_at: str | None = None,
) -> list[dict[str, Any]]:
    """Keep one salary category and add parsed salary fields.

    Source values are retained unchanged.  A salary midpoint is created only
    when both lower and upper bounds are numeric.
    """

    _validate_salary_type(salary_type)
    fetched_at = snapshot_fetched_at or datetime.now(timezone.utc).isoformat()
    if not isinstance(fetched_at, str) or not fetched_at.strip():
        raise JobVacancySalaryCollectorError(
            "snapshot_fetched_at must be a non-empty string or None"
        )

    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise JobVacancySalaryCollectorError(
                f"record {index} must be a mapping"
            )

        source_salary_type = _get_source_value(
            record,
            SALARY_TYPE_FIELD,
            index=index,
        )
        if _clean_text(source_salary_type) != salary_type:
            continue

        lower_raw = _get_source_value(record, SALARY_LOWER_FIELD, index=index)
        upper_raw = _get_source_value(record, SALARY_UPPER_FIELD, index=index)
        lower = _parse_salary_bound(
            lower_raw,
            field=SALARY_LOWER_FIELD,
            index=index,
        )
        upper = _parse_salary_bound(
            upper_raw,
            field=SALARY_UPPER_FIELD,
            index=index,
        )
        if lower is not None and upper is not None:
            estimate_type = "range_midpoint"
            midpoint = _coerce_number((lower + upper) / 2)
        elif lower is not None:
            estimate_type = "lower_bound"
            midpoint = None
        elif upper is not None:
            estimate_type = "upper_bound"
            midpoint = None
        else:
            estimate_type = "missing"
            midpoint = None

        enriched = dict(record)
        enriched.update(
            {
                "salary_type": salary_type,
                "salary_lower": lower,
                "salary_upper": upper,
                "salary_midpoint": midpoint,
                "salary_estimate_type": estimate_type,
                "snapshot_fetched_at": fetched_at,
            }
        )
        normalized.append(enriched)

    return normalized


def summarize_posted_salary_by_district(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Summarize normalized monthly salary records by district.

    The median is based only on complete salary ranges.  If the source query
    reached its 1,000-row limit, the median is withheld because the sample may
    be truncated.
    """

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise JobVacancySalaryCollectorError(
                f"record {index} must be a mapping"
            )
        district = record.get("district")
        if not isinstance(district, str) or not district.strip():
            raise JobVacancySalaryCollectorError(
                f"record {index} is missing collector district metadata"
            )
        grouped.setdefault(district.strip(), []).append(record)

    summary: dict[str, dict[str, Any]] = {}
    for district, district_records in grouped.items():
        values: list[int | float] = []
        query_truncated = False
        for index, record in enumerate(district_records):
            query_truncated = query_truncated or bool(
                record.get("query_truncated", False)
            )
            if "salary_midpoint" not in record:
                raise JobVacancySalaryCollectorError(
                    f"record for {district!r} is not normalized"
                )
            midpoint = record["salary_midpoint"]
            if midpoint is not None:
                if isinstance(midpoint, bool) or not isinstance(
                    midpoint,
                    (int, float),
                ):
                    raise JobVacancySalaryCollectorError(
                        f"record {index} has invalid salary_midpoint: {midpoint!r}"
                    )
                values.append(midpoint)

        complete_median = _coerce_number(median(values)) if values else None
        summary[district] = {
            "vacancy_count": len(district_records),
            "salary_valid_count": len(values),
            "salary_coverage": round(
                len(values) / len(district_records),
                6,
            ),
            "salary_median": None if query_truncated else complete_median,
            "query_truncated": query_truncated,
        }

    return summary


def _validate_salary_type(salary_type: str) -> None:
    if not isinstance(salary_type, str) or not salary_type.strip():
        raise JobVacancySalaryCollectorError(
            "salary_type must be a non-empty string"
        )


def _get_source_value(
    record: Mapping[str, Any],
    canonical_name: str,
    *,
    index: int,
) -> Any:
    for field, value in record.items():
        if _canonical_source_name(field) == canonical_name:
            return value
    raise JobVacancySalaryCollectorError(
        f"record {index} is missing source field {canonical_name}"
    )


def _canonical_source_name(field: Any) -> str:
    if not isinstance(field, str):
        return ""
    return re.split(r"[（(]", field, maxsplit=1)[0].strip()


def _parse_salary_bound(
    value: Any,
    *,
    field: str,
    index: int,
) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise JobVacancySalaryCollectorError(
            f"record {index} has invalid {field}: {value!r}"
        )
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        if text in NULL_NUMERIC_VALUES:
            return None
        try:
            number = float(text)
        except ValueError as exc:
            raise JobVacancySalaryCollectorError(
                f"record {index} has invalid {field}: {value!r}"
            ) from exc
    else:
        raise JobVacancySalaryCollectorError(
            f"record {index} has invalid {field}: {value!r}"
        )

    if number < 0:
        raise JobVacancySalaryCollectorError(
            f"record {index} has invalid {field}: {value!r}"
        )
    return _coerce_number(number)


def _coerce_number(value: float | int) -> int | float:
    rounded = round(float(value), 10)
    return int(rounded) if rounded.is_integer() else rounded


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()
