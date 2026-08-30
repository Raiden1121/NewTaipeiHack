"""Collect vocational training course records from the MOL open API."""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


COURSE_URL = (
    "https://apiservice.mol.gov.tw/OdService/rest/datastore/"
    "A17000000J-000007-Hv9"
)
DEFAULT_COUNTY = "新北市"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 60

OpenURL = Callable[..., Any]


class VtCourseCollectorError(RuntimeError):
    """Raised when the MOL vocational course API returns invalid data."""


def _create_ssl_context() -> ssl.SSLContext:
    """Keep certificate and hostname checks while supporting MOL's chain."""

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        # apiservice.mol.gov.tw currently omits Subject Key Identifier.
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_vt_courses(
    county: str | None = DEFAULT_COUNTY,
    district: str | None = None,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    open_url: OpenURL = _open_url,
) -> list[dict[str, Any]]:
    """Fetch all matching vocational training courses.

    The API is paginated. Filters are sent to the server, while the returned
    course dictionaries keep the source field names and values unchanged.
    Pass ``county=None`` to fetch nationwide data.
    """

    _validate_inputs(county=county, district=district, page_size=page_size)
    filters = _build_filters(county=county, district=district)

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

        if not page or len(page) < page_size:
            break
        if total is not None and offset + len(page) >= total:
            break
        offset += len(page)

    return records


def count_distinct_courses(records: Iterable[Mapping[str, Any]]) -> int:
    """Count non-empty distinct ``課程編號`` values without summing ``數量``."""

    course_ids = {
        str(record["課程編號"]).strip()
        for record in records
        if "課程編號" in record and str(record["課程編號"]).strip()
    }
    return len(course_ids)


def _validate_inputs(
    *,
    county: str | None,
    district: str | None,
    page_size: int,
) -> None:
    if county is not None and (not isinstance(county, str) or not county.strip()):
        raise VtCourseCollectorError("county must be a non-empty string or None")
    if district is not None and (
        not isinstance(district, str) or not district.strip()
    ):
        raise VtCourseCollectorError("district must be a non-empty string or None")
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= MAX_PAGE_SIZE
    ):
        raise VtCourseCollectorError(
            f"page_size must be an integer between 1 and {MAX_PAGE_SIZE}"
        )


def _build_filters(
    *,
    county: str | None,
    district: str | None,
) -> dict[str, str]:
    filters: dict[str, str] = {}
    if county is not None:
        filters["訓練縣市"] = county.strip()
    if district is not None:
        filters["訓練區域"] = district.strip()
    return filters


def _fetch_page(
    *,
    filters: dict[str, str],
    limit: int,
    offset: int,
    open_url: OpenURL,
) -> tuple[list[dict[str, Any]], int | None]:
    query: dict[str, str | int] = {
        "limit": limit,
        "offset": offset,
    }
    if filters:
        query["filters"] = json.dumps(
            filters,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    request = Request(f"{COURSE_URL}?{urlencode(query)}")
    request.add_header("Accept", "application/json")

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise VtCourseCollectorError(
            f"MOL 6060 HTTP error: {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise VtCourseCollectorError(f"MOL 6060 request failed: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VtCourseCollectorError("MOL 6060 returned invalid JSON") from exc

    return _parse_page(payload)


def _parse_page(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    if not isinstance(payload, dict):
        raise VtCourseCollectorError("MOL 6060 response must be an object")

    if payload.get("success") is not True:
        error = payload.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        suffix = f": {message}" if message else ""
        raise VtCourseCollectorError(f"MOL 6060 API error{suffix}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise VtCourseCollectorError("MOL 6060 response is missing result")

    raw_records = result.get("records")
    total = result.get("total")
    if not isinstance(raw_records, list):
        raise VtCourseCollectorError("MOL 6060 result.records must be a list")
    if total is not None and (
        isinstance(total, bool) or not isinstance(total, int) or total < 0
    ):
        raise VtCourseCollectorError("MOL 6060 result.total must be non-negative")

    records: list[dict[str, Any]] = []
    for index, record in enumerate(raw_records):
        if not isinstance(record, dict) or not all(
            isinstance(key, str) for key in record
        ):
            raise VtCourseCollectorError(
                "MOL 6060 records must contain string keys "
                f"at record {index}"
            )
        records.append(record)

    return records, total
