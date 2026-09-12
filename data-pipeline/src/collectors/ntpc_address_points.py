"""Exact address matching against the official New Taipei address-point file."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import ssl
import unicodedata
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contracts import SourceArtifact


NTPC_ADDRESS_POINTS_URL = (
    "https://data.ntpc.gov.tw/api/datasets/"
    "d7b568ab-3819-40c8-a6e7-a6b199443101/csv/zip"
)
REQUEST_TIMEOUT_SECONDS = 180
MAX_ZIP_BYTES = 350 * 1024 * 1024
OpenURL = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class AddressMatchResult:
    matches: list[dict[str, Any]]
    metadata: dict[str, Any]
    artifacts: tuple[SourceArtifact, ...] = ()


class AddressPointCollectorError(RuntimeError):
    """Raised when the official address-point source cannot be read."""


def _open_url(url_or_request: str | Request, *, timeout: int = REQUEST_TIMEOUT_SECONDS) -> Any:
    request = url_or_request
    if isinstance(url_or_request, str):
        request = Request(
            url_or_request,
            headers={
                "Accept": "application/zip,application/octet-stream",
                "User-Agent": "NewTaipeiHack-data-pipeline/1.0",
            },
        )
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        context.verify_flags &= ~strict_flag
    return urlopen(request, timeout=timeout, context=context)


def match_ntpc_address_points(
    addresses: Iterable[Mapping[str, Any] | str], *, open_url: OpenURL = _open_url
) -> AddressMatchResult:
    """Return only unique exact address matches from the official CSV ZIP."""

    requested = [_requested_address(item) for item in addresses]
    requested = [item for item in requested if item["address"]]
    if not requested:
        return AddressMatchResult(
            matches=[],
            metadata={
                "source_url": NTPC_ADDRESS_POINTS_URL,
                "requested_count": 0,
                "matched_count": 0,
            },
        )
    content = _request_bytes(NTPC_ADDRESS_POINTS_URL, open_url=open_url)
    digest = hashlib.sha256(content).hexdigest()
    artifact = SourceArtifact(
        filename=f"ntpc_address_points_{digest[:12]}.zip",
        content=content,
        media_type="application/zip",
        sha256="sha256:" + digest,
    )
    match_rows, source_rows = _match_csv(content, requested)
    return AddressMatchResult(
        matches=match_rows,
        metadata={
            "source_url": NTPC_ADDRESS_POINTS_URL,
            "source_period": "latest",
            "requested_count": len(requested),
            "source_rows_scanned": source_rows,
            "matched_count": len(match_rows),
            "matching_policy": "unique_normalized_address_components",
        },
        artifacts=(artifact,),
    )


def _requested_address(item: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return {"point_id": item.get("point_id"), "address": item.get("address")}
    return {"point_id": None, "address": item}


def _request_bytes(url: str, *, open_url: OpenURL) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/zip,application/octet-stream",
            "User-Agent": "NewTaipeiHack-data-pipeline/1.0",
        },
    )
    try:
        response = open_url(request, timeout=REQUEST_TIMEOUT_SECONDS)
        try:
            content = response.read(MAX_ZIP_BYTES + 1)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise AddressPointCollectorError(f"NTPC address-point request failed: {exc}") from exc
    if len(content) > MAX_ZIP_BYTES:
        raise AddressPointCollectorError("NTPC address-point ZIP exceeds size limit")
    if not content:
        raise AddressPointCollectorError("NTPC address-point response is empty")
    return content


def _match_csv(content: bytes, requested: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    query_keys: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in requested:
        for key in _address_keys(item["address"]):
            query_keys[key].append(item)
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_rows = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            csv_members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_members:
                raise AddressPointCollectorError("NTPC address-point ZIP has no CSV member")
            with archive.open(csv_members[0], "r") as binary:
                text = io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline="")
                reader = csv.DictReader(text)
                for row in reader:
                    source_rows += 1
                    normalized = _normalize_source_row(row)
                    if normalized is None:
                        continue
                    for key in _source_address_keys(normalized):
                        if key in query_keys:
                            candidates[key].append(normalized)
                text.detach()
    except zipfile.BadZipFile as exc:
        raise AddressPointCollectorError("NTPC address-point response is not a ZIP") from exc
    matches: list[dict[str, Any]] = []
    for item in requested:
        item_candidates: dict[tuple[str, str], dict[str, Any]] = {}
        for key in _address_keys(item["address"]):
            for source in candidates.get(key, []):
                identity = (str(source["x_3826"]), str(source["y_3826"]))
                item_candidates[identity] = source
        if len(item_candidates) != 1:
            continue
        source = next(iter(item_candidates.values()))
        matches.append(
            {
                "point_id": item.get("point_id"),
                "address": item["address"],
                "geocode_status": "matched",
                "geocode_provider": "ntpc_address_points",
                "geocode_crs": "EPSG:3826",
                "x_3826": source["x_3826"],
                "y_3826": source["y_3826"],
                "geocode_source_period": "latest",
                "geocode_source_record": source,
            }
        )
    return matches, source_rows


def _normalize_source_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    values = {_header_key(key): value for key, value in row.items()}
    x = _number(_value(values, "x_3826", "x3826", "橫座標"))
    y = _number(_value(values, "y_3826", "y3826", "縱座標"))
    if x is None or y is None:
        return None
    result = {key: _clean(value) for key, value in values.items()}
    combined_street = _value(values, "street、road、section", "streetroadsection")
    if combined_street and not result.get("street"):
        result["street"] = _clean(combined_street)
    result["x_3826"] = x
    result["y_3826"] = y
    return result


def _source_address_keys(row: Mapping[str, Any]) -> set[str]:
    tail = "".join(
        part
        for name in ("section", "lane", "alley", "number")
        for part in (_clean(row.get(name)) or "",)
    )
    keys: set[str] = set()
    for base_name in ("street", "road", "area"):
        base = _clean(row.get(base_name)) or ""
        if base or tail:
            keys.add(_normalize_address(base + tail))
    return {key for key in keys if key}


def _address_keys(value: Any) -> set[str]:
    text = _clean(value)
    if not text:
        return set()
    normalized = _normalize_address(text)
    keys = {normalized, _strip_floor(normalized)}
    district_match = re.search(r"(?:新北市)?(?P<district>[^區]{1,5}區)(?P<rest>.*)", normalized)
    if district_match:
        rest = district_match.group("rest")
        keys.add(rest)
        keys.add(_strip_floor(rest))
    return {key for key in keys if key}


def _strip_floor(value: str) -> str:
    """Allow a source house number to match an address with floor text."""

    return re.sub(r"號[0-9]+(?:[、,][0-9]+)?樓.*$", "號", value)


def _normalize_address(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).replace("臺", "台")
    text = re.sub(r"新北市", "", text)
    text = re.sub(r"[^0-9A-Za-z\u3400-\u9fff]", "", text)
    return text


def _header_key(value: Any) -> str:
    return _normalize_address(value).lower().replace("縣市", "").replace("鄉鎮市區", "")


def _value(values: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        normalized = _header_key(key)
        if normalized in values:
            return values[normalized]
    return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return text or None


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


__all__ = [
    "AddressMatchResult",
    "AddressPointCollectorError",
    "NTPC_ADDRESS_POINTS_URL",
    "match_ntpc_address_points",
]
