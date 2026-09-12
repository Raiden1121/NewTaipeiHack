"""Collect and snapshot New Taipei Youth Bureau meeting-record PDFs."""

from __future__ import annotations

import hashlib
import io
import re
import ssl
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from html import unescape
from typing import Any, Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .contracts import CollectedPayload, SourceArtifact

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - dependency is declared in requirements.txt
    PdfReader = None  # type: ignore[assignment,misc]


MINUTES_LIST_URL = (
    "https://www.youth.ntpc.gov.tw/youth/ch/app/artwebsite/view?"
    "id=200&module=artwebsite&serno=2e4f0428-1fc7-41dd-92a8-6555183229be"
)
REQUEST_TIMEOUT_SECONDS = 120
MAX_PDF_BYTES = 50 * 1024 * 1024
OpenURL = Callable[..., Any]

_ANCHOR_PATTERN = re.compile(
    r"<a\b(?P<attributes>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL
)
_HREF_PATTERN = re.compile(r"\bhref\s*=\s*(['\"])(?P<href>.*?)\1", re.I | re.S)
_DATE_PATTERN = re.compile(
    r"(?P<year>\d{2,3})\s*[年./-]\s*(?P<month>\d{1,2})\s*[月./-]\s*(?P<day>\d{1,2})\s*日?"
)
_COMPACT_DATE_PATTERN = re.compile(r"(?P<year>\d{3})(?P<month>\d{2})(?P<day>\d{2})")
_TERM_PATTERN = re.compile(r"第\s*(?P<term>[一二三四五六七八九十百\d]+)\s*屆")


class YouthCouncilMinutesCollectorError(RuntimeError):
    """Raised when meeting records cannot be safely collected or parsed."""


@dataclass(frozen=True, slots=True)
class MeetingDocument:
    meeting_id: str
    meeting_name: str
    meeting_date: str | None
    term: str | None
    detail_url: str
    pdf_url: str | None = None


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


def fetch_youth_council_minutes(
    *, listing_url: str = MINUTES_LIST_URL, open_url: OpenURL = _open_url
) -> CollectedPayload:
    listing_html = _decode_html(_request_bytes(listing_url, open_url=open_url, accept="text/html"))
    documents = _parse_listing_page(listing_html, page_url=listing_url)
    if not documents:
        raise YouthCouncilMinutesCollectorError("meeting listing has no documents")

    records: list[dict[str, Any]] = []
    artifacts: list[SourceArtifact] = []
    failures: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    document_metadata: list[dict[str, Any]] = []

    for document in documents:
        try:
            detail_bytes = _request_bytes(
                document.detail_url,
                open_url=open_url,
                accept="application/pdf,text/html,application/xhtml+xml",
            )
            if _is_pdf(detail_bytes):
                pdf_bytes = _validate_pdf_bytes(detail_bytes)
                resolved = replace(document, pdf_url=document.detail_url)
            else:
                detail_html = _decode_html(detail_bytes)
                detail_date = _extract_meeting_date(_visible_text(detail_html))
                if not resolved.meeting_date and detail_date:
                    resolved = replace(resolved, meeting_date=detail_date)
                pdf_url = _find_pdf_url(detail_html, page_url=document.detail_url)
                if pdf_url is None:
                    raise YouthCouncilMinutesCollectorError("meeting detail has no PDF link")
                pdf_bytes = _validate_pdf_bytes(
                    _request_bytes(pdf_url, open_url=open_url, accept="application/pdf")
                )
                resolved = replace(resolved, pdf_url=pdf_url)
            pages = _extract_pdf_pages(pdf_bytes)
            if not resolved.meeting_date:
                page_date = _extract_meeting_date("\n".join(pages))
                if page_date:
                    resolved = replace(resolved, meeting_date=page_date)
            if not resolved.meeting_date:
                raise YouthCouncilMinutesCollectorError("meeting date is missing")
            artifact = _build_source_artifact(resolved, pdf_bytes)
            key = (resolved.meeting_id, artifact.sha256)
            if key in seen:
                continue
            seen.add(key)
            artifacts.append(artifact)
            year_roc = _year_roc(resolved.meeting_date)
            record = {
                "meeting_id": resolved.meeting_id,
                "meeting_name": resolved.meeting_name,
                "meeting_date": resolved.meeting_date,
                "term": resolved.term,
                "year_roc": year_roc,
                "detail_url": resolved.detail_url,
                "pdf_url": resolved.pdf_url,
                "source_pdf_sha256": artifact.sha256,
                "artifact_filename": artifact.filename,
                "page_texts": pages,
            }
            records.append(record)
            document_metadata.append(
                {
                    key: record[key]
                    for key in (
                        "meeting_id",
                        "meeting_name",
                        "meeting_date",
                        "term",
                        "year_roc",
                        "detail_url",
                        "pdf_url",
                        "source_pdf_sha256",
                        "artifact_filename",
                    )
                }
                | {"page_count": len(pages)}
            )
        except Exception as exc:
            failures.append(
                {
                    "meeting_id": document.meeting_id,
                    "detail_url": document.detail_url,
                    "reason": str(exc),
                }
            )

    if not records:
        raise YouthCouncilMinutesCollectorError(
            "no youth council minutes could be parsed"
            + (f": {failures[0]['reason']}" if failures else "")
        )
    return CollectedPayload(
        records=records,
        metadata={
            "listing_url": listing_url,
            "documents": document_metadata,
            "discovered_count": len(documents),
            "successful_count": len(records),
            "skipped_count": len(failures),
            "failures": failures,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        artifacts=tuple(artifacts),
    )


def _parse_listing_page(html: str, *, page_url: str) -> list[MeetingDocument]:
    documents: list[MeetingDocument] = []
    seen: set[tuple[str, str]] = set()
    for match in _ANCHOR_PATTERN.finditer(html):
        href_match = _HREF_PATTERN.search(match.group("attributes"))
        if href_match is None:
            continue
        href = unescape(href_match.group("href")).strip()
        detail_url = urljoin(page_url, href)
        body = _visible_text(match.group("body"))
        date_match = _DATE_PATTERN.search(body) or _COMPACT_DATE_PATTERN.search(body)
        meeting_date = date_match.group(0) if date_match else None
        term_match = _TERM_PATTERN.search(body)
        term = f"第{term_match.group('term')}屆" if term_match else None
        meeting_name = _clean_name(body, date_match.group(0) if date_match else None, term)
        meeting_id = _stable_id(detail_url)
        key = (meeting_id, detail_url)
        if key in seen:
            continue
        seen.add(key)
        documents.append(
            MeetingDocument(
                meeting_id=meeting_id,
                meeting_name=meeting_name or "青年局會議紀錄",
                meeting_date=meeting_date,
                term=term,
                detail_url=detail_url,
            )
        )
    return documents


def _extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    if PdfReader is None:
        raise YouthCouncilMinutesCollectorError("pypdf is required to extract meeting PDFs")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise YouthCouncilMinutesCollectorError(f"PDF text extraction failed: {exc}") from exc


def _build_source_artifact(document: MeetingDocument, pdf_bytes: bytes) -> SourceArtifact:
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", document.meeting_id).strip("_") or "meeting"
    return SourceArtifact(
        filename=f"{safe_id}_{digest[:16]}.pdf",
        content=pdf_bytes,
        media_type="application/pdf",
        sha256=f"sha256:{digest}",
    )


def _request_bytes(url: str, *, open_url: OpenURL, accept: str) -> bytes:
    response = open_url(url, timeout=REQUEST_TIMEOUT_SECONDS, accept=accept)
    if isinstance(response, bytes):
        data = response
    elif isinstance(response, str):
        data = response.encode("utf-8")
    else:
        with response:
            data = response.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise YouthCouncilMinutesCollectorError(f"PDF response exceeds {MAX_PDF_BYTES} bytes")
    return data


def _validate_pdf_bytes(pdf_bytes: bytes) -> bytes:
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
        raise YouthCouncilMinutesCollectorError("source is not a PDF")
    return pdf_bytes


def _is_pdf(payload: bytes) -> bool:
    return payload.startswith(b"%PDF-")


def _find_pdf_url(html: str, *, page_url: str) -> str | None:
    for match in _ANCHOR_PATTERN.finditer(html):
        href_match = _HREF_PATTERN.search(match.group("attributes"))
        if href_match is None:
            continue
        href = unescape(href_match.group("href")).strip()
        body = _visible_text(match.group("body"))
        if ".pdf" in href.lower() or "pdf" in body.lower() or "下載" in body:
            return urljoin(page_url, href)
    return None


def _year_roc(value: str) -> str | None:
    match = _COMPACT_DATE_PATTERN.search(value) or _DATE_PATTERN.search(value)
    if match is None:
        return None
    year = int(match.group("year"))
    return str(year - 1911 if year > 1911 else year)


def _extract_meeting_date(value: str) -> str | None:
    match = _DATE_PATTERN.search(value) or _COMPACT_DATE_PATTERN.search(value)
    return match.group(0) if match else None


def _clean_name(value: str, date_text: str | None, term: str | None) -> str:
    result = value
    if date_text:
        result = result.replace(date_text, "")
    if term:
        result = result.replace(term, "")
    return re.sub(r"\s+", " ", result).strip(" -_，,：:")


def _visible_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _decode_html(payload: bytes) -> str:
    return payload.decode("utf-8-sig", errors="replace")


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
