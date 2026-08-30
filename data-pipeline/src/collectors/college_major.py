"""Collect Ministry of Education college and major enrollment records."""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OVERVIEW_URL = "https://stats.moe.gov.tw/files/opendata/sdata.json"
STUDENT_DETAIL_URL = "https://stats.moe.gov.tw/files/opendata/students.json"
DEFAULT_COUNTY = "新北市"
REQUEST_TIMEOUT_SECONDS = 120

OpenURL = Callable[..., Any]


class CollegeMajorCollectorError(RuntimeError):
    """Raised when a Ministry of Education JSON resource is invalid."""


def _create_ssl_context() -> ssl.SSLContext:
    """Keep certificate and hostname checks while supporting MOE's chain."""

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        # stats.moe.gov.tw currently omits Subject Key Identifier in its chain.
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_college_majors(
    academic_year: str | None = None,
    county: str | None = DEFAULT_COUNTY,
    *,
    include_student_detail: bool = False,
    open_url: OpenURL = _open_url,
) -> list[dict[str, str]]:
    """Fetch and locally filter one Ministry of Education JSON resource.

    By default this fetches dataset 9621, which contains the overview fields
    including ``學生數``. When ``include_student_detail`` is true, it fetches
    dataset 9622 instead and returns its raw gender and grade fields. The two
    datasets are intentionally not merged in this collector.

    ``county`` matches the county name suffix in values such as ``01 新北市``.
    Pass ``None`` to return records for all counties. The source files are
    downloaded as complete JSON resources, so filtering happens locally.
    """

    _validate_inputs(
        academic_year=academic_year,
        county=county,
        include_student_detail=include_student_detail,
    )
    source_url = STUDENT_DETAIL_URL if include_student_detail else OVERVIEW_URL
    source_name = "9622" if include_student_detail else "9621"
    records = _fetch_records(source_url, source_name=source_name, open_url=open_url)

    return [
        record
        for record in records
        if _matches_filters(
            record,
            academic_year=academic_year,
            county=county,
        )
    ]


def _validate_inputs(
    *,
    academic_year: str | None,
    county: str | None,
    include_student_detail: bool,
) -> None:
    if academic_year is not None and (
        not isinstance(academic_year, str) or not academic_year.strip()
    ):
        raise CollegeMajorCollectorError(
            "academic_year must be a non-empty string or None"
        )
    if county is not None and (not isinstance(county, str) or not county.strip()):
        raise CollegeMajorCollectorError("county must be a non-empty string or None")
    if not isinstance(include_student_detail, bool):
        raise CollegeMajorCollectorError("include_student_detail must be a boolean")


def _fetch_records(
    url: str,
    *,
    source_name: str,
    open_url: OpenURL,
) -> list[dict[str, str]]:
    request = Request(url, headers={"Accept": "application/json"})

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise CollegeMajorCollectorError(
            f"MOE {source_name} HTTP error: {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CollegeMajorCollectorError(
            f"MOE {source_name} request failed: {exc}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CollegeMajorCollectorError(
            f"MOE {source_name} returned invalid JSON"
        ) from exc

    if not isinstance(payload, list):
        raise CollegeMajorCollectorError(f"MOE {source_name} response must be a list")

    for index, record in enumerate(payload):
        if not isinstance(record, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in record.items()
        ):
            raise CollegeMajorCollectorError(
                f"MOE {source_name} records must contain string keys and values "
                f"at record {index}"
            )

    return payload


def _matches_filters(
    record: dict[str, str],
    *,
    academic_year: str | None,
    county: str | None,
) -> bool:
    if academic_year is not None and record.get("學年度") != academic_year:
        return False
    if county is not None and not _matches_county(record.get("縣市名稱"), county):
        return False
    return True


def _matches_county(value: str | None, county: str) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().endswith(county.strip())
