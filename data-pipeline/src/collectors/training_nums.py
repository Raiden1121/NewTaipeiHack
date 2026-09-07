"""Collect training-course records and training people counts from MOL."""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TRAINING_URL = (
    "https://apiservice.mol.gov.tw/OdService/rest/datastore/"
    "A17000000J-030190-lfV"
)
DEFAULT_COUNTY = "新北市"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 60
COUNTY_FIELD = "縣市別辦訓地"
PEOPLE_FIELD = "訓練人次"

OpenURL = Callable[..., Any]


class TrainingNumsCollectorError(RuntimeError):
    """Raised when the MOL training-people API returns invalid data."""


def _create_ssl_context() -> ssl.SSLContext:
    """Create the TLS context used by the MOL API request."""

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        # The MOL host currently omits a certificate field required by this
        # optional OpenSSL strictness flag, while normal certificate checking
        # remains enabled.
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_training_numbers(
    county: str | None = DEFAULT_COUNTY,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    open_url: OpenURL = _open_url,
) -> list[dict[str, Any]]:
    """Fetch all records from dataset 59296 for a county or all Taiwan.

    The returned dictionaries are the API's original records.  No field is
    renamed or dropped here; cleaning and aggregation belong to later stages.
    """

    _validate_inputs(county=county, page_size=page_size)

    filters: dict[str, str] = {}
    if county is not None:
        filters[COUNTY_FIELD] = county.strip()

    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        page, total = _fetch_page(
            filters=filters,
            limit=page_size,
            offset=offset,
            open_url=open_url,
        )
        records.extend(page)

        # The MOL response may omit result.total.  A short or empty page is
        # therefore also a valid end-of-pagination signal.
        if not page or len(page) < page_size:
            break
        if total is not None and offset + len(page) >= total:
            break
        offset += len(page)

    return records


def sum_training_people(records: Iterable[Mapping[str, Any]]) -> int:
    """Sum the integer values in the original ``訓練人次`` field."""

    total = 0
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise TrainingNumsCollectorError(
                f"record {index} must be a JSON object"
            )

        if PEOPLE_FIELD not in record:
            raise TrainingNumsCollectorError(
                f"record {index} is missing {PEOPLE_FIELD}"
            )

        value = record[PEOPLE_FIELD]
        if isinstance(value, bool):
            raise TrainingNumsCollectorError(
                f"record {index} has invalid {PEOPLE_FIELD}: {value!r}"
            )

        if isinstance(value, int):
            people = value
        elif isinstance(value, str):
            normalized = value.strip().replace(",", "")
            if not normalized.isdigit():
                raise TrainingNumsCollectorError(
                    f"record {index} has invalid {PEOPLE_FIELD}: {value!r}"
                )
            people = int(normalized)
        else:
            raise TrainingNumsCollectorError(
                f"record {index} has invalid {PEOPLE_FIELD}: {value!r}"
            )

        total += people

    return total


def _validate_inputs(*, county: str | None, page_size: int) -> None:
    if county is not None and (not isinstance(county, str) or not county.strip()):
        raise ValueError("county must be a non-empty string or None")

    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= MAX_PAGE_SIZE
    ):
        raise ValueError(f"page_size must be an integer from 1 to {MAX_PAGE_SIZE}")


def _fetch_page(
    *,
    filters: Mapping[str, str],
    limit: int,
    offset: int,
    open_url: OpenURL,
) -> tuple[list[dict[str, Any]], int | None]:
    query: dict[str, str | int] = {"limit": limit, "offset": offset}
    if filters:
        query["filters"] = json.dumps(
            dict(filters), ensure_ascii=False, separators=(",", ":")
        )

    request = Request(
        f"{TRAINING_URL}?{urlencode(query)}",
        headers={"Accept": "application/json"},
    )

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw_payload = response.read()
    except HTTPError as exc:
        raise TrainingNumsCollectorError(
            f"MOL 59296 API HTTP error: {exc.code} {exc.reason}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise TrainingNumsCollectorError(
            f"MOL 59296 API request failed: {exc}"
        ) from exc

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrainingNumsCollectorError(
            "MOL 59296 API returned invalid JSON"
        ) from exc

    return _parse_page(payload)


def _parse_page(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    if not isinstance(payload, dict):
        raise TrainingNumsCollectorError("MOL 59296 API response must be a JSON object")

    if payload.get("success") is not True:
        error = payload.get("error")
        if isinstance(error, Mapping):
            error_message = error.get("message") or error.get("detail")
        else:
            error_message = error
        suffix = f": {error_message}" if error_message else ""
        raise TrainingNumsCollectorError(f"MOL 59296 API error{suffix}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise TrainingNumsCollectorError(
            "MOL 59296 API response is missing result object"
        )

    raw_records = result.get("records")
    if not isinstance(raw_records, list):
        raise TrainingNumsCollectorError(
            "MOL 59296 API result.records must be a JSON array"
        )

    records: list[dict[str, Any]] = []
    for index, record in enumerate(raw_records):
        if not isinstance(record, dict):
            raise TrainingNumsCollectorError(
                f"MOL 59296 API result.records[{index}] must be a JSON object"
            )
        records.append(record)

    total = result.get("total")
    if total is not None and (
        isinstance(total, bool) or not isinstance(total, int) or total < 0
    ):
        raise TrainingNumsCollectorError(
            "MOL 59296 API result.total must be a non-negative integer"
        )

    return records, total
