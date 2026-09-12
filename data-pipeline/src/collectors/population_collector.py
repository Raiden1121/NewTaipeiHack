"""Collect village-level population data from the household registration API."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collectors.errors import CollectorNoDataError

from .contracts import CollectedPayload
from .historical_population import _open_url as _historical_open_url
from .historical_population import fetch_historical_population


API_URL_TEMPLATE = (
    "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP014/{yyyymm}"
)
DEFAULT_COUNTY = "新北市"
REQUEST_TIMEOUT_SECONDS = 30
SUCCESS_RESPONSE_CODE = "OD-0101-S"

OpenURL = Callable[..., Any]


class PopulationCollectorError(RuntimeError):
    """Raised when the population API cannot provide valid data."""


def fetch_population(
    yyyymm: str,
    county: str | None = DEFAULT_COUNTY,
    town: str | None = None,
    *,
    open_url: OpenURL = urlopen,
) -> list[dict[str, str]]:
    """Fetch all ODRP014 records for one ROC month.

    Args:
        yyyymm: Five-digit Republic of China calendar month, such as ``11507``.
        county: County or city filter sent to the official API. Pass ``None``
            to omit the filter and fetch nationwide records.
        town: Optional township or district filter.
        open_url: Injectable URL opener for tests; defaults to ``urllib``.

    Returns:
        The API's village-level ``responseData`` records, preserving raw strings.

    Raises:
        PopulationCollectorError: If validation, HTTP, JSON, or API validation
            fails.
    """

    _validate_yyyymm(yyyymm)
    if county is not None and (not isinstance(county, str) or not county.strip()):
        raise PopulationCollectorError("county must be a non-empty string")

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
            raise PopulationCollectorError(
                "ODRP014 totalPage changed while fetching "
                f"{yyyymm}: expected {total_pages}, got {page_total} on page {page}"
            )
        records.extend(page_records)

    return records


def fetch_population_for_period(
    yyyymm: str,
    county: str | None = DEFAULT_COUNTY,
    town: str | None = None,
    *,
    open_url: OpenURL | None = None,
) -> list[dict[str, str]] | CollectedPayload:
    """Fetch population using ODRP014 or a registered historical archive.

    The historical adapter returns a :class:`CollectedPayload` so the
    pipeline can preserve the downloaded official ZIP alongside normalized
    records.  Current ODRP014 behavior remains unchanged for all other months.
    """

    if yyyymm == "10312" and town is None:
        return fetch_historical_population(
            yyyymm,
            county=county,
            open_url=_historical_open_url if open_url is None else open_url,
        )
    return fetch_population(
        yyyymm,
        county=county,
        town=town,
        open_url=urlopen if open_url is None else open_url,
    )


def _validate_yyyymm(yyyymm: str) -> None:
    if not isinstance(yyyymm, str) or re.fullmatch(r"\d{5}", yyyymm) is None:
        raise PopulationCollectorError(
            "yyyymm must be a five-digit ROC calendar month, such as 11507"
        )

    month = int(yyyymm[-2:])
    if not 1 <= month <= 12:
        raise PopulationCollectorError("yyyymm month must be between 01 and 12")


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
        query.append(("COUNTY", county))
    if town is not None and town.strip():
        query.append(("TOWN", town))

    url = f"{API_URL_TEMPLATE.format(yyyymm=yyyymm)}?{urlencode(query)}"
    request = Request(url, headers={"Accept": "application/json"})

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise PopulationCollectorError(
            f"ODRP014 HTTP error for {yyyymm} page {page}: {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise PopulationCollectorError(
            f"ODRP014 request failed for {yyyymm} page {page}: {exc}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PopulationCollectorError(
            f"ODRP014 returned invalid JSON for {yyyymm} page {page}"
        ) from exc

    return _parse_page(payload, yyyymm=yyyymm, page=page)


def _parse_page(
    payload: Any,
    *,
    yyyymm: str,
    page: int,
) -> tuple[int, list[dict[str, str]]]:
    if not isinstance(payload, dict):
        raise PopulationCollectorError(
            f"ODRP014 response must be an object for {yyyymm} page {page}"
        )

    response_code = payload.get("responseCode")
    if response_code == "OD-0102-S":
        message = payload.get("responseMessage", "unknown API error")
        raise CollectorNoDataError(
            f"ODRP014 has no data for {yyyymm} page {page}: {message}"
        )
    if response_code != SUCCESS_RESPONSE_CODE:
        message = payload.get("responseMessage", "unknown API error")
        raise PopulationCollectorError(
            f"ODRP014 returned {response_code!r} for {yyyymm} page {page}: {message}"
        )

    try:
        total_pages = int(payload["totalPage"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PopulationCollectorError(
            f"ODRP014 response has invalid totalPage for {yyyymm} page {page}"
        ) from exc

    if total_pages < 1:
        raise PopulationCollectorError(
            f"ODRP014 totalPage must be positive for {yyyymm} page {page}"
        )

    records = payload.get("responseData")
    if not isinstance(records, list):
        raise PopulationCollectorError(
            f"ODRP014 responseData must be a list for {yyyymm} page {page}"
        )

    for index, record in enumerate(records):
        if not isinstance(record, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in record.items()
        ):
            raise PopulationCollectorError(
                "ODRP014 responseData records must contain string keys and values "
                f"for {yyyymm} page {page} record {index}"
            )

    return total_pages, records
