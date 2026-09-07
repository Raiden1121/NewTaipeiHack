"""Collect historical nationwide talent-demand records by occupation."""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


RESOURCE_ID = "A17000000J-030281-nQF"
TALENT_DEMAND_URL = (
    "https://apiservice.mol.gov.tw/OdService/rest/datastore/"
    f"{RESOURCE_ID}"
)
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000
REQUEST_TIMEOUT_SECONDS = 60

PERIOD_FIELD = "統計期"
OCCUPATION_FIELD = "職業別"
NEW_DEMAND_FIELD = "新登記求才人數（人次）"
NEW_HIRED_FIELD = "新登記求才僱用人數（人次）"
VALID_HIRED_FIELD = "有效求才僱用人數（人次）"
REQUIRED_FIELDS = frozenset(
    {
        PERIOD_FIELD,
        OCCUPATION_FIELD,
        NEW_DEMAND_FIELD,
        NEW_HIRED_FIELD,
        VALID_HIRED_FIELD,
    }
)

OpenURL = Callable[..., Any]


class TalentDemandCollectorError(RuntimeError):
    """Raised when the MOL talent-demand API returns invalid data."""


def _create_ssl_context() -> ssl.SSLContext:
    """Create the TLS context used by the MOL API request."""

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        # The MOL host currently omits a certificate field required by this
        # optional OpenSSL strictness flag.
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_talent_demand(
    period: str | None = None,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    open_url: OpenURL = _open_url,
) -> list[dict[str, Any]]:
    """Fetch nationwide historical talent-demand records by occupation.

    ``period`` can be an exact value such as ``"102年"``.  When omitted, all
    periods exposed by the resource are fetched.  The API response currently
    does not always include ``result.total``, so pagination also stops on an
    empty or short page.

    The returned records retain the original field names and values.  Numeric
    strings are intentionally not converted here; cleaning and aggregation
    belong to later transform/analytics stages.
    """

    _validate_inputs(period=period, page_size=page_size)
    period = period.strip() if period is not None else None

    filters: dict[str, str] = {}
    if period is not None:
        filters[PERIOD_FIELD] = period

    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        page, total = _fetch_page(
            filters=filters,
            limit=page_size,
            offset=offset,
            open_url=open_url,
        )
        records.extend(
            record
            for record in page
            if period is None or record[PERIOD_FIELD].strip() == period
        )

        if not page or len(page) < page_size:
            break
        if total is not None and offset + len(page) >= total:
            break
        offset += len(page)

    return records


def _validate_inputs(*, period: str | None, page_size: int) -> None:
    if period is not None and (
        not isinstance(period, str) or not period.strip()
    ):
        raise TalentDemandCollectorError(
            "period must be a non-empty string or None"
        )
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= MAX_PAGE_SIZE
    ):
        raise TalentDemandCollectorError(
            f"page_size must be an integer from 1 to {MAX_PAGE_SIZE}"
        )


def _fetch_page(
    *,
    filters: Mapping[str, str],
    limit: int,
    offset: int,
    open_url: OpenURL,
) -> tuple[list[dict[str, Any]], int | None]:
    query: dict[str, str | int] = {
        "limit": limit,
        "offset": offset,
    }
    if filters:
        query["filters"] = json.dumps(dict(filters), ensure_ascii=False)

    request = Request(
        f"{TALENT_DEMAND_URL}?{urlencode(query)}",
        headers={"Accept": "application/json"},
    )

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw_payload = response.read()
    except HTTPError as exc:
        raise TalentDemandCollectorError(
            f"MOL {RESOURCE_ID} API HTTP error: {exc.code} {exc.reason}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise TalentDemandCollectorError(
            f"MOL {RESOURCE_ID} API request failed: {exc}"
        ) from exc

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TalentDemandCollectorError(
            f"MOL {RESOURCE_ID} API returned invalid JSON"
        ) from exc

    return _parse_page(payload)


def _parse_page(
    payload: Any,
) -> tuple[list[dict[str, Any]], int | None]:
    if not isinstance(payload, dict):
        raise TalentDemandCollectorError(
            f"MOL {RESOURCE_ID} API response must be a JSON object"
        )

    if payload.get("success") is not True:
        error = payload.get("error")
        if isinstance(error, Mapping):
            error_message = error.get("message") or error.get("detail")
        else:
            error_message = error
        suffix = f": {error_message}" if error_message else ""
        raise TalentDemandCollectorError(
            f"MOL {RESOURCE_ID} API error{suffix}"
        )

    result = payload.get("result")
    if not isinstance(result, dict):
        raise TalentDemandCollectorError(
            f"MOL {RESOURCE_ID} API response is missing result object"
        )
    if result.get("resource_id") != RESOURCE_ID:
        raise TalentDemandCollectorError(
            f"MOL {RESOURCE_ID} API response has an unexpected resource_id"
        )

    raw_records = result.get("records")
    if not isinstance(raw_records, list):
        raise TalentDemandCollectorError(
            f"MOL {RESOURCE_ID} API result.records must be a JSON array"
        )

    records: list[dict[str, Any]] = []
    for index, record in enumerate(raw_records):
        if not isinstance(record, dict):
            raise TalentDemandCollectorError(
                f"MOL {RESOURCE_ID} API result.records[{index}] "
                "must be a JSON object"
            )
        missing_fields = REQUIRED_FIELDS.difference(record)
        if missing_fields:
            raise TalentDemandCollectorError(
                f"MOL {RESOURCE_ID} API record {index} is missing fields "
                f"{sorted(missing_fields)}"
            )
        if not isinstance(record[PERIOD_FIELD], str) or not record[PERIOD_FIELD].strip():
            raise TalentDemandCollectorError(
                f"MOL {RESOURCE_ID} API record {index} has invalid {PERIOD_FIELD}"
            )
        if not isinstance(record[OCCUPATION_FIELD], str) or not record[OCCUPATION_FIELD].strip():
            raise TalentDemandCollectorError(
                f"MOL {RESOURCE_ID} API record {index} has invalid {OCCUPATION_FIELD}"
            )
        records.append(record)

    total = result.get("total")
    if total is not None and (
        isinstance(total, bool) or not isinstance(total, int) or total < 0
    ):
        raise TalentDemandCollectorError(
            f"MOL {RESOURCE_ID} API result.total must be a non-negative integer"
        )

    return records, total
