"""Collect the official higher-education school location directory."""

from __future__ import annotations

import csv
from copy import deepcopy
from functools import lru_cache
import io
import re
import ssl
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Dataset 33207: 108 academic-year national university directory.  The file
# contains the stable school code, address, and third-level administrative
# district used to locate college-major records.
SCHOOL_DIRECTORY_URL = (
    "https://ws.moe.edu.tw/001/Upload/4/relfile/0/5038/"
    "55f39b31-27a0-4009-866a-ea260eb45eaf.csv"
)
SOURCE_NAME = "moe_33207_108"
REQUEST_TIMEOUT_SECONDS = 120
# The Ministry of Education's school-change records changed these codes after
# the 108 directory.  Keep the historical location row and expose the newer
# codes used by later 9621/9622 snapshots.
SCHOOL_CODE_ALIASES = {
    "1084": "1166",  # 亞東科技大學 <- 亞東技術學院
    "1085": "1195",  # 馬偕醫學大學 <- 馬偕醫學院
}

OpenURL = Callable[..., Any]


class CollegeSchoolCollectorError(RuntimeError):
    """Raised when the official school directory cannot be parsed."""


def _create_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_college_school_locations(
    *,
    open_url: OpenURL = _open_url,
) -> list[dict[str, Any]]:
    """Fetch school-code-to-location records from the official directory.

    The default network path is cached for the lifetime of one pipeline
    process because every academic-year college snapshot uses the same
    location reference. Tests and callers with an injected ``open_url`` still
    fetch independently.
    """

    if open_url is _open_url:
        return [deepcopy(record) for record in _cached_default_locations()]
    return _fetch_locations(open_url=open_url)


@lru_cache(maxsize=1)
def _cached_default_locations() -> tuple[dict[str, Any], ...]:
    return tuple(_fetch_locations(open_url=_open_url))


def _fetch_locations(*, open_url: OpenURL) -> list[dict[str, Any]]:
    # The MOE IIS endpoint returns 406 for ``Accept: text/csv`` even though
    # the response body is CSV. Use a generic Accept value and identify the
    # pipeline explicitly instead of negotiating an unsupported media type.
    request = Request(
        SCHOOL_DIRECTORY_URL,
        headers={
            "Accept": "*/*",
            "User-Agent": "NewTaipeiHack-data-pipeline/1.0",
        },
    )
    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except HTTPError as exc:
        raise CollegeSchoolCollectorError(
            f"MOE school directory HTTP error: {exc.code} {exc.reason}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CollegeSchoolCollectorError(
            f"MOE school directory request failed: {exc}"
        ) from exc

    if not isinstance(payload, (bytes, str)):
        raise CollegeSchoolCollectorError("MOE school directory response must be CSV")
    try:
        text = _decode_payload(payload)
    except UnicodeDecodeError as exc:
        raise CollegeSchoolCollectorError(
            "MOE school directory returned invalid text encoding"
        ) from exc
    return _parse_csv(text)


def _decode_payload(payload: bytes | str) -> str:
    if isinstance(payload, str):
        return payload
    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", payload, 0, len(payload), "unsupported encoding")


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CollegeSchoolCollectorError("MOE school directory CSV is missing a header")

    headers = {_normalize_header(header) for header in reader.fieldnames if header is not None}
    required = {"學校代碼", "學校名稱", "縣市別", "第三級行政區", "學校地址"}
    missing = sorted(required - headers)
    if missing:
        raise CollegeSchoolCollectorError(
            f"MOE school directory CSV is missing fields: {', '.join(missing)}"
        )

    records: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, row in enumerate(reader):
        if None in row:
            raise CollegeSchoolCollectorError(
                f"MOE school directory CSV record {index} has extra fields"
            )
        normalized = {
            _normalize_header(key): value
            for key, value in row.items()
            if key is not None
        }
        school_code = _text(normalized.get("學校代碼"))
        if not school_code:
            raise CollegeSchoolCollectorError(
                f"MOE school directory CSV record {index} is missing school code"
            )
        if school_code in seen_codes:
            raise CollegeSchoolCollectorError(
                f"MOE school directory has duplicate school code: {school_code}"
            )
        seen_codes.add(school_code)
        records.append(
            {
                "school_code": school_code,
                "school_name": _text(normalized.get("學校名稱")),
                "county_name": _text(normalized.get("縣市別")),
                "district_name": _text(normalized.get("第三級行政區")),
                "postal_code": _text(normalized.get("郵遞區號")),
                "school_address": _text(normalized.get("學校地址")),
                "source": SOURCE_NAME,
                "raw_record": dict(row),
            }
        )
    return _add_code_aliases(records)


def _add_code_aliases(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_code = {record["school_code"]: record for record in records}
    enriched = list(records)
    for alias_code, source_code in SCHOOL_CODE_ALIASES.items():
        if alias_code in by_code or source_code not in by_code:
            continue
        alias_record = deepcopy(by_code[source_code])
        alias_record["school_code"] = alias_code
        alias_record["school_code_alias_of"] = source_code
        alias_record["source"] = f"{SOURCE_NAME}_code_alias"
        enriched.append(alias_record)
    return enriched


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
