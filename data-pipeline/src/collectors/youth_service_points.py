"""Collect New Taipei Youth Bureau startup-base detail pages."""

from __future__ import annotations

import hashlib
import re
import ssl
from collections.abc import Callable
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

from .contracts import CollectedPayload, SourceArtifact
from .ntpc_address_points import match_ntpc_address_points


SERVICE_POINTS_LIST_URL = (
    "https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?module=youth0001&id=145"
)
REQUEST_TIMEOUT_SECONDS = 120
MAX_HTML_BYTES = 10 * 1024 * 1024
OpenURL = Callable[..., Any]

_ANCHOR_PATTERN = re.compile(
    r"<a\b(?P<attributes>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL
)
_HREF_PATTERN = re.compile(r"\bhref\s*=\s*(['\"])(?P<href>.*?)\1", re.I | re.S)
_TITLE_PATTERN = re.compile(r"\btitle\s*=\s*(['\"])(?P<title>.*?)\1", re.I | re.S)
_CONTENT_PATTERN = re.compile(
    r"<div\b[^>]*class\s*=\s*(['\"])[^'\"]*\bed_txt\b[^'\"]*\1[^>]*>"
    r"(?P<body>.*?)</div>",
    re.I | re.S,
)
_NAME_PATTERN = re.compile(
    r"<div\b[^>]*class\s*=\s*(['\"])[^'\"]*\bd_title\b[^'\"]*\1[^>]*>"
    r"(?P<body>.*?)</div>",
    re.I | re.S,
)
_DATE_PATTERN = re.compile(
    r"(?:發佈|發布|更新)日期\s*[:：]?\s*(?P<date>\d{2,3}[-./]\d{1,2}[-./]\d{1,2})"
)
_ADDRESS_PATTERN = re.compile(
    r"(?:地址|聯絡地址)\s*[:：]\s*(?P<value>.+?)(?=\s*(?:Email|E-?mail|服務電話|聯絡電話|電話)\s*[:：]|$)",
    re.I,
)
_PHONE_PATTERN = re.compile(
    r"(?:服務電話|聯絡電話|電話)\s*[:：]\s*(?P<value>[0-9０-９()+\-、,，/\s]+)"
)
_EMAIL_PATTERN = re.compile(r"mailto:(?P<email>[^\"' >]+)", re.I)
_DISTRICT_PATTERN = re.compile(r"新北市(?P<district>[^\s,，]+區)")


class YouthServicePointCollectorError(RuntimeError):
    """Raised when the official startup-base roster cannot be collected."""


def _create_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        context.verify_flags &= ~strict_flag
    return context


def _open_url(url_or_request: str | Request, *, timeout: int = REQUEST_TIMEOUT_SECONDS) -> Any:
    request = url_or_request
    if isinstance(url_or_request, str):
        request = Request(
            url_or_request,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "NewTaipeiHack-data-pipeline/1.0",
            },
        )
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_youth_service_points(
    *,
    listing_url: str = SERVICE_POINTS_LIST_URL,
    open_url: OpenURL = _open_url,
) -> CollectedPayload:
    """Discover current startup-base detail pages and preserve source HTML."""

    listing_bytes = _request_bytes(listing_url, open_url=open_url)
    listing_html = _decode_html(listing_bytes)
    documents = _parse_listing_page(listing_html, page_url=listing_url)
    if not documents:
        raise YouthServicePointCollectorError("startup-base listing has no detail links")

    listing_artifact = _build_source_artifact(
        filename_prefix="youth_service_points_listing",
        content=listing_bytes,
        media_type="text/html",
        suffix="html",
    )
    artifacts: list[SourceArtifact] = [listing_artifact]
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    document_metadata: list[dict[str, Any]] = []

    for document in documents:
        try:
            detail_bytes = _request_bytes(document["detail_url"], open_url=open_url)
            detail_html = _decode_html(detail_bytes)
            parsed = _parse_detail_page(detail_html, document=document)
            artifact = _build_source_artifact(
                filename_prefix=f"youth_service_point_{document['point_id']}",
                content=detail_bytes,
                media_type="text/html",
                suffix="html",
            )
            artifacts.append(artifact)
            parsed.update(
                {
                    "source_html_sha256": artifact.sha256,
                    "artifact_filename": artifact.filename,
                    "listing_url": listing_url,
                }
            )
            records.append(parsed)
            document_metadata.append(
                {
                    "point_id": parsed["point_id"],
                    "name": parsed["name"],
                    "detail_url": parsed["detail_url"],
                    "address_present": parsed["address"] is not None,
                    "source_html_sha256": artifact.sha256,
                    "artifact_filename": artifact.filename,
                }
            )
        except YouthServicePointCollectorError as exc:
            failures.append(
                {
                    "point_id": document["point_id"],
                    "detail_url": document["detail_url"],
                    "reason": str(exc),
                }
            )

    if not records:
        detail = "; ".join(f"{item['point_id']}: {item['reason']}" for item in failures)
        raise YouthServicePointCollectorError(
            f"no startup-base detail page could be parsed"
            f"{': ' + detail if detail else ''}"
        )

    geocode_metadata: dict[str, Any] = {
        "geocode_provider": "ntpc_address_points",
        "geocode_requested_count": sum(bool(record.get("address")) for record in records),
    }
    try:
        geocode = match_ntpc_address_points(records, open_url=open_url)
        matches_by_point = {item.get("point_id"): item for item in geocode.matches}
        for record in records:
            match = matches_by_point.get(record.get("point_id"))
            if match is not None:
                record.update(match)
        geocode_metadata.update(geocode.metadata)
        artifacts.extend(geocode.artifacts)
    except Exception as exc:
        geocode_metadata.update({"geocode_status": "source_unavailable", "geocode_error": str(exc)})

    return CollectedPayload(
        records=records,
        metadata={
            "listing_url": listing_url,
            "discovered_count": len(documents),
            "successful_count": len(records),
            "document_failures": failures,
            "documents": document_metadata,
            "listing_artifact": listing_artifact.filename,
            **geocode_metadata,
        },
        artifacts=tuple(artifacts),
    )


def _parse_listing_page(html: str, *, page_url: str) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _ANCHOR_PATTERN.finditer(html):
        attributes = match.group("attributes")
        href_match = _HREF_PATTERN.search(attributes)
        if href_match is None:
            continue
        detail_url = urljoin(page_url, unescape(href_match.group("href")).strip())
        query = parse_qs(urlparse(detail_url).query)
        if query.get("module") != ["youth0001"] or query.get("id") != ["145"]:
            continue
        point_id = query.get("serno", [""])[0]
        if not point_id or point_id in seen:
            continue
        title_match = _TITLE_PATTERN.search(attributes)
        title = (
            _visible_text(title_match.group("title"))
            if title_match
            else _visible_text(match.group("body"))
        )
        documents.append(
            {
                "point_id": point_id,
                "name": title,
                "detail_url": detail_url,
            }
        )
        seen.add(point_id)
    return documents


def _parse_detail_page(html: str, *, document: dict[str, str]) -> dict[str, Any]:
    content_match = _CONTENT_PATTERN.search(html)
    content_html = content_match.group("body") if content_match else ""
    content_text = _visible_text(content_html)
    name_match = _NAME_PATTERN.search(html)
    name = _visible_text(name_match.group("body")) if name_match else document["name"]
    address_match = _ADDRESS_PATTERN.search(content_text)
    address = (
        _clean_address(address_match.group("value")) if address_match else None
    )
    phone_match = _PHONE_PATTERN.search(content_text)
    phone = _clean_field(phone_match.group("value")) if phone_match else None
    email_match = _EMAIL_PATTERN.search(html)
    email = unescape(email_match.group("email")).strip() if email_match else None
    dates = _DATE_PATTERN.findall(_visible_text(html))
    district_match = _DISTRICT_PATTERN.search(address or "")
    return {
        "point_id": document["point_id"],
        "point_type": "startup_base",
        "name": name or document["name"],
        "address": address,
        "source_district_name": district_match.group("district") if district_match else None,
        "phone": phone,
        "email": email,
        "published_date_raw": dates[0] if dates else None,
        "published_date_roc": _compact_roc_date(dates[0]) if dates else None,
        "updated_date_raw": dates[1] if len(dates) > 1 else None,
        "updated_date_roc": _compact_roc_date(dates[1]) if len(dates) > 1 else None,
        "detail_url": document["detail_url"],
        "content_text": content_text or None,
        "latitude": None,
        "longitude": None,
        "geocode_status": "not_attempted",
        "geocode_provider": None,
    }


def _build_source_artifact(
    *, filename_prefix: str, content: bytes, media_type: str, suffix: str
) -> SourceArtifact:
    if not content:
        raise YouthServicePointCollectorError("source HTML is empty")
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    filename = f"{_safe_filename(filename_prefix)}_{digest[7:19]}.{suffix}"
    return SourceArtifact(
        filename=filename,
        content=content,
        media_type=media_type,
        sha256=digest,
    )


def _request_bytes(url: str, *, open_url: OpenURL) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "NewTaipeiHack-data-pipeline/1.0",
        },
    )
    try:
        response = open_url(request, timeout=REQUEST_TIMEOUT_SECONDS)
        try:
            content = response.read(MAX_HTML_BYTES + 1)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise YouthServicePointCollectorError(f"Youth Bureau source request failed: {exc}") from exc
    if len(content) > MAX_HTML_BYTES:
        raise YouthServicePointCollectorError("source HTML exceeds size limit")
    return content


def _decode_html(content: bytes) -> str:
    for encoding in ("utf-8", "cp950", "big5"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise YouthServicePointCollectorError("source HTML returned unsupported encoding")


def _visible_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _clean_field(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", unescape(value)).strip() or None


def _clean_address(value: str | None) -> str | None:
    """Keep the address label value, excluding adjacent directions/hours."""

    if value is None:
        return None
    address = re.split(
        r"\s+(?:交通|開放時間)\s*[:：]|\s*【",
        unescape(value),
        maxsplit=1,
    )[0]
    return _clean_field(address)


def _compact_roc_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d{2,3})[-./](\d{1,2})[-./](\d{1,2})", value)
    if match is None:
        return None
    return f"{int(match.group(1)):03d}{int(match.group(2)):02d}{int(match.group(3)):02d}"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "source"
