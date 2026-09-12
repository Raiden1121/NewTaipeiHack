"""Exact address matching against the official New Taipei address-point file."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import ssl
import unicodedata
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
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
# Several official door plates share one street address (one per unit or per
# floor). Candidates inside this radius are treated as the same building and
# collapsed to their centroid; anything wider stays ambiguous.
SAME_BUILDING_RADIUS_M = 150.0
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
        address = item.get("address")
        district = _clean(
            item.get("district_code") or item.get("areacode") or item.get("district_id")
        )
        return {
            "point_id": item.get("point_id"),
            "address": address,
            "district_code": district or _district_code_from_address(address),
        }
    return {
        "point_id": None,
        "address": item,
        "district_code": _district_code_from_address(item),
    }


_DISTRICT_CODES: dict[str, str] | None = None


def _district_name_to_code() -> dict[str, str]:
    """Map district name -> official code, read once from the shared config."""

    global _DISTRICT_CODES
    if _DISTRICT_CODES is None:
        path = Path(__file__).resolve().parents[2] / "config" / "districts.json"
        mapping: dict[str, str] = {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for row in payload.get("districts", []):
                code = _clean(row.get("district_id"))
                name = _clean(row.get("district_name"))
                if code and name:
                    mapping[name] = code
        except (OSError, ValueError, AttributeError, TypeError):
            mapping = {}
        _DISTRICT_CODES = mapping
    return _DISTRICT_CODES


def _district_code_from_address(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    match = re.search(r"(?P<district>[^\s市區]{1,5}區)", _normalize_address(text))
    if match is None:
        return None
    return _district_name_to_code().get(match.group("district"))


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


def _resolve_candidates(rows: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """Collapse door plates that describe one building; reject real ambiguity."""

    if not rows:
        return None
    by_point: dict[tuple[float, float], Mapping[str, Any]] = {}
    counts: Counter[tuple[float, float]] = Counter()
    for row in rows:
        point = (float(row["x_3826"]), float(row["y_3826"]))
        by_point.setdefault(point, row)
        counts[point] += 1
    points = list(by_point)
    if len(points) == 1:
        return by_point[points[0]]
    centre_x = sum(point[0] for point in points) / len(points)
    centre_y = sum(point[1] for point in points) / len(points)
    spread = max(math.dist(point, (centre_x, centre_y)) for point in points)
    if spread <= SAME_BUILDING_RADIUS_M:
        nearest = min(points, key=lambda point: math.dist(point, (centre_x, centre_y)))
        return {**by_point[nearest], "x_3826": centre_x, "y_3826": centre_y}
    # One outlier among many identical plates is a bad row in the official
    # file, not a genuine second address.
    (top, top_count), = counts.most_common(1)
    if top_count >= 2 * (sum(counts.values()) - top_count) + 1:
        return by_point[top]
    return None


def _match_csv(content: bytes, requested: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    query_keys: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in requested:
        for key in _address_keys(item["address"], item.get("district_code")):
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
        source = None
        for tier in _address_key_tiers(item["address"], item.get("district_code")):
            rows = [row for key in tier for row in candidates.get(key, [])]
            source = _resolve_candidates(rows)
            if source is not None:
                break
        if source is None:
            continue
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


_CJK_DIGITS = "一二三四五六七八九十"
_PARENTHETICAL = re.compile(r"[（(][^）)]*[）)]")
_FLOOR_SUFFIX = re.compile(
    r"號\s*(?:[0-9]+|[一二三四五六七八九十]+)?\s*(?:樓|層|[FfBb][0-9]*).*$"
)


def _cjk_digit_value(text: str) -> int | None:
    return _CJK_DIGITS.index(text) + 1 if text in _CJK_DIGITS else None


def _pre_normalize(value: str) -> str:
    """Rewrite door-plate punctuation while the separators are still present."""

    text = unicodedata.normalize("NFKC", str(value)).replace("臺", "台")
    # 巿 (U+5DFF) is a look-alike that appears in hand-typed source addresses.
    text = text.replace("巿", "市")
    text = _PARENTHETICAL.sub("", text)
    text = re.sub(r"新北市", "", text)
    # 「19號之一」「19號之1」-> 「19之1號」, matching the official plate order.
    text = re.sub(
        r"號之([一二三四五六七八九十])",
        lambda m: f"之{_cjk_digit_value(m.group(1))}號",
        text,
    )
    text = re.sub(r"號之([0-9]+)", r"之\1號", text)
    # 「165-1號」-> 「165之1號」 (only hyphens inside a door plate).
    text = re.sub(r"([0-9]+)\s*[-–—]\s*([0-9]+)(?=\s*(?:[、,.]|及|號))", r"\1之\2", text)
    # 「8、10、12、16號」-> 「8號」: keep the first plate of a listed range.
    text = re.sub(
        r"([0-9]+(?:之[0-9]+)?)(?:\s*[、,.]\s*|及)"
        r"(?:[0-9]+(?:之[0-9]+)?(?:\s*[、,.]\s*|及))*"
        r"([0-9]+(?:之[0-9]+)?)\s*號",
        r"\1號",
        text,
    )
    return text


def _normalize_address(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]", "", _pre_normalize(value))


def _strip_floor(value: str) -> str:
    """Drop the floor/unit text that follows a door plate, keeping the plate."""

    return _FLOOR_SUFFIX.sub("號", value)


def _section_variants(value: str) -> set[str]:
    """Official plates spell 段 in CJK digits; sources use both spellings."""

    variants = {value}
    variants.add(
        re.sub(
            r"([一二三四五六七八九十])段",
            lambda m: f"{_cjk_digit_value(m.group(1))}段",
            value,
        )
    )
    variants.add(
        re.sub(
            r"([0-9]{1,2})段",
            lambda m: (
                _CJK_DIGITS[int(m.group(1)) - 1] + "段"
                if 1 <= int(m.group(1)) <= len(_CJK_DIGITS)
                else m.group(0)
            ),
            value,
        )
    )
    return {item for item in variants if item}


def _plate_variants(value: str) -> set[str]:
    return {value, value.replace("之", "-"), re.sub(r"([0-9]+)-([0-9]+)", r"\1之\2", value)}


def _drop_sub_plate(value: str) -> str:
    """「53之4號」-> 「53號」, so a block with only sub-plates can still match."""

    return re.sub(r"([0-9]+)之[0-9]+號", r"\1號", value)


def _expand(value: str) -> set[str]:
    keys: set[str] = set()
    for plate in _plate_variants(value):
        keys |= _section_variants(plate)
    return {key for key in keys if key}


def _scoped(district_code: str | None, keys: Iterable[str]) -> set[str]:
    prefix = f"{district_code}|" if district_code else ""
    return {f"{prefix}{key}" for key in keys}


def _truncate_at_plate(value: str) -> str:
    """Keep everything up to the first 號, dropping floors and building names."""

    index = value.find("號")
    return value[: index + 1] if index >= 0 else value


def _strip_locality_prefix(value: str) -> str:
    """Drop district/village/neighbour prefixes, keeping the street onwards.

    The district has to go first: stripping a village would otherwise eat the
    district name itself for 八里區, whose name ends in 里.
    """

    text = value
    for _ in range(3):
        match = re.match(r"(?P<district>[^區]{1,4}區)(?P<rest>.+)", text)
        if match is None:
            break
        text = match.group("rest")
    for _ in range(2):
        text = re.sub(r"^[0-9]{1,4}鄰", "", text)
        # Safe once the district is gone: no New Taipei street name ends in 里,
        # but villages are often written in front of the street (or of a bare
        # place name such as 後湖).
        text = re.sub(r"^[^0-9]{1,5}里", "", text)
    return text or value


def _address_key_tiers(value: Any, district_code: str | None = None) -> list[set[str]]:
    """Key sets ordered from the most literal reading to the loosest."""

    text = _clean(value)
    if not text:
        return []
    rest = _strip_locality_prefix(_normalize_address(text))
    stripped = _strip_floor(rest)
    candidates = [
        {rest},
        {stripped},
        {_truncate_at_plate(stripped)},
        {_drop_sub_plate(_truncate_at_plate(stripped))},
    ]
    expanded: list[set[str]] = []
    for group in candidates:
        keys: set[str] = set()
        for item in group:
            keys |= _expand(item)
        if keys and keys not in expanded:
            expanded.append(keys)
    if not district_code:
        return expanded
    # Every district-scoped reading is tried before any unscoped one, so a
    # street name shared across districts can no longer collide. The unscoped
    # pass still runs last for sources whose rows carry no district column.
    tiers = [_scoped(district_code, keys) for keys in expanded]
    tiers.extend(expanded)
    return tiers


def _address_keys(value: Any, district_code: str | None = None) -> set[str]:
    keys: set[str] = set()
    for tier in _address_key_tiers(value, district_code):
        keys |= tier
    return keys


def _source_address_keys(row: Mapping[str, Any]) -> set[str]:
    district_code = _clean(row.get("areacode"))
    middle = "".join(
        _normalize_address(_clean(row.get(name)) or "")
        for name in ("section", "area", "lane", "alley")
    )
    number = _normalize_address(_clean(row.get("number")) or "")
    keys: set[str] = set()
    for base_name in ("street", "road"):
        base = _normalize_address(_clean(row.get(base_name)) or "")
        if not (base or middle or number):
            continue
        for plate in {number, _strip_floor(number), _drop_sub_plate(_strip_floor(number))}:
            if not (base or middle or plate):
                continue
            keys |= _expand(base + middle + plate)
    return _scoped(district_code, keys) | keys


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
