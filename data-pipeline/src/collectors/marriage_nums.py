"""Collect monthly marriage-pair records from the household registration API."""

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
    "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP003/{yyyymm}"
)
DEFAULT_COUNTY = "新北市"
REQUEST_TIMEOUT_SECONDS = 30
SUCCESS_RESPONSE_CODE = "OD-0101-S"
REQUIRED_FIELDS = frozenset(
    {"statistic_yyymm", "site_id", "village", "marry_pair"}
)

OpenURL = Callable[..., Any]


class MarriageNumsCollectorError(RuntimeError):
    """Raised when the marriage-pair API cannot provide valid data."""


def fetch_marriage_numbers(
    yyy: str,
    county: str | None = DEFAULT_COUNTY,
    town: str | None = None,
    *,
    open_url: OpenURL = urlopen,
) -> list[dict[str, str]]:
    """Fetch all 12 monthly ODRP003 records for one ROC year.

    The API is monthly and village-level.  This function calls every month of
    the requested year, sends optional county/town filters to the API, and
    keeps the original records for later aggregation.
    """

    _validate_inputs(yyy=yyy, county=county, town=town)

    records: list[dict[str, str]] = []
    for month in range(1, 13):
        yyyymm = f"{yyy}{month:02d}"
        month_records = _fetch_month(
            yyyymm=yyyymm,
            county=county,
            town=town,
            open_url=open_url,
        )
        if not month_records:
            raise MarriageNumsCollectorError(
                f"ODRP003 returned no records for {yyyymm}; "
                "annual data would be incomplete"
            )
        records.extend(month_records)

    return records


def aggregate_marriage_pairs(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    """Sum village-level ``marry_pair`` values by district.

    The input is expected to contain one or more monthly records.  The month
    is part of the duplicate key, so the same village can be summed across all
    12 months while an accidental duplicate within one month is rejected.
    """

    totals: dict[str, int] = {}
    seen_keys: set[tuple[str, str, str]] = set()

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise MarriageNumsCollectorError(
                f"record {index} must be a JSON object"
            )

        missing_fields = REQUIRED_FIELDS.difference(record)
        if missing_fields:
            raise MarriageNumsCollectorError(
                f"record {index} is missing fields {sorted(missing_fields)}"
            )

        yyyymm = record["statistic_yyymm"]
        site_id = record["site_id"]
        village = record["village"]
        if not all(
            isinstance(value, str) and value.strip()
            for value in (yyyymm, site_id, village)
        ):
            raise MarriageNumsCollectorError(
                f"record {index} has invalid month, site_id, or village"
            )

        key = (yyyymm, site_id, village)
        if key in seen_keys:
            raise MarriageNumsCollectorError(
                "duplicate marriage row for "
                f"statistic_yyymm={yyyymm!r}, site_id={site_id!r}, "
                f"village={village!r}"
            )
        seen_keys.add(key)

        count = _parse_non_negative_int(
            record["marry_pair"],
            index=index,
            field="marry_pair",
        )
        totals[site_id] = totals.get(site_id, 0) + count

    return totals


def _validate_inputs(
    *,
    yyy: str,
    county: str | None,
    town: str | None,
) -> None:
    if not isinstance(yyy, str) or re.fullmatch(r"\d{3}", yyy) is None:
        raise MarriageNumsCollectorError(
            "yyy must be a three-digit ROC calendar year, such as 114"
        )
    if county is not None and (not isinstance(county, str) or not county.strip()):
        raise MarriageNumsCollectorError("county must be a non-empty string or None")
    if town is not None and (not isinstance(town, str) or not town.strip()):
        raise MarriageNumsCollectorError("town must be a non-empty string or None")


def _fetch_month(
    *,
    yyyymm: str,
    county: str | None,
    town: str | None,
    open_url: OpenURL,
) -> list[dict[str, str]]:
    total_pages, records = _fetch_page(
        yyyymm=yyyymm,
        page=1,
        county=county,
        town=town,
        open_url=open_url,
    )

    for page in range(2, total_pages + 1):
        page_total, page_records = _fetch_page(
            yyyymm=yyyymm,
            page=page,
            county=county,
            town=town,
            open_url=open_url,
        )
        if page_total != total_pages:
            raise MarriageNumsCollectorError(
                "ODRP003 totalPage changed while fetching "
                f"{yyyymm}: expected {total_pages}, got {page_total} on page {page}"
            )
        records.extend(page_records)

    return [
        record
        for record in records
        if _matches_scope(record, county=county, town=town)
    ]


def _matches_scope(
    record: Mapping[str, str],
    *,
    county: str | None,
    town: str | None,
) -> bool:
    site_id = record["site_id"]
    if county is not None and not site_id.startswith(county.strip()):
        return False
    if town is not None and not site_id.endswith(town.strip()):
        return False
    return True


def _fetch_page(
    *,
    yyyymm: str,
    page: int,
    county: str | None,
    town: str | None,
    open_url: OpenURL,
) -> tuple[int, list[dict[str, str]]]:
    query = [("PAGE", str(page))]
    if county is not None:
        query.append(("COUNTY", county.strip()))
    if town is not None:
        query.append(("TOWN", town.strip()))

    url = f"{API_URL_TEMPLATE.format(yyyymm=yyyymm)}?{urlencode(query)}"
    request = Request(url, headers={"Accept": "application/json"})

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise MarriageNumsCollectorError(
            f"ODRP003 HTTP error for {yyyymm} page {page}: {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise MarriageNumsCollectorError(
            f"ODRP003 request failed for {yyyymm} page {page}: {exc}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarriageNumsCollectorError(
            f"ODRP003 returned invalid JSON for {yyyymm} page {page}"
        ) from exc

    return _parse_page(payload, yyyymm=yyyymm, page=page)


def _parse_page(
    payload: Any,
    *,
    yyyymm: str,
    page: int,
) -> tuple[int, list[dict[str, str]]]:
    if not isinstance(payload, dict):
        raise MarriageNumsCollectorError(
            f"ODRP003 response must be an object for {yyyymm} page {page}"
        )

    response_code = payload.get("responseCode")
    if response_code == "OD-0102-S":
        message = payload.get("responseMessage", "unknown API error")
        raise CollectorNoDataError(
            f"ODRP003 has no data for {yyyymm} page {page}: {message}"
        )
    if response_code != SUCCESS_RESPONSE_CODE:
        message = payload.get("responseMessage", "unknown API error")
        raise MarriageNumsCollectorError(
            f"ODRP003 returned {response_code!r} for {yyyymm} page {page}: {message}"
        )

    try:
        total_pages = int(payload["totalPage"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MarriageNumsCollectorError(
            f"ODRP003 response has invalid totalPage for {yyyymm} page {page}"
        ) from exc

    if total_pages < 1:
        raise MarriageNumsCollectorError(
            f"ODRP003 totalPage must be positive for {yyyymm} page {page}"
        )

    records = payload.get("responseData")
    if not isinstance(records, list):
        raise MarriageNumsCollectorError(
            f"ODRP003 responseData must be a list for {yyyymm} page {page}"
        )

    for index, record in enumerate(records):
        if not isinstance(record, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in record.items()
        ):
            raise MarriageNumsCollectorError(
                "ODRP003 responseData records must contain string keys and values "
                f"for {yyyymm} page {page} record {index}"
            )

        missing_fields = REQUIRED_FIELDS.difference(record)
        if missing_fields:
            raise MarriageNumsCollectorError(
                "ODRP003 responseData record is missing fields "
                f"{sorted(missing_fields)} for {yyyymm} page {page}"
            )
        if record["statistic_yyymm"] != yyyymm:
            raise MarriageNumsCollectorError(
                "ODRP003 responseData record statistic_yyymm does not match "
                f"requested month {yyyymm}: {record['statistic_yyymm']!r}"
            )
        _parse_non_negative_int(
            record["marry_pair"],
            index=index,
            field="marry_pair",
        )

    return total_pages, records


def _parse_non_negative_int(value: Any, *, index: int, field: str) -> int:
    if isinstance(value, bool):
        raise MarriageNumsCollectorError(
            f"record {index} has invalid {field}: {value!r}"
        )

    if isinstance(value, int):
        if value >= 0:
            return value
    elif isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if normalized.isdigit():
            return int(normalized)

    raise MarriageNumsCollectorError(
        f"record {index} has invalid {field}: {value!r}"
    )
