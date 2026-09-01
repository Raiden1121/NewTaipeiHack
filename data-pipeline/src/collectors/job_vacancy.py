"""Collect current TaiwanJobs vacancy records by New Taipei district."""

from __future__ import annotations

import csv
import io
import re
import ssl
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


JOB_VACANCY_URL = (
    "https://free.taiwanjobs.gov.tw/webservice_taipei/"
    "webservice.ashx"
)
DEFAULT_CITY = "31"
DEFAULT_COUNT = 1000
MAX_COUNT = 1000
REQUEST_TIMEOUT_SECONDS = 60
CITYNAME_FIELD = "CITYNAME"
JOB_PERSON_FIELD = "JOB_PERSON"
REQUIRED_SOURCE_FIELDS = frozenset({CITYNAME_FIELD, JOB_PERSON_FIELD})

# The API accepts the first three digits of the postal code.  The mapping is
# kept here because the response contains CITYNAME but does not return ZIPNO.
NEW_TAIPEI_ZIP_CODES: dict[str, str] = {
    "板橋區": "220",
    "三重區": "241",
    "中和區": "235",
    "永和區": "234",
    "新莊區": "242",
    "新店區": "231",
    "樹林區": "238",
    "鶯歌區": "239",
    "三峽區": "237",
    "淡水區": "251",
    "汐止區": "221",
    "瑞芳區": "224",
    "土城區": "236",
    "蘆洲區": "247",
    "五股區": "248",
    "泰山區": "243",
    "林口區": "244",
    "深坑區": "222",
    "石碇區": "223",
    "坪林區": "232",
    "三芝區": "252",
    "石門區": "253",
    "八里區": "249",
    "平溪區": "226",
    "雙溪區": "227",
    "貢寮區": "228",
    "金山區": "208",
    "萬里區": "207",
    "烏來區": "233",
}
ZIP_TO_DISTRICT = {
    zipno: district for district, zipno in NEW_TAIPEI_ZIP_CODES.items()
}

OpenURL = Callable[..., Any]


class JobVacancyCollectorError(RuntimeError):
    """Raised when the TaiwanJobs vacancy API returns invalid data."""


def _create_ssl_context() -> ssl.SSLContext:
    """Keep certificate and hostname checks while supporting the MOL chain."""

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        # The MOL host currently omits Subject Key Identifier.
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_job_vacancies(
    zipno: str,
    *,
    city: str = DEFAULT_CITY,
    district: str | None = None,
    count: int = DEFAULT_COUNT,
    open_url: OpenURL = _open_url,
) -> list[dict[str, Any]]:
    """Fetch current vacancy rows for one three-digit postal-code area.

    Original API columns and values are preserved.  The collector adds
    ``query_zipno``, ``district`` and ``query_truncated`` metadata so later
    aggregation can identify the query scope and a possible 1,000-row cap.
    """

    _validate_inputs(zipno=zipno, city=city, district=district, count=count)
    zipno = zipno.strip()
    city = city.strip()
    expected_district = district.strip() if district is not None else None
    if expected_district is None and city == DEFAULT_CITY:
        expected_district = ZIP_TO_DISTRICT.get(zipno)

    query = {
        "city": city,
        "zipno": zipno,
        "count": str(count),
        "T": "CSV",
    }
    request = Request(f"{JOB_VACANCY_URL}?{urlencode(query)}")
    request.add_header("Accept", "text/csv, text/plain")

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw_payload = response.read()
    except HTTPError as exc:
        raise JobVacancyCollectorError(
            f"TaiwanJobs API HTTP error for zipno={zipno}: "
            f"{exc.code} {exc.reason}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise JobVacancyCollectorError(
            f"TaiwanJobs API request failed for zipno={zipno}: {exc}"
        ) from exc

    records = _parse_csv(raw_payload)
    query_truncated = len(records) >= count
    enriched_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if expected_district is not None:
            _validate_cityname(
                _get_source_value(record, CITYNAME_FIELD, index=index),
                expected_district=expected_district,
                index=index,
            )

        enriched = dict(record)
        enriched["query_zipno"] = zipno
        enriched["district"] = expected_district or ""
        enriched["query_truncated"] = query_truncated
        enriched_records.append(enriched)

    return enriched_records


def fetch_new_taipei_job_vacancies(
    zip_codes: Mapping[str, str] = NEW_TAIPEI_ZIP_CODES,
    *,
    count: int = DEFAULT_COUNT,
    open_url: OpenURL = _open_url,
) -> list[dict[str, Any]]:
    """Fetch current vacancy rows for each configured New Taipei district."""

    _validate_zip_codes(zip_codes)
    _validate_count(count)

    records: list[dict[str, Any]] = []
    for district, zipno in zip_codes.items():
        records.extend(
            fetch_job_vacancies(
                zipno,
                city=DEFAULT_CITY,
                district=district,
                count=count,
                open_url=open_url,
            )
        )
    return records


def count_job_vacancies(records: Iterable[Mapping[str, Any]]) -> int:
    """Count vacancy rows, where each API row represents one listed vacancy."""

    return sum(1 for _ in records)


def count_job_vacancies_by_district(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    """Count listed vacancy rows by the collector's district metadata."""

    totals: dict[str, int] = {}
    for index, record in enumerate(records):
        district = _get_district(record, index=index)
        totals[district] = totals.get(district, 0) + 1
    return totals


def sum_job_person(records: Iterable[Mapping[str, Any]]) -> int:
    """Sum numeric ``JOB_PERSON`` values as vacancy positions."""

    total = 0
    for index, record in enumerate(records):
        total += _parse_job_person(
            _get_source_value(record, JOB_PERSON_FIELD, index=index),
            index=index,
        )
    return total


def sum_job_person_by_district(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    """Sum ``JOB_PERSON`` vacancy positions by district."""

    totals: dict[str, int] = {}
    for index, record in enumerate(records):
        district = _get_district(record, index=index)
        people = _parse_job_person(
            _get_source_value(record, JOB_PERSON_FIELD, index=index),
            index=index,
        )
        totals[district] = totals.get(district, 0) + people
    return totals


def _validate_inputs(
    *,
    zipno: str,
    city: str,
    district: str | None,
    count: int,
) -> None:
    if (
        not isinstance(zipno, str)
        or re.fullmatch(r"\d{3}", zipno.strip()) is None
    ):
        raise JobVacancyCollectorError(
            "zipno must be a three-digit postal code, such as 220"
        )
    if not isinstance(city, str) or not city.strip():
        raise JobVacancyCollectorError("city must be a non-empty string")
    if district is not None and (
        not isinstance(district, str) or not district.strip()
    ):
        raise JobVacancyCollectorError(
            "district must be a non-empty string or None"
        )
    _validate_count(count)


def _validate_count(count: int) -> None:
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not 1 <= count <= MAX_COUNT
    ):
        raise JobVacancyCollectorError(
            f"count must be an integer from 1 to {MAX_COUNT}"
        )


def _validate_zip_codes(zip_codes: Mapping[str, str]) -> None:
    if not isinstance(zip_codes, Mapping) or not zip_codes:
        raise JobVacancyCollectorError("zip_codes must be a non-empty mapping")
    for district, zipno in zip_codes.items():
        if not isinstance(district, str) or not district.strip():
            raise JobVacancyCollectorError(
                "zip_codes keys must be non-empty district names"
            )
        if (
            not isinstance(zipno, str)
            or re.fullmatch(r"\d{3}", zipno.strip()) is None
        ):
            raise JobVacancyCollectorError(
                f"zip code for {district!r} must be a three-digit string"
            )


def _parse_csv(raw_payload: bytes) -> list[dict[str, str]]:
    if not isinstance(raw_payload, bytes):
        raise JobVacancyCollectorError("TaiwanJobs API response must be bytes")

    text: str | None = None
    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            text = raw_payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise JobVacancyCollectorError("TaiwanJobs API returned invalid CSV encoding")
    if not text.strip():
        return []

    reader = csv.DictReader(io.StringIO(text, newline=""))
    fieldnames = reader.fieldnames
    if not fieldnames or any(
        not field or not field.strip()
        for field in fieldnames
    ):
        raise JobVacancyCollectorError(
            "TaiwanJobs API CSV is missing a valid header row"
        )

    missing_fields = {
        field
        for field in REQUIRED_SOURCE_FIELDS
        if not _has_source_field(fieldnames, field)
    }
    if missing_fields:
        raise JobVacancyCollectorError(
            "TaiwanJobs API CSV is missing fields "
            f"{sorted(missing_fields)}"
        )

    records: list[dict[str, str]] = []
    for index, record in enumerate(reader):
        if None in record or any(value is None for value in record.values()):
            raise JobVacancyCollectorError(
                f"TaiwanJobs API CSV has malformed row at index {index}"
            )
        records.append(record)
    return records


def _validate_cityname(
    value: Any,
    *,
    expected_district: str,
    index: int,
) -> None:
    if not isinstance(value, str) or expected_district not in value:
        raise JobVacancyCollectorError(
            f"TaiwanJobs API CITYNAME at row {index} does not match "
            f"district {expected_district!r}: {value!r}"
        )


def _has_source_field(fields: Iterable[Any], canonical_name: str) -> bool:
    return any(
        _canonical_source_name(field) == canonical_name
        for field in fields
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
    raise JobVacancyCollectorError(
        f"record {index} is missing source field {canonical_name}"
    )


def _canonical_source_name(field: Any) -> str:
    if not isinstance(field, str):
        return ""
    return re.split(r"[（(]", field, maxsplit=1)[0].strip()


def _get_district(record: Mapping[str, Any], *, index: int) -> str:
    district = record.get("district")
    if not isinstance(district, str) or not district.strip():
        raise JobVacancyCollectorError(
            f"record {index} is missing collector district metadata"
        )
    return district.strip()


def _parse_job_person(value: Any, *, index: int) -> int:
    if isinstance(value, bool):
        raise JobVacancyCollectorError(
            f"record {index} has invalid {JOB_PERSON_FIELD}: {value!r}"
        )
    if isinstance(value, int):
        if value < 0:
            raise JobVacancyCollectorError(
                f"record {index} has invalid {JOB_PERSON_FIELD}: {value!r}"
            )
        return value
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if normalized.isdigit():
            return int(normalized)
    raise JobVacancyCollectorError(
        f"record {index} has invalid {JOB_PERSON_FIELD}: {value!r}"
    )
