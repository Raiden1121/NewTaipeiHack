"""Collect and normalize New Taipei real-estate sale records."""

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


DATASET_OID = "acce802d-58cc-4dff-9e7a-9ecc517f78be"
HOUSE_JSON_URL = (
    "https://data.ntpc.gov.tw/api/datasets/"
    f"{DATASET_OID}/json"
)
HOUSE_CSV_URL = (
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

HOUSE_TRANSACTION_TARGETS = frozenset(
    {
        "房地(土地+建物)",
        "房地(土地+建物)+車位",
    }
)
RESIDENTIAL_USES = frozenset({"住家用", "集合住宅", "住宅"})
EXCLUDED_BUILDING_MARKERS = ("店面", "辦公", "商業", "工廠", "廠辦", "倉庫")
NULL_VALUES = frozenset({"", "-", "—", "－", "NA", "N/A", "無", "面議"})

OpenURL = Callable[..., Any]


class HousePriceCollectorError(RuntimeError):
    """Raised when the New Taipei house-price API returns invalid data."""


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


def fetch_house_prices(
    district: str | None = None,
    *,
    residential_only: bool = DEFAULT_RESIDENTIAL_ONLY,
    source_format: str = DEFAULT_SOURCE_FORMAT,
    open_url: OpenURL = _open_url,
) -> list[dict[str, Any]]:
    """Fetch the current New Taipei house-sale snapshot.

    The dataset already covers New Taipei City and includes ``district``.
    ``district`` is an optional local filter such as ``"板橋區"``.  Raw
    source fields are kept, while aggregation and growth calculations remain
    in analytics.
    """

    _validate_inputs(
        district=district,
        residential_only=residential_only,
        source_format=source_format,
    )
    district = district.strip() if district is not None else None
    source_format = source_format.strip().lower()
    raw_records = _fetch_records(
        source_format=source_format,
        open_url=open_url,
    )
    return normalize_house_records(
        raw_records,
        district=district,
        residential_only=residential_only,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def normalize_house_records(
    records: Iterable[Mapping[str, Any]],
    *,
    district: str | None = None,
    residential_only: bool = DEFAULT_RESIDENTIAL_ONLY,
    fetched_at: str | None = None,
) -> list[dict[str, Any]]:
    """Filter and enrich sale rows without producing group statistics."""

    _validate_inputs(district=district, residential_only=residential_only)
    district = district.strip() if district is not None else None
    snapshot_fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    if not isinstance(snapshot_fetched_at, str) or not snapshot_fetched_at.strip():
        raise HousePriceCollectorError(
            "fetched_at must be a non-empty string or None"
        )

    normalized: list[dict[str, Any]] = []
    for index, source_record in enumerate(records):
        if not isinstance(source_record, Mapping):
            raise HousePriceCollectorError(
                f"record {index} must be a JSON object"
            )

        source_district = _source_text(source_record.get("district"))
        if not source_district:
            raise HousePriceCollectorError(
                f"record {index} is missing district"
            )
        if district is not None and source_district != district:
            continue
        if residential_only and not _is_residential(source_record):
            continue

        total_price = _parse_number(
            source_record.get("rps21_amountsunitdollars")
        )
        building_area_sqm = _parse_number(source_record.get("rps15_area"))
        price_per_sqm = _parse_number(
            source_record.get("rps22_amountsunitdollars")
        )
        transaction_date = _source_text(
            source_record.get("rps07_yyymmddroc")
        )

        enriched = dict(source_record)
        enriched.update(
            {
                "district": source_district,
                "transaction_date": transaction_date or None,
                "transaction_period": _to_roc_period(transaction_date),
                "total_price": total_price,
                "building_area_sqm": building_area_sqm,
                "price_per_sqm": price_per_sqm,
                "price_per_ping": (
                    _coerce_number(price_per_sqm * PING_SQUARE_METERS)
                    if price_per_sqm is not None and price_per_sqm > 0
                    else None
                ),
                "transaction_type": _source_text(source_record.get("rps01"))
                or None,
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
        raise HousePriceCollectorError(
            "district must be a non-empty string or None"
        )
    if not isinstance(residential_only, bool):
        raise HousePriceCollectorError("residential_only must be a boolean")
    if (
        not isinstance(source_format, str)
        or source_format.strip().lower() not in SOURCE_FORMATS
    ):
        raise HousePriceCollectorError(
            "source_format must be one of: csv, json"
        )


def _fetch_records(
    *,
    source_format: str,
    open_url: OpenURL,
) -> list[dict[str, Any]]:
    url = HOUSE_CSV_URL if source_format == "csv" else HOUSE_JSON_URL
    accept = "text/csv" if source_format == "csv" else "application/json"
    request = Request(url, headers={"Accept": accept})
    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw_payload = response.read()
    except HTTPError as exc:
        raise HousePriceCollectorError(
            f"New Taipei house-price API HTTP error: {exc.code} {exc.reason}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HousePriceCollectorError(
            f"New Taipei house-price API request failed: {exc}"
        ) from exc

    try:
        if isinstance(raw_payload, bytes):
            decoded_payload = raw_payload.decode("utf-8-sig")
        elif isinstance(raw_payload, str):
            decoded_payload = raw_payload
        else:
            raise TypeError("response body must be bytes or string")
    except (UnicodeDecodeError, TypeError) as exc:
        raise HousePriceCollectorError(
            f"New Taipei house-price API returned invalid {source_format}"
        ) from exc

    if source_format == "csv":
        return _parse_csv_records(decoded_payload)

    try:
        payload = json.loads(decoded_payload)
    except json.JSONDecodeError as exc:
        raise HousePriceCollectorError(
            "New Taipei house-price API returned invalid JSON"
        ) from exc
    return _parse_json_records(payload)


def _parse_csv_records(decoded_payload: str) -> list[dict[str, Any]]:
    try:
        reader = csv.DictReader(io.StringIO(decoded_payload))
        fieldnames = reader.fieldnames
        if not fieldnames or any(
            field is None or not field.strip() for field in fieldnames
        ):
            raise HousePriceCollectorError(
                "New Taipei house-price API CSV is missing a valid header"
            )

        records: list[dict[str, Any]] = []
        for index, row in enumerate(reader):
            if None in row:
                raise HousePriceCollectorError(
                    f"New Taipei house-price API CSV record {index} has extra fields"
                )
            records.append(dict(row))
        return records
    except csv.Error as exc:
        raise HousePriceCollectorError(
            "New Taipei house-price API returned invalid CSV"
        ) from exc


def _parse_json_records(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        if isinstance(payload, Mapping):
            message = payload.get("message") or payload.get("error")
            suffix = f": {message}" if message else ""
        else:
            suffix = ""
        raise HousePriceCollectorError(
            "New Taipei house-price API response must be a JSON array" + suffix
        )

    records: list[dict[str, Any]] = []
    for index, record in enumerate(payload):
        if not isinstance(record, dict):
            raise HousePriceCollectorError(
                f"New Taipei house-price API record {index} must be a JSON object"
            )
        records.append(record)
    return records


def _is_residential(record: Mapping[str, Any]) -> bool:
    target = _source_text(record.get("rps01"))
    usage = _source_text(record.get("rps12"))
    building_type = _source_text(record.get("rps11"))
    return (
        target in HOUSE_TRANSACTION_TARGETS
        and usage in RESIDENTIAL_USES
        and not any(
            marker in building_type for marker in EXCLUDED_BUILDING_MARKERS
        )
    )


def _parse_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
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


def _to_roc_period(transaction_date: str) -> str | None:
    if len(transaction_date) == 7 and transaction_date.isdigit():
        return transaction_date[:5]
    return None
