"""Collect current TaiwanJobs vacancy records by New Taipei district."""

from __future__ import annotations

import csv
import hashlib
import io
import json
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
COUNTY_CITYNAMES = frozenset({"新北市不限", "新北市"})
COUNTY_DEDUPLICATION_EXCLUDED_FIELDS = frozenset(
    {
        "query_zipno",
        "district",
        "query_truncated",
        "query_filtered_row_count",
        "query_warnings",
        "query_observations",
        "geo_scope",
    }
)
CROSS_COUNTY_CITYNAME_WARNING = "cross_county_cityname_filtered"
DISTRICT_MISMATCH_WARNING = "query_district_mismatch_filtered"
OTHER_COUNTY_CITYNAME_PREFIXES = frozenset(
    {
        "臺北市", "台北市", "桃園市", "臺中市", "台中市", "臺南市", "台南市",
        "高雄市", "基隆市", "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣",
        "南投縣", "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣",
        "臺東縣", "台東縣", "澎湖縣", "金門縣", "連江縣",
    }
)

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
    ``query_zipno``, ``district``, ``geo_scope`` and ``query_truncated``
    metadata so later aggregation can identify query provenance, geography,
    and a possible 1,000-row cap.
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
    cityname_errors: list[tuple[JobVacancyCollectorError, str]] = []
    for index, record in enumerate(records):
        geo_scope = "district"
        if expected_district is not None:
            cityname_value = _get_source_value(
                record,
                CITYNAME_FIELD,
                index=index,
            )
            try:
                geo_scope = _validate_cityname(
                    cityname_value,
                    expected_district=expected_district,
                    index=index,
                )
            except JobVacancyCollectorError as exc:
                warning = _filtered_cityname_warning(cityname_value)
                if warning is None:
                    raise
                cityname_errors.append((exc, warning))
                continue

        enriched = dict(record)
        enriched["query_zipno"] = zipno
        enriched["district"] = expected_district if geo_scope == "district" else ""
        enriched["geo_scope"] = geo_scope
        enriched["query_truncated"] = query_truncated
        enriched_records.append(enriched)

    if records and not enriched_records and cityname_errors:
        raise cityname_errors[0][0]

    filtered_row_count = len(cityname_errors)
    query_warnings = list(dict.fromkeys(warning for _, warning in cityname_errors))
    for enriched in enriched_records:
        enriched["query_filtered_row_count"] = filtered_row_count
        enriched["query_warnings"] = list(query_warnings)
        enriched["query_observations"] = [
            {
                "query_zipno": zipno,
                "query_filtered_row_count": filtered_row_count,
                "query_warnings": list(query_warnings),
                "query_truncated": query_truncated,
            }
        ]

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
    return _deduplicate_county_rows(records)


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
) -> str:
    if not isinstance(value, str):
        raise JobVacancyCollectorError(
            f"TaiwanJobs API CITYNAME at row {index} does not match "
            f"district {expected_district!r}: {value!r}"
        )
    cityname = value.strip()
    if cityname in COUNTY_CITYNAMES:
        return "county"
    if cityname == f"新北市{expected_district}":
        return "district"
    raise JobVacancyCollectorError(
        f"TaiwanJobs API CITYNAME at row {index} does not match "
        f"district {expected_district!r}: {value!r}"
    )


def _filtered_cityname_warning(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cityname = value.strip()
    if any(
        cityname.startswith(prefix)
        for prefix in OTHER_COUNTY_CITYNAME_PREFIXES
    ):
        return CROSS_COUNTY_CITYNAME_WARNING
    if cityname in {
        f"新北市{district}"
        for district in NEW_TAIPEI_ZIP_CODES
    }:
        return DISTRICT_MISMATCH_WARNING
    return None


def _deduplicate_county_rows(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    county_records_by_key: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("geo_scope") != "county":
            deduplicated.append(record)
            continue
        record_key = _county_record_key(record)
        existing = county_records_by_key.get(record_key)
        if existing is None:
            county_records_by_key[record_key] = record
            deduplicated.append(record)
            continue
        _merge_county_query_metadata(existing, record)
    return deduplicated


def _merge_county_query_metadata(
    target: dict[str, Any],
    duplicate: Mapping[str, Any],
) -> None:
    observations = target.setdefault("query_observations", [])
    incoming = duplicate.get("query_observations", [])
    if not isinstance(observations, list) or not isinstance(incoming, list):
        raise JobVacancyCollectorError("county query observations must be lists")

    seen = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        for item in observations
    }
    for item in incoming:
        serialized = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if serialized not in seen:
            observations.append(item)
            seen.add(serialized)

    target["query_truncated"] = any(
        bool(item.get("query_truncated", False))
        for item in observations
        if isinstance(item, Mapping)
    )
    target["query_filtered_row_count"] = sum(
        int(item.get("query_filtered_row_count", 0))
        for item in observations
        if isinstance(item, Mapping)
    )
    target["query_warnings"] = list(
        dict.fromkeys(
            warning
            for item in observations
            if isinstance(item, Mapping)
            for warning in item.get("query_warnings", [])
            if isinstance(warning, str)
        )
    )


def _county_record_key(record: Mapping[str, Any]) -> str:
    source_fields = {
        field: value
        for field, value in record.items()
        if field not in COUNTY_DEDUPLICATION_EXCLUDED_FIELDS
    }
    serialized = json.dumps(
        source_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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
