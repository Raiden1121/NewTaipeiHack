"""Collect Youth Bureau civil-organization grant detail PDFs."""

from __future__ import annotations

import hashlib
import io
import re
import ssl
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .contracts import CollectedPayload, SourceArtifact

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment,misc]


GRANT_LIST_URL = (
    "https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?id=112&module=youth0008"
)
REQUEST_TIMEOUT_SECONDS = 120
MAX_PDF_BYTES = 50 * 1024 * 1024
_ANCHOR_PATTERN = re.compile(
    r"<a\b(?P<attributes>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL
)
_HREF_PATTERN = re.compile(
    r"\bhref\s*=\s*(['\"])(?P<href>.*?)\1", re.IGNORECASE | re.DOTALL
)
_YEAR_PATTERN = re.compile(r"(?:新北市政府)?(?P<year>\d{3})年度")
_AMOUNT_PATTERN = re.compile(r"(?P<amount>\d[\d,]*)\s+(?:無|有)\s+(?:V|v)?\s*$")
_GENERIC_AMOUNT_PATTERN = re.compile(r"(?P<amount>\d[\d,]*)\s*$")
_WORK_PLAN_MARKERS = (
    "青年發展業務",
    "青年事務",
    "經濟發展及輔導",
)
OpenURL = Callable[..., Any]


class YouthGrantCollectorError(RuntimeError):
    """Raised when the official grant source cannot be safely collected."""


@dataclass(frozen=True, slots=True)
class GrantDocument:
    year_roc: str
    title: str
    detail_url: str
    pdf_url: str | None = None


def _create_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int = REQUEST_TIMEOUT_SECONDS) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_youth_grants(
    *,
    list_url: str = GRANT_LIST_URL,
    open_url: OpenURL = _open_url,
    years: Sequence[str] | None = None,
) -> CollectedPayload:
    """Discover official annual grant PDFs and parse their row-wise tables."""

    selected = _normalize_years(years)
    listing_html = _request_text(list_url, open_url=open_url)
    documents = _parse_listing_page(listing_html, page_url=list_url)
    if selected is not None:
        documents = [document for document in documents if document.year_roc in selected]
    if not documents:
        suffix = f" for years {sorted(selected)}" if selected else ""
        raise YouthGrantCollectorError(f"grant listing has no matching annual documents{suffix}")

    records: list[dict[str, Any]] = []
    artifacts: list[SourceArtifact] = []
    document_metadata: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for document in documents:
        try:
            detail_bytes = _request_bytes(
                document.detail_url,
                open_url=open_url,
                accept="text/html,application/xhtml+xml,application/pdf",
            )
            if detail_bytes.startswith(b"%PDF-"):
                pdf_url = document.detail_url
                pdf_bytes = _validate_pdf(detail_bytes)
            else:
                detail_html = _decode_html(detail_bytes)
                pdf_url = _find_pdf_url(detail_html, page_url=document.detail_url)
                if pdf_url is None:
                    raise YouthGrantCollectorError("detail page does not expose a PDF link")
                pdf_bytes = _validate_pdf(
                    _request_bytes(pdf_url, open_url=open_url, accept="application/pdf")
                )
            digest = "sha256:" + hashlib.sha256(pdf_bytes).hexdigest()
            key = (document.year_roc, digest)
            if key in seen:
                continue
            seen.add(key)
            artifact = SourceArtifact(
                filename=f"{document.year_roc}_grant_{digest[7:19]}.pdf",
                content=pdf_bytes,
                media_type="application/pdf",
                sha256=digest,
            )
            artifacts.append(artifact)
            pages = _extract_pdf_pages(pdf_bytes)
            parsed = _parse_grant_pages(
                pages,
                document=document,
                source_pdf_sha256=digest,
                source_pdf_url=pdf_url,
            )
            if not parsed:
                raise YouthGrantCollectorError("grant table was found but no rows were parsed")
            records.extend(parsed)
            document_metadata.append(
                {
                    "year_roc": document.year_roc,
                    "title": document.title,
                    "detail_url": document.detail_url,
                    "pdf_url": pdf_url,
                    "source_pdf_sha256": digest,
                    "artifact_filename": artifact.filename,
                    "row_count": len(parsed),
                }
            )
        except YouthGrantCollectorError as exc:
            failures.append(
                {"year_roc": document.year_roc, "title": document.title, "url": document.detail_url, "reason": str(exc)}
            )

    if not records:
        detail = "; ".join(f"{item['year_roc']}: {item['reason']}" for item in failures)
        raise YouthGrantCollectorError(f"no valid youth grant document could be parsed{': ' + detail if detail else ''}")
    return CollectedPayload(
        records=records,
        metadata={
            "list_url": list_url,
            "selected_years": list(selected) if selected else None,
            "documents": document_metadata,
            "document_failures": failures,
            "source_unit": "TWD_thousand",
        },
        artifacts=tuple(artifacts),
    )


def _parse_listing_page(html: str, *, page_url: str) -> list[GrantDocument]:
    documents: list[GrantDocument] = []
    seen: set[tuple[str, str]] = set()
    for match in _ANCHOR_PATTERN.finditer(html):
        href_match = _HREF_PATTERN.search(match.group("attributes"))
        if href_match is None:
            continue
        title = _visible_text(match.group("body"))
        year_match = _YEAR_PATTERN.search(_compact(title))
        if year_match is None:
            continue
        href = urljoin(page_url, unescape(href_match.group("href")).strip())
        key = (year_match.group("year"), href)
        if key in seen:
            continue
        seen.add(key)
        documents.append(GrantDocument(key[0], title, href))
    return documents


def _parse_grant_pages(
    pages: Sequence[str], *, document: GrantDocument, source_pdf_sha256: str,
    source_pdf_url: str | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page_number, page in enumerate(pages, start=1):
        lines = _normalized_lines(page)
        if not any("補" in line and "助" in line for line in lines):
            continue
        current: list[str] | None = None
        for line in lines:
            if _is_header_line(line):
                continue
            if _is_work_plan(line):
                if current:
                    current = None
                current = [line]
                if _looks_like_amount_row(line):
                    parsed = _parse_current_grant(
                        current, document=document, page_number=page_number,
                        source_pdf_sha256=source_pdf_sha256, source_pdf_url=source_pdf_url,
                        row_number=len(records) + 1,
                    )
                    if parsed is not None:
                        records.append(parsed)
                    current = None
                continue
            if current is None:
                continue
            current.append(line)
            amount_match = _AMOUNT_PATTERN.search(line) or _GENERIC_AMOUNT_PATTERN.search(line)
            if amount_match is None or not _looks_like_amount_row(line):
                continue
            parsed = _parse_current_grant(
                current, document=document, page_number=page_number,
                source_pdf_sha256=source_pdf_sha256, source_pdf_url=source_pdf_url,
                row_number=len(records) + 1,
            )
            if parsed is not None:
                records.append(parsed)
            current = None
    return records


def _split_grant_fields(fields: list[str]) -> tuple[str, str, str, str] | None:
    if not fields:
        return None
    first = fields[0]
    work_plan = next((marker for marker in _WORK_PLAN_MARKERS if first.startswith(marker)), first)
    first_remainder = first[len(work_plan) :].strip()
    fields = [work_plan, *([first_remainder] if first_remainder else []), *fields[1:]]
    agency = "新北市政府青年局"
    agency_start = None
    for index, value in enumerate(fields[1:], start=1):
        marker_index = value.find("新北市政府")
        if marker_index < 0:
            continue
        before = value[:marker_index].strip()
        after = value[marker_index:].strip()
        agency = " ".join([after, *fields[index + 1 :]])
        fields = fields[:index] + ([before] if before else [])
        agency_start = index
        break
    if agency_start is None:
        # Older PDFs sometimes put the agency on a separate, wrapped line.
        agency_start = next(
            (index for index, value in enumerate(fields[1:], start=1) if "新北市政府" in value),
            None,
        )
        if agency_start is not None:
            agency = " ".join(fields[agency_start:])
            fields = fields[:agency_start]
    if len(fields) < 2:
        return None
    content = " ".join(fields[1:])
    content = _join_wrapped_company_words(content)
    tokens = content.split()
    recipient_index = _recipient_token_index(tokens)
    if recipient_index is None:
        recipient_index = max(1, len(tokens) - 1)
    purpose = " ".join(tokens[:recipient_index]).strip()
    recipient = " ".join(tokens[recipient_index:]).strip()
    if not purpose or not recipient:
        return None
    return work_plan, purpose, recipient, agency


def _parse_current_grant(
    current: list[str], *, document: GrantDocument, page_number: int,
    source_pdf_sha256: str, source_pdf_url: str | None, row_number: int,
) -> dict[str, Any] | None:
    if not current:
        return None
    amount_line = current[-1]
    amount_match = _AMOUNT_PATTERN.search(amount_line) or _GENERIC_AMOUNT_PATTERN.search(amount_line)
    if amount_match is None:
        return None
    amount = amount_match.group("amount").replace(",", "")
    fields = list(current)
    fields[-1] = amount_line[: amount_match.start()].strip()
    if not fields[-1]:
        fields.pop()
    parsed = _split_grant_fields(fields)
    if parsed is None:
        return None
    work_plan, purpose, recipient, agency = parsed
    return {
        "grant_id": f"{document.year_roc}:{page_number}:{row_number}",
        "year_roc": document.year_roc,
        "work_plan": work_plan,
        "purpose": purpose,
        "recipient_name": recipient,
        "recipient_address": _extract_address(recipient),
        "project_location": None,
        "agency": agency,
        "amount_twd_thousand": amount,
        "purchase_involved": _purchase_flag(amount_line),
        "source_page_number": page_number,
        "source_document_url": document.detail_url,
        "source_pdf_url": source_pdf_url,
        "source_pdf_sha256": source_pdf_sha256,
        "source_row_text": " ".join(current),
    }


def _recipient_token_index(tokens: list[str]) -> int | None:
    markers = (
        "發展協會",
        "股份有限公司",
        "有限公司",
        "企業社",
        "協會",
        "基金會",
        "學會",
        "總會",
        "社區",
        "事務所",
        "工作室",
        "商行",
        "公司",
    )
    for index, value in enumerate(tokens):
        if any(marker in value for marker in markers):
            return index
    return None


def _join_wrapped_company_words(value: str) -> str:
    for left, right in (
        ("股", "份"),
        ("有", "限"),
        ("發", "展"),
        ("協", "會"),
        ("基", "金"),
        ("有限", "公司"),
        ("股份", "有限公司"),
        ("股份有限", "公司"),
        ("企業", "社"),
        ("事", "業"),
        ("好", "事"),
        ("工", "作室"),
        ("工作", "室"),
        ("發展", "協會"),
        ("總", "會"),
        ("商", "行"),
    ):
        value = re.sub(rf"{re.escape(left)}\s+{re.escape(right)}", left + right, value)
    return value


def _extract_address(value: str) -> str | None:
    match = re.search(r"(?:臺|台)灣[^\s]*?(?:區|鄉|鎮|市)[^\s]*", value)
    return match.group(0) if match else None


def _is_work_plan(line: str) -> bool:
    is_start = line == "青年發展業" or any(
        line.startswith(marker) for marker in _WORK_PLAN_MARKERS
    )
    if is_start:
        return True
    if _AMOUNT_PATTERN.search(line) or _GENERIC_AMOUNT_PATTERN.search(line):
        return False
    return False


def _is_header_line(line: str) -> bool:
    return any(
        token in line
        for token in (
            "單位：",
            "工作計畫",
            "科目名稱",
            "補助事項",
            "補助對象",
            "主辦機關",
            "累計撥付金額",
            "有無涉及",
            "是否為除外",
            "合計",
        )
    ) or line in {"是", "否"}


def _looks_like_amount_row(line: str) -> bool:
    return bool(_AMOUNT_PATTERN.search(line)) or ("無" in line or "有" in line) and bool(_GENERIC_AMOUNT_PATTERN.search(line))


def _purchase_flag(line: str) -> bool | None:
    if "無" in line:
        return False
    if "有" in line:
        return True
    return None


def _extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    if PdfReader is None:
        raise YouthGrantCollectorError("pypdf is required to parse grant PDFs")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise YouthGrantCollectorError(f"PDF text extraction failed: {exc}") from exc


def _validate_pdf(value: bytes) -> bytes:
    if not value.startswith(b"%PDF-"):
        raise YouthGrantCollectorError("downloaded grant document is not a PDF")
    if len(value) > MAX_PDF_BYTES:
        raise YouthGrantCollectorError("grant PDF exceeds size limit")
    return value


def _find_pdf_url(html: str, *, page_url: str) -> str | None:
    for match in _ANCHOR_PATTERN.finditer(html):
        href_match = _HREF_PATTERN.search(match.group("attributes"))
        if href_match is None:
            continue
        href = unescape(href_match.group("href")).strip()
        text = _visible_text(match.group("body"))
        absolute = urljoin(page_url, href)
        if ".pdf" in absolute.lower() or "pdf" in text.lower() or "附件" in text:
            return absolute
    match = re.search(r"https?://[^\s'\"]+\.pdf(?:\?[^\s'\"]*)?", html, re.IGNORECASE)
    return unescape(match.group(0)) if match else None


def _request_text(url: str, *, open_url: OpenURL) -> str:
    return _decode_html(_request_bytes(url, open_url=open_url, accept="text/html,application/xhtml+xml"))


def _request_bytes(url: str, *, open_url: OpenURL, accept: str) -> bytes:
    request = Request(url, headers={"Accept": accept, "User-Agent": "NewTaipeiHack-data-pipeline/1.0"})
    try:
        response = open_url(request, timeout=REQUEST_TIMEOUT_SECONDS)
        return response.read(MAX_PDF_BYTES + 1)
    except Exception as exc:
        raise YouthGrantCollectorError(f"request failed for {url}: {exc}") from exc


def _decode_html(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _normalized_lines(page: str) -> list[str]:
    lines = [
        re.sub(r"\s+", " ", unicodedata.normalize("NFKC", line)).strip()
        for line in page.splitlines()
        if line.strip()
    ]
    merged: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index] == "青年發展業" and index + 1 < len(lines) and lines[index + 1] == "務":
            merged.append("青年發展業務")
            index += 2
            continue
        merged.append(lines[index])
        index += 1
    return merged


def _visible_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _normalize_years(years: Sequence[str] | None) -> set[str] | None:
    if years is None:
        return None
    normalized: set[str] = set()
    for value in years:
        text = str(value).strip()
        if text.isdigit() and int(text) > 1911:
            text = str(int(text) - 1911)
        if not text.isdigit():
            raise YouthGrantCollectorError(f"invalid ROC year: {value!r}")
        normalized.add(str(int(text)))
    return normalized


__all__ = ["GRANT_LIST_URL", "YouthGrantCollectorError", "fetch_youth_grants"]
