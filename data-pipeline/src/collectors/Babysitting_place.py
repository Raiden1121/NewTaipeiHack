"""Collect public and private New Taipei childcare facility rosters."""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .contracts import CollectedPayload
from .errors import CollectorNoDataError


PRIVATE_DATASET_OID = "69cecdb0-7796-48df-84e5-99e4f1274245"
PUBLIC_DATASET_OID = "b3faf2aa-e96b-4f2f-b647-da47dc094860"
PRIVATE_API_URL = f"https://data.ntpc.gov.tw/api/datasets/{PRIVATE_DATASET_OID}/json"
PUBLIC_API_URL = f"https://data.ntpc.gov.tw/api/datasets/{PUBLIC_DATASET_OID}/json"
REQUEST_TIMEOUT_SECONDS = 60
DEFAULT_PAGE_SIZE = 1000

OpenURL = Callable[..., Any]


class BabysittingPlaceCollectorError(RuntimeError):
    """Raised when the New Taipei childcare roster API is invalid."""


def _create_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_babysitting_places(
    *, page_size: int = DEFAULT_PAGE_SIZE, open_url: OpenURL = _open_url
) -> CollectedPayload:
    """Fetch and combine the current private and public childcare rosters."""

    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size <= 0:
        raise BabysittingPlaceCollectorError("page_size must be a positive integer")

    source_specs = (
        ("private", PRIVATE_DATASET_OID, PRIVATE_API_URL),
        ("public", PUBLIC_DATASET_OID, PUBLIC_API_URL),
    )
    records: list[dict[str, Any]] = []
    source_metadata: list[dict[str, Any]] = []

    for care_type, dataset_oid, url in source_specs:
        source_records = _fetch_records(
            url,
            care_type=care_type,
            page_size=page_size,
            open_url=open_url,
        )
        source_metadata.append(
            {
                "care_type": care_type,
                "dataset_id": dataset_oid,
                "url": url,
                "record_count": len(source_records),
            }
        )
        for source_record in source_records:
            record = dict(source_record)
            record["care_type"] = care_type
            record["source_dataset_id"] = dataset_oid
            records.append(record)

    if not records:
        raise CollectorNoDataError("New Taipei childcare roster APIs returned no records")

    return CollectedPayload(
        records=records,
        metadata={
            "source": "ntpc_social_affairs_babysitting",
            "update_frequency": "annual",
            "source_datasets": source_metadata,
        },
    )


def _fetch_records(
    url: str,
    *,
    care_type: str,
    page_size: int,
    open_url: OpenURL,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 0
    while True:
        page_records = _fetch_page(
            url,
            care_type=care_type,
            page=page,
            page_size=page_size,
            open_url=open_url,
        )
        records.extend(page_records)
        if len(page_records) < page_size:
            return records
        page += 1


def _fetch_page(
    url: str,
    *,
    care_type: str,
    page: int,
    page_size: int,
    open_url: OpenURL,
) -> list[dict[str, Any]]:
    request = Request(
        f"{url}?{urlencode({'page': page, 'size': page_size})}",
        headers={"Accept": "application/json"},
    )
    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw_payload = response.read()
    except HTTPError as exc:
        raise BabysittingPlaceCollectorError(
            f"New Taipei {care_type} childcare API HTTP error: {exc.code} {exc.reason}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise BabysittingPlaceCollectorError(
            f"New Taipei {care_type} childcare API request failed: {exc}"
        ) from exc

    if isinstance(raw_payload, bytes):
        try:
            decoded_payload = raw_payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise BabysittingPlaceCollectorError(
                f"New Taipei {care_type} childcare API returned invalid UTF-8"
            ) from exc
    elif isinstance(raw_payload, str):
        decoded_payload = raw_payload
    else:
        raise BabysittingPlaceCollectorError(
            f"New Taipei {care_type} childcare API response body must be bytes or string"
        )

    try:
        payload = json.loads(decoded_payload)
    except json.JSONDecodeError as exc:
        raise BabysittingPlaceCollectorError(
            f"New Taipei {care_type} childcare API returned invalid JSON"
        ) from exc

    return _parse_records(payload, care_type=care_type)


def _parse_records(payload: Any, *, care_type: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        message = payload.get("message") if isinstance(payload, Mapping) else None
        suffix = f": {message}" if message else ""
        raise BabysittingPlaceCollectorError(
            f"New Taipei {care_type} childcare API response must be a JSON array{suffix}"
        )

    records: list[dict[str, Any]] = []
    for index, record in enumerate(payload):
        if not isinstance(record, dict) or not all(
            isinstance(key, str) for key in record
        ):
            raise BabysittingPlaceCollectorError(
                f"New Taipei {care_type} childcare API record {index} must be a JSON object"
            )
        records.append(record)
    return records
