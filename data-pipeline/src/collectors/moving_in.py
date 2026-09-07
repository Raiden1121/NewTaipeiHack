"""Collect village-level movement data from the household registration API."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collectors.errors import CollectorNoDataError


API_URL_TEMPLATE = (
    "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP011/{yyyymm}"
)
DEFAULT_COUNTY = "新北市"
REQUEST_TIMEOUT_SECONDS = 30
SUCCESS_RESPONSE_CODE = "OD-0101-S"

OpenURL = Callable[..., Any]


class PopulationMovementCollectorError(RuntimeError):
    """Raised when the population movement API cannot provide valid data."""


def fetch_moving(
    yyyymm: str,
    county: str = DEFAULT_COUNTY,
    town: str | None = None,
    *,
    open_url: OpenURL = urlopen,
) -> list[dict[str, str]]:
    """Fetch all ODRP011 records for one ROC month.

    Args:
        yyyymm: Five-digit Republic of China calendar month, such as ``11507``.
        county: County or city filter sent to the official API.
        town: Optional township or district filter.
        open_url: Injectable URL opener for tests; defaults to ``urllib``.

    Returns:
        Village-level records with raw string values, including movement-in and
        movement-out fields.

    Raises:
        PopulationMovementCollectorError: If validation, HTTP, JSON, or API
            validation fails.
    """

    _validate_yyyymm(yyyymm)
    if not isinstance(county, str) or not county.strip():
        raise PopulationMovementCollectorError("county must be a non-empty string")
    if town is not None and not isinstance(town, str):
        raise PopulationMovementCollectorError("town must be a string or None")

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
            raise PopulationMovementCollectorError(
                "ODRP011 totalPage changed while fetching "
                f"{yyyymm}: expected {total_pages}, got {page_total} on page {page}"
            )
        records.extend(page_records)

    return records


def _validate_yyyymm(yyyymm: str) -> None:
    if not isinstance(yyyymm, str) or re.fullmatch(r"\d{5}", yyyymm) is None:
        raise PopulationMovementCollectorError(
            "yyyymm must be a five-digit ROC calendar month, such as 11507"
        )

    month = int(yyyymm[-2:])
    if not 1 <= month <= 12:
        raise PopulationMovementCollectorError(
            "yyyymm month must be between 01 and 12"
        )


def _fetch_page(
    *,
    yyyymm: str,
    page: int,
    county: str,
    town: str | None,
    open_url: OpenURL,
) -> tuple[int, list[dict[str, str]]]:
    query = [("PAGE", str(page)), ("COUNTY", county)]
    if town is not None and town.strip():
        query.append(("TOWN", town))

    url = f"{API_URL_TEMPLATE.format(yyyymm=yyyymm)}?{urlencode(query)}"
    request = Request(url, headers={"Accept": "application/json"})

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise PopulationMovementCollectorError(
            f"ODRP011 HTTP error for {yyyymm} page {page}: {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise PopulationMovementCollectorError(
            f"ODRP011 request failed for {yyyymm} page {page}: {exc}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PopulationMovementCollectorError(
            f"ODRP011 returned invalid JSON for {yyyymm} page {page}"
        ) from exc

    return _parse_page(payload, yyyymm=yyyymm, page=page)


def _parse_page(
    payload: Any,
    *,
    yyyymm: str,
    page: int,
) -> tuple[int, list[dict[str, str]]]:
    if not isinstance(payload, dict):
        raise PopulationMovementCollectorError(
            f"ODRP011 response must be an object for {yyyymm} page {page}"
        )

    response_code = payload.get("responseCode")
    if response_code == "OD-0102-S":
        message = payload.get("responseMessage", "unknown API error")
        raise CollectorNoDataError(
            f"ODRP011 has no data for {yyyymm} page {page}: {message}"
        )
    if response_code != SUCCESS_RESPONSE_CODE:
        message = payload.get("responseMessage", "unknown API error")
        raise PopulationMovementCollectorError(
            f"ODRP011 returned {response_code!r} for {yyyymm} page {page}: {message}"
        )

    try:
        total_pages = int(payload["totalPage"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PopulationMovementCollectorError(
            f"ODRP011 response has invalid totalPage for {yyyymm} page {page}"
        ) from exc

    if total_pages < 1:
        raise PopulationMovementCollectorError(
            f"ODRP011 totalPage must be positive for {yyyymm} page {page}"
        )

    records = payload.get("responseData")
    if not isinstance(records, list):
        raise PopulationMovementCollectorError(
            f"ODRP011 responseData must be a list for {yyyymm} page {page}"
        )

    for index, record in enumerate(records):
        if not isinstance(record, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in record.items()
        ):
            raise PopulationMovementCollectorError(
                "ODRP011 responseData records must contain string keys and values "
                f"for {yyyymm} page {page} record {index}"
            )

    return total_pages, records
