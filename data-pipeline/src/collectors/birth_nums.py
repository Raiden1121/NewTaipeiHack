"""Collect district-level birth records from the household registration API."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collectors.errors import CollectorNoDataError


API_URL_TEMPLATE = (
    "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP056/{yyy}"
)
DEFAULT_COUNTY = "新北市"
REQUEST_TIMEOUT_SECONDS = 30
SUCCESS_RESPONSE_CODE = "OD-0101-S"
MIN_YOUNG_AGE = 18
MAX_YOUNG_AGE = 35
TOTAL_SEX_VALUES = ("總計", "合計")
SEX_VALUES = frozenset({"男", "女", *TOTAL_SEX_VALUES})
REQUIRED_FIELDS = frozenset(
    {
        "statistic_yyy",
        "according",
        "site_id",
        "mother_age",
        "birth_sex",
        "birth_count",
    }
)
FIELD_ALIASES = {
    "statistic_yyy": "統計年度",
    "according": "按照別",
    "site_id": "區域別",
    "mother_age": "生母年齡",
    "birth_sex": "出生者性別",
    "birth_count": "嬰兒出生數",
}
OPEN_ENDED_AGE_LABELS = frozenset({"未滿15歲", "50歲以上"})

OpenURL = Callable[..., Any]


class BirthNumsCollectorError(RuntimeError):
    """Raised when the birth statistics API cannot provide valid data."""


def fetch_birth_numbers(
    yyy: str,
    county: str | None = DEFAULT_COUNTY,
    *,
    open_url: OpenURL = urlopen,
) -> list[dict[str, str]]:
    """Fetch one ROC statistical year and optionally keep one county.

    ODRP056 returns all areas for a year and exposes pagination through the
    ``PAGE`` query parameter.  County filtering is applied locally by matching
    the ``site_id`` prefix and excluding a possible county aggregate row.
    Returned records keep the original field names and string values.
    """

    _validate_yyy(yyy)
    if county is not None and (not isinstance(county, str) or not county.strip()):
        raise BirthNumsCollectorError("county must be a non-empty string or None")

    total_pages, records = _fetch_page(
        yyy=yyy,
        page=1,
        open_url=open_url,
    )

    for page in range(2, total_pages + 1):
        page_total, page_records = _fetch_page(
            yyy=yyy,
            page=page,
            open_url=open_url,
        )
        if page_total != total_pages:
            raise BirthNumsCollectorError(
                "ODRP056 totalPage changed while fetching "
                f"{yyy}: expected {total_pages}, got {page_total} on page {page}"
            )
        records.extend(page_records)

    if county is None:
        return records

    county_prefix = county.strip()
    return [
        record
        for record in records
        if record["site_id"].startswith(county_prefix)
        and record["site_id"] != county_prefix
    ]


def aggregate_young_births(
    records: Iterable[Mapping[str, Any]],
    *,
    min_age: int = MIN_YOUNG_AGE,
    max_age: int = MAX_YOUNG_AGE,
) -> dict[str, int]:
    """Sum exact mother ages 18 through 35 by district.

    ODRP056 has one row per single mother age and baby sex.  Male and female
    rows are summed.  If the source also provides a ``總計`` or ``合計`` sex
    row, that row is used for the age instead, preventing double counting.
    """

    _validate_age_range(min_age=min_age, max_age=max_age)
    age_sex_counts: dict[tuple[str, int], dict[str, int]] = {}
    seen_keys: set[tuple[str, int, str]] = set()

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise BirthNumsCollectorError(
                f"record {index} must be a JSON object"
            )

        age = _parse_single_age(record.get("mother_age"), index=index)
        if age is None or not min_age <= age <= max_age:
            continue

        site_id = record.get("site_id")
        if not isinstance(site_id, str) or not site_id.strip():
            raise BirthNumsCollectorError(f"record {index} has invalid site_id")

        birth_sex = record.get("birth_sex")
        if birth_sex not in SEX_VALUES:
            raise BirthNumsCollectorError(
                f"record {index} has invalid birth_sex: {birth_sex!r}"
            )

        key = (site_id, age, birth_sex)
        if key in seen_keys:
            raise BirthNumsCollectorError(
                f"duplicate birth row for site_id={site_id!r}, "
                f"mother_age={age}, birth_sex={birth_sex!r}"
            )
        seen_keys.add(key)

        count = _parse_birth_count(record.get("birth_count"), index=index)
        age_sex_counts.setdefault((site_id, age), {})[birth_sex] = count

    totals: dict[str, int] = {}
    for (site_id, _age), sex_counts in age_sex_counts.items():
        total_sex = next(
            (sex for sex in TOTAL_SEX_VALUES if sex in sex_counts),
            None,
        )
        if total_sex is not None:
            count = sex_counts[total_sex]
        else:
            count = sum(sex_counts.get(sex, 0) for sex in ("男", "女"))
        totals[site_id] = totals.get(site_id, 0) + count

    return totals


def _validate_yyy(yyy: str) -> None:
    if not isinstance(yyy, str) or re.fullmatch(r"\d{3}", yyy) is None:
        raise BirthNumsCollectorError(
            "yyy must be a three-digit ROC calendar year, such as 114"
        )


def _validate_age_range(*, min_age: int, max_age: int) -> None:
    if (
        isinstance(min_age, bool)
        or isinstance(max_age, bool)
        or not isinstance(min_age, int)
        or not isinstance(max_age, int)
        or not 0 <= min_age <= max_age <= 120
    ):
        raise BirthNumsCollectorError(
            "min_age and max_age must be integers from 0 to 120, with min_age <= max_age"
        )


def _parse_single_age(value: Any, *, index: int) -> int | None:
    if not isinstance(value, str):
        raise BirthNumsCollectorError(
            f"record {index} has invalid mother_age: {value!r}"
        )

    normalized = value.strip()
    if normalized in OPEN_ENDED_AGE_LABELS:
        return None

    match = re.fullmatch(r"(\d{1,3})歲", normalized)
    if match is None:
        raise BirthNumsCollectorError(
            f"record {index} has invalid mother_age: {value!r}"
        )
    return int(match.group(1))


def _parse_birth_count(value: Any, *, index: int) -> int:
    if isinstance(value, bool):
        raise BirthNumsCollectorError(
            f"record {index} has invalid birth_count: {value!r}"
        )

    if isinstance(value, int):
        if value >= 0:
            return value
    elif isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if normalized.isdigit():
            return int(normalized)

    raise BirthNumsCollectorError(
        f"record {index} has invalid birth_count: {value!r}"
    )


def _fetch_page(
    *,
    yyy: str,
    page: int,
    open_url: OpenURL,
) -> tuple[int, list[dict[str, str]]]:
    url = f"{API_URL_TEMPLATE.format(yyy=yyy)}?{urlencode({'PAGE': page})}"
    request = Request(url, headers={"Accept": "application/json"})

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise BirthNumsCollectorError(
            f"ODRP056 HTTP error for {yyy} page {page}: {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise BirthNumsCollectorError(
            f"ODRP056 request failed for {yyy} page {page}: {exc}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BirthNumsCollectorError(
            f"ODRP056 returned invalid JSON for {yyy} page {page}"
        ) from exc

    return _parse_page(payload, yyy=yyy, page=page)


def _parse_page(
    payload: Any,
    *,
    yyy: str,
    page: int,
) -> tuple[int, list[dict[str, str]]]:
    if not isinstance(payload, dict):
        raise BirthNumsCollectorError(
            f"ODRP056 response must be an object for {yyy} page {page}"
        )

    response_code = payload.get("responseCode")
    if response_code == "OD-0102-S":
        message = payload.get("responseMessage", "unknown API error")
        raise CollectorNoDataError(
            f"ODRP056 has no data for {yyy} page {page}: {message}"
        )
    if response_code != SUCCESS_RESPONSE_CODE:
        message = payload.get("responseMessage", "unknown API error")
        raise BirthNumsCollectorError(
            f"ODRP056 returned {response_code!r} for {yyy} page {page}: {message}"
        )

    try:
        total_pages = int(payload["totalPage"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BirthNumsCollectorError(
            f"ODRP056 response has invalid totalPage for {yyy} page {page}"
        ) from exc

    if total_pages < 1:
        raise BirthNumsCollectorError(
            f"ODRP056 totalPage must be positive for {yyy} page {page}"
        )

    records = payload.get("responseData")
    if not isinstance(records, list):
        raise BirthNumsCollectorError(
            f"ODRP056 responseData must be a list for {yyy} page {page}"
        )

    enriched_records: list[dict[str, str]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in record.items()
        ):
            raise BirthNumsCollectorError(
                "ODRP056 responseData records must contain string keys and values "
                f"for {yyy} page {page} record {index}"
            )

        enriched_record = dict(record)
        for canonical_field, source_field in FIELD_ALIASES.items():
            if source_field in enriched_record:
                enriched_record.setdefault(
                    canonical_field,
                    enriched_record[source_field],
                )

        missing_fields = REQUIRED_FIELDS.difference(enriched_record)
        if missing_fields:
            raise BirthNumsCollectorError(
                "ODRP056 responseData record is missing fields "
                f"{sorted(missing_fields)} for {yyy} page {page}"
            )
        if enriched_record["statistic_yyy"] != yyy:
            raise BirthNumsCollectorError(
                "ODRP056 responseData record statistic_yyy does not match "
                f"requested year {yyy}: {enriched_record['statistic_yyy']!r}"
            )
        enriched_records.append(enriched_record)

    return total_pages, enriched_records
