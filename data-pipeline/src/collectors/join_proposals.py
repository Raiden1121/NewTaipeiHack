"""Collect nationwide public-policy proposals used as a youth-topic proxy."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import ssl
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

from .contracts import CollectedPayload


DATA_GOV_DATASET_URL = "https://data.gov.tw/dataset/58036"
JOIN_LIST_URL = "https://join.gov.tw/idea/"
REQUEST_TIMEOUT_SECONDS = 60
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
OpenURL = Callable[..., Any]

_ANCHOR_PATTERN = re.compile(
    r"<a\b(?P<attributes>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL
)
_HREF_PATTERN = re.compile(r"\bhref\s*=\s*(['\"])(?P<href>.*?)\1", re.I | re.S)
_FIELD_PATTERN = re.compile(
    r"(?:data-field\s*=\s*['\"](?P<field>[^'\"]+)['\"]|"
    r"(?P<label>提案編號|提案主旨|提案內容|附議人數|提案日期|權責機關|分類|狀態))"
    r"[^>]*>(?P<value>.*?)</", re.I | re.S
)
_ROC_DATE_PATTERN = re.compile(r"(?P<year>\d{2,3})[年./-](?P<month>\d{1,2})[月./-](?P<day>\d{1,2})日?")
_GREGORIAN_DATE_PATTERN = re.compile(
    r"(?P<year>\d{4})[年./-](?P<month>\d{1,2})[月./-](?P<day>\d{1,2})日?"
)
_COMPACT_DATE_PATTERN = re.compile(r"(?P<year>\d{3})(?P<month>\d{2})(?P<day>\d{2})")

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "proposal_id": ("proposal_id", "id", "提案編號", "提案ID", "案號"),
    "proposal_url": ("proposal_url", "url", "提案網址", "網址"),
    "title": ("title", "name", "提案主旨", "提案標題", "標題"),
    "content": ("content", "description", "提案內容", "提議內容", "內容", "說明"),
    "interest_impact": ("interest_impact", "公共利益", "利益與影響", "影響"),
    "endorsement_count": (
        "endorsement_count",
        "endorsements",
        "附議人數",
        "附議數量",
        "附議數",
    ),
    "endorsement_threshold": ("endorsement_threshold", "附議門檻"),
    "submitted_at": (
        "submitted_at",
        "submission_date",
        "提送日期",
        "提案日期",
        "提議日期",
        "publishDate",
    ),
    "published_at": ("published_at", "公告日期", "發布日期"),
    "status": ("status", "狀態", "提案狀態"),
    "agency": ("agency", "權責機關", "主管機關"),
    "category": ("category", "分類", "議題分類"),
}


class JoinProposalCollectorError(RuntimeError):
    """Raised when no usable join proposal source can be collected."""


@dataclass(frozen=True, slots=True)
class ProposalDocument:
    proposal_id: str
    detail_url: str
    title: str | None


def _create_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        context.verify_flags &= ~strict_flag
    return context


def _open_url(url: str, *, timeout: int = REQUEST_TIMEOUT_SECONDS, accept: str = "*/*") -> Any:
    request = Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "NewTaipeiHack-data-pipeline/1.0",
        },
    )
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_join_proposals(
    *,
    resource_urls: Sequence[str] | None = None,
    listing_url: str = JOIN_LIST_URL,
    open_url: OpenURL = _open_url,
) -> CollectedPayload:
    """Fetch open-data rows first, then fall back to join listing/detail pages."""

    failures: list[dict[str, str]] = []
    configured_resources = tuple(resource_urls) if resource_urls is not None else None
    discovered_resources = configured_resources
    if discovered_resources is None:
        try:
            dataset_html = _request_bytes(DATA_GOV_DATASET_URL, open_url=open_url, accept="text/html")
            discovered_resources = tuple(
                _discover_resource_urls(_decode_text(dataset_html), page_url=DATA_GOV_DATASET_URL)
            )
        except Exception as exc:  # pragma: no cover - live-source failure varies
            failures.append({"url": DATA_GOV_DATASET_URL, "reason": str(exc)})
            discovered_resources = ()

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    resource_failures: list[dict[str, str]] = []
    for source_url in discovered_resources or ():
        try:
            payload = _request_bytes(source_url, open_url=open_url, accept="application/json,text/csv,*/*")
            rows = _parse_resource_payload(payload, source_url=source_url)
            for row in rows:
                proposal_id = str(row.get("proposal_id") or _stable_id(row))
                if proposal_id in seen_ids:
                    continue
                row["proposal_id"] = proposal_id
                seen_ids.add(proposal_id)
                records.append(row)
        except Exception as exc:
            failure = {"url": source_url, "reason": str(exc)}
            resource_failures.append(failure)
            failures.append(failure)

    if records:
        return _payload(
            records,
            metadata={
                "source_mode": "data_gov",
                "resource_urls": list(discovered_resources or ()),
                "discovered_count": len(records),
                "successful_count": len(records),
                "skipped_count": 0,
                "failures": failures,
                "resource_failures": resource_failures,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    documents = _discover_listing_documents(listing_url, open_url=open_url, failures=failures)
    for document in documents:
        if document.proposal_id in seen_ids:
            continue
        try:
            detail_html = _decode_text(
                _request_bytes(document.detail_url, open_url=open_url, accept="text/html,application/xhtml+xml")
            )
            row = _parse_detail_page(
                detail_html,
                document=document,
            )
            seen_ids.add(document.proposal_id)
            records.append(row)
        except Exception as exc:
            failures.append({"url": document.detail_url, "reason": str(exc)})

    if not records:
        detail = "; ".join(f"{item['url']}: {item['reason']}" for item in failures[-5:])
        raise JoinProposalCollectorError(f"no join proposals could be collected{': ' + detail if detail else ''}")
    return _payload(
        records,
        metadata={
            "source_mode": "join_listing",
            "listing_url": listing_url,
            "discovered_count": len(documents),
            "successful_count": len(records),
            "skipped_count": max(0, len(documents) - len(records)),
            "failures": failures,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _parse_resource_payload(payload: Any, *, source_url: str) -> list[dict[str, Any]]:
    if isinstance(payload, bytes):
        text = _decode_text(payload)
        stripped = text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            payload = json.loads(text)
        else:
            return _parse_csv(text, source_url=source_url)
    if isinstance(payload, str):
        return _parse_resource_payload(payload.encode("utf-8"), source_url=source_url)
    rows = _rows_from_payload(payload)
    return [_normalize_row(row, source_url=source_url) for row in rows]


def _parse_listing_page(html: str, *, page_url: str) -> list[ProposalDocument]:
    documents: list[ProposalDocument] = []
    seen: set[str] = set()
    for match in _ANCHOR_PATTERN.finditer(html):
        href_match = _HREF_PATTERN.search(match.group("attributes"))
        if href_match is None:
            continue
        href = unescape(href_match.group("href")).strip()
        absolute_url = urljoin(page_url, href)
        parsed = urlparse(absolute_url)
        path_parts = [part for part in parsed.path.split("/") if part]
        if not path_parts or not any("proposal" in part.lower() or "idea" in part.lower() for part in path_parts):
            continue
        proposal_id = path_parts[-1] or parse_qs(parsed.query).get("id", [""])[0]
        if not proposal_id or proposal_id in seen:
            continue
        title = _visible_text(match.group("body")) or None
        documents.append(ProposalDocument(proposal_id, absolute_url, title))
        seen.add(proposal_id)
    return documents


def _parse_detail_page(html: str, *, document: ProposalDocument) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for match in _FIELD_PATTERN.finditer(html):
        key = match.group("field") or match.group("label")
        fields[key] = _visible_text(match.group("value"))
    title_match = re.search(r"<h1\b[^>]*>(?P<value>.*?)</h1>", html, re.I | re.S)
    content_match = re.search(
        r"<[^>]+class=['\"][^'\"]*(?:content|description)[^'\"]*['\"][^>]*>(?P<value>.*?)</",
        html,
        re.I | re.S,
    )
    if title_match:
        fields.setdefault("title", _visible_text(title_match.group("value")))
    if content_match:
        fields.setdefault("content", _visible_text(content_match.group("value")))
    fields.setdefault("proposal_id", document.proposal_id)
    fields.setdefault("proposal_url", document.detail_url)
    return _normalize_row(fields, source_url=document.detail_url, fallback_title=document.title)


def _normalize_row(
    source_row: Mapping[str, Any], *, source_url: str, fallback_title: str | None = None
) -> dict[str, Any]:
    source_payload = dict(source_row)
    values: dict[str, Any] = {}
    for canonical, aliases in _FIELD_ALIASES.items():
        values[canonical] = _first_value(source_row, aliases)
    values["title"] = _clean_text(values["title"] or fallback_title)
    values["content"] = _clean_text(values["content"])
    values["proposal_url"] = _clean_text(values["proposal_url"] or source_url)
    values["proposal_id"] = _clean_text(values["proposal_id"])
    if values["proposal_id"] is None:
        values["proposal_id"] = _stable_id(source_payload)
    values["endorsement_count"] = _optional_int(values["endorsement_count"])
    values["endorsement_threshold"] = _optional_int(values["endorsement_threshold"])
    for key in ("interest_impact", "submitted_at", "published_at", "status", "agency", "category"):
        values[key] = _clean_text(values[key])
    submitted = values["submitted_at"]
    values["year_roc"] = _year_roc(submitted)
    values["source_payload"] = source_payload
    return values


def _discover_listing_documents(
    listing_url: str, *, open_url: OpenURL, failures: list[dict[str, str]]
) -> list[ProposalDocument]:
    try:
        html = _decode_text(_request_bytes(listing_url, open_url=open_url, accept="text/html"))
    except Exception as exc:
        failures.append({"url": listing_url, "reason": str(exc)})
        return []
    documents = _parse_listing_page(html, page_url=listing_url)
    next_url = _next_page_url(html, page_url=listing_url)
    seen = {item.proposal_id for item in documents}
    for _ in range(1, 100):
        if not next_url:
            break
        try:
            page_html = _decode_text(_request_bytes(next_url, open_url=open_url, accept="text/html"))
        except Exception as exc:
            failures.append({"url": next_url, "reason": str(exc)})
            break
        for item in _parse_listing_page(page_html, page_url=next_url):
            if item.proposal_id not in seen:
                documents.append(item)
                seen.add(item.proposal_id)
        next_url = _next_page_url(page_html, page_url=next_url)
    return documents


def _discover_resource_urls(html: str, *, page_url: str) -> list[str]:
    urls: list[str] = []
    for match in _ANCHOR_PATTERN.finditer(html):
        href_match = _HREF_PATTERN.search(match.group("attributes"))
        if href_match is None:
            continue
        href = unescape(href_match.group("href")).strip()
        label = _visible_text(match.group("body"))
        if any(token in f"{href} {label}".lower() for token in ("json", "csv", "download", "resource")):
            absolute = urljoin(page_url, href)
            if absolute not in urls:
                urls.append(absolute)
    return urls


def _next_page_url(html: str, *, page_url: str) -> str | None:
    match = re.search(r"<a\b[^>]*(?:rel=['\"]next['\"]|class=['\"][^'\"]*next)[^>]*>", html, re.I)
    if match:
        href_match = _HREF_PATTERN.search(match.group(0))
        if href_match:
            return urljoin(page_url, unescape(href_match.group("href")).strip())
    return None


def _rows_from_payload(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, Mapping):
        rows = payload.get("data") or payload.get("records") or payload.get("result")
        if isinstance(rows, Mapping):
            rows = rows.get("records") or rows.get("data")
    else:
        rows = None
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise JoinProposalCollectorError("resource payload must contain an array of objects")
    return list(rows)


def _parse_csv(text: str, *, source_url: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    return [_normalize_row(row, source_url=source_url) for row in reader]


def _request_bytes(url: str, *, open_url: OpenURL, accept: str) -> bytes:
    response = open_url(url, timeout=REQUEST_TIMEOUT_SECONDS, accept=accept)
    if isinstance(response, bytes):
        data = response
    elif isinstance(response, str):
        data = response.encode("utf-8")
    else:
        with response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise JoinProposalCollectorError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
    return data


def _payload(records: list[dict[str, Any]], *, metadata: dict[str, Any]) -> CollectedPayload:
    return CollectedPayload(records=records, metadata=metadata, artifacts=())


def _first_value(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for key in aliases:
        if key in row:
            return row[key]
    return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return text or None


def _visible_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    match = re.search(r"\d[\d,]*", str(value))
    if not match:
        return None
    return int(match.group(0).replace(",", ""))


def _year_roc(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    match = _GREGORIAN_DATE_PATTERN.search(text)
    if match:
        return str(int(match.group("year")) - 1911)
    match = _COMPACT_DATE_PATTERN.search(text) or _ROC_DATE_PATTERN.search(text)
    if match:
        year = int(match.group("year"))
        if year > 1911:
            year -= 1911
        return str(year)
    try:
        return str(datetime.fromisoformat(text.replace("Z", "+00:00")).year - 1911)
    except ValueError:
        return None


def _stable_id(row: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _decode_text(payload: bytes) -> str:
    return payload.decode("utf-8-sig", errors="replace")
