"""Collect and normalize New Taipei rental transaction records."""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
import io
import json
import math
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DATASET_OID = "18d62577-1d5f-4967-ab9c-d71faba8cde1"
RENTAL_JSON_URL = (
    "https://data.ntpc.gov.tw/api/datasets/"
    f"{DATASET_OID}/json"
)
RENTAL_CSV_URL = (
    "https://data.ntpc.gov.tw/api/datasets/"
    f"{DATASET_OID}/csv/file"
)
DEFAULT_SOURCE_FORMAT = "csv"
SOURCE_FORMATS = frozenset({"csv", "json"})
REQUEST_TIMEOUT_SECONDS = 60
PING_SQUARE_METERS = 3.305785
# Keep the complete source snapshot by default.  Callers that need the
# residential-only subset can still pass ``residential_only=True``.
DEFAULT_RESIDENTIAL_ONLY = False

RENTAL_TARGETS = frozenset({"租賃房屋", "租賃房屋+車位"})
RESIDENTIAL_USES = frozenset({"住家用", "集合住宅", "住宅"})
EXCLUDED_BUILDING_MARKERS = ("店面", "辦公", "商業", "工廠", "廠辦", "倉庫")
NULL_VALUES = frozenset({"", "-", "—", "－", "NA", "N/A", "無", "面議"})
RENTAL_TYPE_NAMES = {
    "整棟(戶)出租": "整戶",
    "獨立套房": "獨立套房",
    "分租套房": "分租套房",
    "分租雅房": "分租雅房",
    "分層出租": "分層出租",
}

OpenURL = Callable[..., Any]


class RentalPriceCollectorError(RuntimeError):
    """Raised when the New Taipei rental API returns invalid data."""


def _create_ssl_context() -> ssl.SSLContext:
    """Keep certificate and hostname checks for the New Taipei API."""

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        # The API host currently omits Subject Key Identifier in its chain.
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_rental_prices(
    district: str | None = None,
    *,
    residential_only: bool = DEFAULT_RESIDENTIAL_ONLY,
    source_format: str = DEFAULT_SOURCE_FORMAT,
    open_url: OpenURL = _open_url,
) -> list[dict[str, Any]]:
    """Fetch the current New Taipei rental snapshot.

    The API dataset is already scoped to New Taipei City.  ``district`` is an
    optional local filter such as ``"板橋區"``; ``None`` keeps all districts.
    Raw source fields are retained and row-level normalized values are added.
    Aggregation, outlier rules, and YoY calculations belong to analytics.
    """

    _validate_inputs(
        district=district,
        residential_only=residential_only,
        source_format=source_format,
    )
    source_format = source_format.strip().lower()
    raw_records = _fetch_records(
        source_format=source_format,
        open_url=open_url,
    )
    return normalize_rental_records(
        raw_records,
        district=district,
        residential_only=residential_only,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def normalize_rental_records(
    records: Iterable[Mapping[str, Any]],
    *,
    district: str | None = None,
    residential_only: bool = DEFAULT_RESIDENTIAL_ONLY,
    fetched_at: str | None = None,
) -> list[dict[str, Any]]:
    """Filter and enrich source rows without producing group statistics."""

    _validate_inputs(district=district, residential_only=residential_only)
    snapshot_fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    if not isinstance(snapshot_fetched_at, str) or not snapshot_fetched_at.strip():
        raise RentalPriceCollectorError(
            "fetched_at must be a non-empty string or None"
        )

    normalized: list[dict[str, Any]] = []
    for index, source_record in enumerate(records):
        if not isinstance(source_record, Mapping):
            raise RentalPriceCollectorError(
                f"record {index} must be a JSON object"
            )

        source_district = _source_text(source_record.get("district"))
        if not source_district:
            raise RentalPriceCollectorError(
                f"record {index} is missing district"
            )
        if district is not None and source_district != district:
            continue
        if residential_only and not _is_residential(source_record):
            continue

        enriched = dict(source_record)
        rent_total = _parse_number(
            source_record.get("rps22_amountsunitdollars")
        )
        building_area_sqm = _parse_number(source_record.get("rps15_area"))
        source_rent_per_sqm = _parse_number(
            source_record.get("rps23_amountsunitdollars")
        )
        rent_per_sqm, rent_per_sqm_source = _resolve_rent_per_sqm(
            source_rent_per_sqm=source_rent_per_sqm,
            rent_total=rent_total,
            building_area_sqm=building_area_sqm,
        )

        rental_date = _source_text(source_record.get("rps07_yyymmddroc"))
        enriched.update(
            {
                "district": source_district,
                "rental_date": rental_date or None,
                "rental_period": _to_roc_period(rental_date),
                "rent_total": rent_total,
                "building_area_sqm": building_area_sqm,
                "rent_per_sqm": rent_per_sqm,
                "rent_per_sqm_source": rent_per_sqm_source,
                "rent_per_ping": (
                    _coerce_number(rent_per_sqm * PING_SQUARE_METERS)
                    if rent_per_sqm is not None and rent_per_sqm > 0
                    else None
                ),
                "rental_type": _classify_rental_type(
                    source_record.get("rps29")
                ),
                "snapshot_fetched_at": snapshot_fetched_at,
            }
        )
        normalized.append(enriched)

    return normalized


def _validate_inputs(
    *,
    district: str | None,
    residential_only: bool,
    source_format: str = DEFAULT_SOURCE_FORMAT,
) -> None:
    if district is not None and (
        not isinstance(district, str) or not district.strip()
    ):
        raise RentalPriceCollectorError(
            "district must be a non-empty string or None"
        )
    if not isinstance(residential_only, bool):
        raise RentalPriceCollectorError("residential_only must be a boolean")
    if (
        not isinstance(source_format, str)
        or source_format.strip().lower() not in SOURCE_FORMATS
    ):
        raise RentalPriceCollectorError(
            "source_format must be one of: csv, json"
        )


def _fetch_records(
    *,
    source_format: str,
    open_url: OpenURL,
) -> list[dict[str, Any]]:
    url = RENTAL_CSV_URL if source_format == "csv" else RENTAL_JSON_URL
    accept = "text/csv" if source_format == "csv" else "application/json"
    request = Request(
        url,
        headers={"Accept": accept},
    )
    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw_payload = response.read()
    except HTTPError as exc:
        raise RentalPriceCollectorError(
            f"New Taipei rental API HTTP error: {exc.code} {exc.reason}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RentalPriceCollectorError(
            f"New Taipei rental API request failed: {exc}"
        ) from exc

    try:
        if isinstance(raw_payload, bytes):
            decoded_payload = raw_payload.decode("utf-8-sig")
        elif isinstance(raw_payload, str):
            decoded_payload = raw_payload
        else:
            raise TypeError("response body must be bytes or string")
    except (UnicodeDecodeError, TypeError) as exc:
        raise RentalPriceCollectorError(
            f"New Taipei rental API returned invalid {source_format}"
        ) from exc

    if source_format == "csv":
        return _parse_csv_records(decoded_payload)

    try:
        payload = json.loads(decoded_payload)
    except json.JSONDecodeError as exc:
        raise RentalPriceCollectorError(
            "New Taipei rental API returned invalid JSON"
        ) from exc
    return _parse_records(payload)


def _parse_csv_records(decoded_payload: str) -> list[dict[str, Any]]:
    try:
        reader = csv.DictReader(io.StringIO(decoded_payload))
        fieldnames = reader.fieldnames
        if not fieldnames or any(field is None or not field.strip() for field in fieldnames):
            raise RentalPriceCollectorError(
                "New Taipei rental API CSV is missing a valid header"
            )

        records: list[dict[str, Any]] = []
        for index, row in enumerate(reader):
            if None in row:
                raise RentalPriceCollectorError(
                    f"New Taipei rental API CSV record {index} has extra fields"
                )
            records.append(dict(row))
        return records
    except csv.Error as exc:
        raise RentalPriceCollectorError(
            "New Taipei rental API returned invalid CSV"
        ) from exc


def _parse_records(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        if isinstance(payload, Mapping):
            message = payload.get("message") or payload.get("error")
            suffix = f": {message}" if message else ""
        else:
            suffix = ""
        raise RentalPriceCollectorError(
            "New Taipei rental API response must be a JSON array" + suffix
        )

    records: list[dict[str, Any]] = []
    for index, record in enumerate(payload):
        if not isinstance(record, dict):
            raise RentalPriceCollectorError(
                f"New Taipei rental API record {index} must be a JSON object"
            )
        records.append(record)
    return records


def _is_residential(record: Mapping[str, Any]) -> bool:
    target = _source_text(record.get("rps01"))
    usage = _source_text(record.get("rps12"))
    building_type = _source_text(record.get("rps11"))
    return (
        target in RENTAL_TARGETS
        and usage in RESIDENTIAL_USES
        and not any(marker in building_type for marker in EXCLUDED_BUILDING_MARKERS)
    )


def _resolve_rent_per_sqm(
    *,
    source_rent_per_sqm: int | float | None,
    rent_total: int | float | None,
    building_area_sqm: int | float | None,
) -> tuple[int | float | None, str]:
    if source_rent_per_sqm is not None and source_rent_per_sqm > 0:
        return source_rent_per_sqm, "source"
    if (
        rent_total is not None
        and rent_total > 0
        and building_area_sqm is not None
        and building_area_sqm > 0
    ):
        return _coerce_number(rent_total / building_area_sqm), "derived"
    return None, "missing"


def _parse_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        if text in NULL_VALUES:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return _coerce_number(number)


def _coerce_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _source_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_roc_period(rental_date: str) -> str | None:
    if len(rental_date) == 7 and rental_date.isdigit():
        return rental_date[:5]
    return None


def _classify_rental_type(value: Any) -> str:
    rental_type = _source_text(value)
    return RENTAL_TYPE_NAMES.get(rental_type, "未知")
