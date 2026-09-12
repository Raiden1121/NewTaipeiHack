"""Read official historical single-age population archives for New Taipei."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import ssl
import zipfile
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contracts import CollectedPayload, SourceArtifact
from .errors import CollectorNoDataError


DATA_GOV_DATASET_URL = "https://data.gov.tw/dataset/8411"
HISTORICAL_POPULATION_RESOURCE_URLS = {
    "10312": (
        "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
        "F4478CE5-7A72-4B14-B91A-F4701758328F/resource/"
        "572AF1C0-D8DE-485C-97B0-D7A550235963/download"
    ),
}
DEFAULT_COUNTY = "新北市"
REQUEST_TIMEOUT_SECONDS = 30
_ROC_MONTH_RE = re.compile(r"^\d{5}$")
_REQUIRED_COLUMNS = (
    "統計年月",
    "區域別",
    "村里",
    "戶數",
    "人口數",
    "人口數-男",
    "人口數-女",
)

OpenURL = Callable[..., Any]


class HistoricalPopulationCollectorError(RuntimeError):
    """Raised when an official historical population archive is invalid."""


def _create_ssl_context() -> ssl.SSLContext:
    """Keep certificate checks while supporting the current Python/OpenSSL stack."""

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int = REQUEST_TIMEOUT_SECONDS) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_historical_population(
    yyyymm: str,
    county: str | None = DEFAULT_COUNTY,
    *,
    open_url: OpenURL = _open_url,
) -> CollectedPayload:
    """Fetch and normalize one supported historical population archive.

    The archive contains the complete New Taipei village file.  This adapter
    intentionally returns the existing population raw-record shape so the
    normal population transform remains the only place that aggregates ages
    and districts.
    """

    _validate_yyyymm(yyyymm)
    if yyyymm not in HISTORICAL_POPULATION_RESOURCE_URLS:
        raise CollectorNoDataError(
            f"historical population archive has no registered resource for {yyyymm}"
        )
    if county != DEFAULT_COUNTY:
        raise CollectorNoDataError(
            f"historical population archive only covers {DEFAULT_COUNTY}"
        )

    source_url = HISTORICAL_POPULATION_RESOURCE_URLS[yyyymm]
    request = Request(source_url, headers={"Accept": "application/zip"})
    archive_bytes = _request_archive(request, yyyymm=yyyymm, open_url=open_url)
    member_name, records = _parse_archive(
        archive_bytes,
        yyyymm=yyyymm,
        county=county,
    )
    digest = hashlib.sha256(archive_bytes).hexdigest()
    artifact = SourceArtifact(
        filename=f"{yyyymm}_moi_village_population_{digest[:16]}.zip",
        content=archive_bytes,
        media_type="application/zip",
        sha256=f"sha256:{digest}",
    )
    return CollectedPayload(
        records=records,
        metadata={
            "source_dataset": "moi_village_population",
            "source_dataset_url": DATA_GOV_DATASET_URL,
            "source_url": source_url,
            "source_period": yyyymm,
            "source_file": member_name,
            "county": county,
            "record_count": len(records),
        },
        artifacts=(artifact,),
    )


def _validate_yyyymm(yyyymm: str) -> None:
    if not isinstance(yyyymm, str) or _ROC_MONTH_RE.fullmatch(yyyymm) is None:
        raise HistoricalPopulationCollectorError(
            "yyyymm must be a five-digit ROC calendar month"
        )
    month = int(yyyymm[-2:])
    if not 1 <= month <= 12:
        raise HistoricalPopulationCollectorError(
            "yyyymm month must be between 01 and 12"
        )


def _request_archive(
    request: Request,
    *,
    yyyymm: str,
    open_url: OpenURL,
) -> bytes:
    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content = response.read()
    except HTTPError as exc:
        raise HistoricalPopulationCollectorError(
            f"historical population HTTP error for {yyyymm}: {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HistoricalPopulationCollectorError(
            f"historical population request failed for {yyyymm}: {exc}"
        ) from exc
    if not isinstance(content, bytes) or not content:
        raise HistoricalPopulationCollectorError(
            f"historical population archive is empty for {yyyymm}"
        )
    return content


def _parse_archive(
    archive_bytes: bytes,
    *,
    yyyymm: str,
    county: str,
) -> tuple[str, list[dict[str, str]]]:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            member_name = _find_csv_member(archive, yyyymm)
            with archive.open(member_name) as binary_stream:
                text_stream = io.TextIOWrapper(
                    binary_stream,
                    encoding="utf-8-sig",
                    newline="",
                )
                try:
                    reader = csv.DictReader(text_stream)
                    fieldnames = [
                        str(field).strip()
                        for field in (reader.fieldnames or [])
                        if field is not None and str(field).strip()
                    ]
                    _validate_columns(fieldnames, yyyymm=yyyymm)
                    records = [
                        _normalize_row(
                            row,
                            row_number=row_number,
                            yyyymm=yyyymm,
                            county=county,
                            source_file=member_name,
                        )
                        for row_number, row in enumerate(reader, start=2)
                    ]
                finally:
                    text_stream.detach()
    except HistoricalPopulationCollectorError:
        raise
    except (csv.Error, UnicodeError, KeyError, OSError, zipfile.BadZipFile) as exc:
        raise HistoricalPopulationCollectorError(
            f"historical population CSV is invalid for {yyyymm}: {exc}"
        ) from exc

    if not records:
        raise HistoricalPopulationCollectorError(
            f"historical population CSV has no records for {yyyymm}"
        )
    return member_name, records


def _find_csv_member(archive: zipfile.ZipFile, yyyymm: str) -> str:
    expected_suffix = f"opendata-{yyyymm}_age-65000.csv"
    candidates = [
        name
        for name in archive.namelist()
        if name.casefold().endswith(expected_suffix.casefold())
    ]
    if len(candidates) != 1:
        raise HistoricalPopulationCollectorError(
            f"historical population archive must contain one {expected_suffix!r}; "
            f"found {len(candidates)}"
        )
    return candidates[0]


def _validate_columns(fieldnames: list[str], *, yyyymm: str) -> None:
    missing = [column for column in _REQUIRED_COLUMNS if column not in fieldnames]
    missing.extend(
        f"{age}歲-{sex}"
        for age in range(18, 36)
        for sex in ("男", "女")
        if f"{age}歲-{sex}" not in fieldnames
    )
    if missing:
        raise HistoricalPopulationCollectorError(
            f"historical population CSV is missing columns for {yyyymm}: "
            + ", ".join(missing)
        )


def _normalize_row(
    row: dict[str, str | None],
    *,
    row_number: int,
    yyyymm: str,
    county: str,
    source_file: str,
) -> dict[str, str]:
    normalized_row = {
        str(key).strip(): value
        for key, value in row.items()
        if key is not None and str(key).strip()
    }
    area = _required_value(normalized_row, "區域別", row_number=row_number)
    if not area.startswith(county):
        raise HistoricalPopulationCollectorError(
            f"historical population row {row_number} is outside {county}: {area!r}"
        )
    statistic_month = _required_value(
        normalized_row, "統計年月", row_number=row_number
    )
    if statistic_month != yyyymm:
        raise HistoricalPopulationCollectorError(
            f"historical population row {row_number} has period {statistic_month!r}; "
            f"expected {yyyymm}"
        )

    result: dict[str, str] = {
        "statistic_yyymm": statistic_month,
        "site_id": area,
        "village": _required_value(normalized_row, "村里", row_number=row_number),
        "household_no": _required_value(normalized_row, "戶數", row_number=row_number),
        "people_total": _required_value(normalized_row, "人口數", row_number=row_number),
        "people_total_m": _required_value(
            normalized_row, "人口數-男", row_number=row_number
        ),
        "people_total_f": _required_value(
            normalized_row, "人口數-女", row_number=row_number
        ),
        "source_dataset": "moi_village_population",
        "source_file": source_file,
        "source_row": str(row_number),
    }
    for age in range(18, 36):
        result[f"people_age_{age:03d}_m"] = _required_value(
            normalized_row, f"{age}歲-男", row_number=row_number
        )
        result[f"people_age_{age:03d}_f"] = _required_value(
            normalized_row, f"{age}歲-女", row_number=row_number
        )
    return result


def _required_value(
    row: dict[str, str | None], column: str, *, row_number: int
) -> str:
    value = row.get(column)
    if value is None or not str(value).strip():
        raise HistoricalPopulationCollectorError(
            f"historical population row {row_number} is missing {column!r}"
        )
    return str(value).strip()
