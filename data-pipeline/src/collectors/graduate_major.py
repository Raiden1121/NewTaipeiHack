"""Collect Ministry of Education graduate-by-major records."""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GRADUATE_URL = "https://stats.moe.gov.tw/files/opendata/graduatesc.json"
DEFAULT_COUNTY = "新北市"
COUNTY_FIELD = "縣市名稱"
REQUEST_TIMEOUT_SECONDS = 120

OpenURL = Callable[..., Any]


class GraduateMajorCollectorError(RuntimeError):
    """Raised when the Ministry of Education graduate resource is invalid."""


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


def fetch_graduate_majors(
    academic_year: str | None = None,
    county: str | None = DEFAULT_COUNTY,
    *,
    open_url: OpenURL = _open_url,
) -> list[dict[str, str]]:
    """Fetch dataset 9620 and locally filter graduate records.

    The source is a complete JSON resource, so ``academic_year`` and
    ``county`` are applied after download. The returned records are the
    original source dictionaries; no field renaming or aggregation occurs in
    this collector. Pass ``county=None`` to return the national resource.

    Dataset 9620 currently does not provide ``縣市名稱``. Therefore a county
    filter raises an explicit error instead of returning an incorrect empty
    result; a geographic source or later join is required for New Taipei
    filtering.
    """

    _validate_inputs(academic_year=academic_year, county=county)
    records = _fetch_records(open_url=open_url)
    if county is not None and records and not all(
        COUNTY_FIELD in record for record in records
    ):
        raise GraduateMajorCollectorError(
            "MOE 9620 response 沒有縣市欄位，無法依縣市篩選；請使用 county=None "
            "取得全國資料"
        )

    return [
        record
        for record in records
        if _matches_filters(
            record,
            academic_year=academic_year,
            county=county,
        )
    ]


def _validate_inputs(*, academic_year: str | None, county: str | None) -> None:
    if academic_year is not None and (
        not isinstance(academic_year, str) or not academic_year.strip()
    ):
        raise GraduateMajorCollectorError(
            "academic_year must be a non-empty string or None"
        )
    if county is not None and (not isinstance(county, str) or not county.strip()):
        raise GraduateMajorCollectorError("county must be a non-empty string or None")


def _fetch_records(*, open_url: OpenURL) -> list[dict[str, str]]:
    request = Request(GRADUATE_URL, headers={"Accept": "application/json"})

    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise GraduateMajorCollectorError(
            f"MOE 9620 HTTP error: {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise GraduateMajorCollectorError(f"MOE 9620 request failed: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GraduateMajorCollectorError("MOE 9620 returned invalid JSON") from exc

    if not isinstance(payload, list):
        raise GraduateMajorCollectorError("MOE 9620 response must be a list")

    for index, record in enumerate(payload):
        if not isinstance(record, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in record.items()
        ):
            raise GraduateMajorCollectorError(
                "MOE 9620 records must contain string keys and values "
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
    if county is not None and not _matches_county(record.get(COUNTY_FIELD), county):
        return False
    return True


def _matches_county(value: str | None, county: str) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().endswith(county.strip())
