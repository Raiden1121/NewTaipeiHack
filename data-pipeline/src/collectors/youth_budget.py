"""Collect New Taipei Youth Bureau annual budget tables from official PDFs."""

from __future__ import annotations

import hashlib
import io
import re
import ssl
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .contracts import CollectedPayload, SourceArtifact

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - dependency is declared in requirements.txt
    PdfReader = None  # type: ignore[assignment,misc]


BUDGET_LIST_URL = (
    "https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?module=youth0008&id=108"
)
SETTLEMENT_LIST_URL = (
    "https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?module=youth0008&id=109"
)
REQUEST_TIMEOUT_SECONDS = 120
MAX_PDF_BYTES = 50 * 1024 * 1024
TABLE_TITLE = "計畫及預算統計表"
UNIT_LABEL = "新臺幣千元"
SETTLEMENT_TABLE_TITLE = "歲出機關別決算表"
SETTLEMENT_UNIT_LABEL = "新臺幣元"
_TITLE_PATTERN = re.compile(
    r"新北市政府青年局主管(?P<year>\d{3})年度單位預算[（(](?P<status>[^）)]+)[）)]"
)
_SETTLEMENT_TITLE_PATTERN = re.compile(r"新北市政府青年局(?P<year>\d{3})年度單位決算")
_DATE_PATTERN = re.compile(r"\d{3,4}[./-]\d{1,2}[./-]\d{1,2}")
_ANCHOR_PATTERN = re.compile(
    r"<a\b(?P<attributes>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL
)
_HREF_PATTERN = re.compile(
    r"\bhref\s*=\s*(['\"])(?P<href>.*?)\1", re.IGNORECASE | re.DOTALL
)
_AMOUNT_RATIO_PATTERN = re.compile(
    r"(?P<amount>\d[\d,]*)\s+(?P<ratio>\d+(?:\.\d+)?)\s*$"
)
_SETTLEMENT_SOURCE_ROW_PATTERN = re.compile(
    r"(?P<original>-?\d[\d,]*|-)\s+"
    r"(?P<adjustment>-?\d[\d,]*|-)\s+"
    r"(?P<budget>-?\d[\d,]*|-)\s*$"
)
_SETTLEMENT_RESULT_ROW_PATTERN = re.compile(
    r"^(?P<realized>-?\d[\d,]*|-)\s+"
    r"(?P<payable>-?\d[\d,]*|-)\s+"
    r"(?P<reserved>-?\d[\d,]*|-)\s+"
    r"(?P<settlement>-?\d[\d,]*|-)\s+"
    r"(?P<difference>-?\d[\d,]*|-)\s+"
    r"(?P<ratio>-|\d+(?:\.\d+)?)(?:%)?"
)
_SETTLEMENT_PLAN_NAMES = frozenset(
    {
        "合計",
        "新北市政府青年局主管",
        "新北市政府青年局",
        "經常門合計",
        "資本門合計",
        "一般行政",
        "青年發展業務",
        "第一預備金",
        "統籌支撥科目",
        "公務人員退休及撫卹給付",
        "公務人員各項補助及慰問金",
    }
)
_CONCATENATED_PLANS = (
    "一般行政",
    "青年發展業務",
    "第一預備金",
)

OpenURL = Callable[..., Any]


class BudgetCollectorError(RuntimeError):
    """Raised when an official budget document cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class BudgetDocument:
    budget_year_roc: str
    document_status: str
    document_status_label: str
    title: str
    detail_url: str
    pdf_url: str | None
    published_date: str | None
    updated_date: str | None
    document_kind: str = "budget"


def _create_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
    if strict_flag is not None:
        context.verify_flags &= ~strict_flag
    return context


def _open_url(request: Request, *, timeout: int) -> Any:
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def fetch_youth_budgets(
    *,
    list_url: str = BUDGET_LIST_URL,
    open_url: OpenURL = _open_url,
    years: Sequence[str] | None = None,
    settlement_list_url: str | None = None,
) -> CollectedPayload:
    """Discover and parse selected budget and final-settlement documents.

    A custom ``list_url`` keeps the historical budget-only test/replay behavior.
    The live default source additionally discovers the official settlement list.
    """

    selected_years = _normalize_years(years)
    if settlement_list_url is None and list_url == BUDGET_LIST_URL:
        settlement_list_url = SETTLEMENT_LIST_URL

    listing_sources = [(list_url, "budget")]
    if settlement_list_url:
        listing_sources.append((settlement_list_url, "settlement"))
    documents: list[BudgetDocument] = []
    listing_failures: list[dict[str, str]] = []
    for source_url, document_kind in listing_sources:
        try:
            listing_html = _request_text(source_url, open_url=open_url)
            documents.extend(
                _parse_listing_page(
                    listing_html,
                    page_url=source_url,
                    document_kind=document_kind,
                )
            )
        except BudgetCollectorError as exc:
            listing_failures.append({"url": source_url, "reason": str(exc)})
    if selected_years is not None:
        documents = [
            document
            for document in documents
            if document.budget_year_roc in selected_years
        ]
    if not documents:
        suffix = f" for years {sorted(selected_years)}" if selected_years else ""
        failure_text = "; ".join(
            f"{failure['url']}: {failure['reason']}" for failure in listing_failures
        )
        raise BudgetCollectorError(
            f"budget listing has no matching documents{suffix}"
            f"{': ' + failure_text if failure_text else ''}"
        )

    records: list[dict[str, Any]] = []
    document_metadata: list[dict[str, Any]] = []
    artifacts: list[SourceArtifact] = []
    failures: list[dict[str, str]] = []
    seen_documents: set[tuple[str, str, str]] = set()

    for document in documents:
        try:
            detail_bytes = _request_bytes(
                document.detail_url,
                open_url=open_url,
                accept="text/html,application/xhtml+xml,application/pdf",
                limit=MAX_PDF_BYTES + 1,
            )
            if detail_bytes.startswith(b"%PDF-"):
                document = replace(document, pdf_url=document.detail_url)
                pdf_bytes = _validate_pdf_bytes(detail_bytes)
            else:
                detail_html = _decode_html(detail_bytes)
                document = _parse_detail_page(detail_html, document=document)
                if not document.pdf_url:
                    raise BudgetCollectorError("detail page does not expose a PDF link")
                pdf_bytes = _request_pdf(document.pdf_url, open_url=open_url)
            artifact = _build_source_artifact(document, pdf_bytes)
            document_key = (
                document.budget_year_roc,
                document.document_status,
                artifact.sha256,
            )
            if document_key in seen_documents:
                continue
            artifacts.append(artifact)
            pages = _extract_pdf_pages(pdf_bytes)
            if document.document_kind == "settlement":
                rows, page_number = _extract_settlement_table(pages, document=document)
            else:
                rows, page_number = _find_budget_table(pages, document=document)
            document_id = (
                f"youth_budgets:{document.budget_year_roc}:"
                f"{document.document_status}:{artifact.sha256.removeprefix('sha256:')}"
            )
            for row in rows:
                row.update(
                    {
                        "document_id": document_id,
                        "source_pdf_sha256": artifact.sha256,
                        "source_pdf_url": document.pdf_url,
                    }
                )
            records.extend(rows)
            seen_documents.add(document_key)
            document_metadata.append(
                {
                    "document_id": document_id,
                    "budget_year_roc": document.budget_year_roc,
                    "document_status": document.document_status,
                    "document_status_label": document.document_status_label,
                    "title": document.title,
                    "detail_url": document.detail_url,
                    "pdf_url": document.pdf_url,
                    "published_date": document.published_date,
                    "updated_date": document.updated_date,
                    "source_pdf_sha256": artifact.sha256,
                    "artifact_filename": artifact.filename,
                    "source_page_number": page_number,
                    "row_count": len(rows),
                    "document_kind": document.document_kind,
                }
            )
        except BudgetCollectorError as exc:
            failures.append(
                {
                    "title": document.title,
                    "detail_url": document.detail_url,
                    "reason": str(exc),
                }
            )

    if not records:
        detail = "; ".join(f"{failure['title']}: {failure['reason']}" for failure in failures)
        raise BudgetCollectorError(f"no valid youth budget document could be parsed{': ' + detail if detail else ''}")

    return CollectedPayload(
        records=records,
        metadata={
            "list_url": list_url,
            "settlement_list_url": settlement_list_url,
            "listing_failures": listing_failures,
            "documents": document_metadata,
            "document_failures": failures,
        },
        artifacts=tuple(artifacts),
    )


def _parse_listing_page(
    html: str, *, page_url: str, document_kind: str = "budget"
) -> list[BudgetDocument]:
    if not isinstance(html, str):
        raise BudgetCollectorError("budget listing must be text")
    documents: list[BudgetDocument] = []
    seen: set[tuple[str, str, str]] = set()
    previous_anchor_end = 0
    for match in _ANCHOR_PATTERN.finditer(html):
        href_match = _HREF_PATTERN.search(match.group("attributes"))
        if href_match is None:
            continue
        title = _visible_text(match.group("body"))
        normalized_title = _compact_text(title)
        title_pattern = (
            _SETTLEMENT_TITLE_PATTERN
            if document_kind == "settlement"
            else _TITLE_PATTERN
        )
        title_match = title_pattern.search(normalized_title)
        if title_match is None:
            previous_anchor_end = match.end()
            continue
        year = title_match.group("year")
        if document_kind == "settlement":
            status, status_label = "final_settlement", "單位決算"
        else:
            status, status_label = _parse_document_status(title_match.group("status"))
        detail_url = urljoin(page_url, unescape(href_match.group("href")).strip())
        key = (year, status, detail_url)
        if key in seen:
            previous_anchor_end = match.end()
            continue
        context = _visible_text(html[previous_anchor_end : match.start()])
        dates = _DATE_PATTERN.findall(f"{context} {title}")
        documents.append(
            BudgetDocument(
                budget_year_roc=year,
                document_status=status,
                document_status_label=status_label,
                title=title_match.group(0),
                detail_url=detail_url,
                pdf_url=None,
                published_date=dates[0] if dates else None,
                updated_date=dates[1] if len(dates) > 1 else None,
                document_kind=document_kind,
            )
        )
        seen.add(key)
        previous_anchor_end = match.end()
    return documents


def _parse_detail_page(html: str, *, document: BudgetDocument) -> BudgetDocument:
    for match in _ANCHOR_PATTERN.finditer(html):
        href_match = _HREF_PATTERN.search(match.group("attributes"))
        if href_match is None:
            continue
        href = unescape(href_match.group("href")).strip()
        text = _visible_text(match.group("body"))
        absolute_url = urljoin(document.detail_url, href)
        if ".pdf" in absolute_url.lower() or "pdf" in text.lower():
            return replace(document, pdf_url=absolute_url)
    pdf_match = re.search(r"https?://[^\s'\"]+\.pdf(?:\?[^\s'\"]*)?", html, re.IGNORECASE)
    if pdf_match:
        return replace(document, pdf_url=unescape(pdf_match.group(0)))
    return document


def _parse_document_status(label: str) -> tuple[str, str]:
    normalized = _compact_text(label)
    if normalized == "預算案":
        return "proposed_budget", "預算案"
    if normalized in {"法定版", "法定預算"}:
        return "legal_budget", normalized
    raise BudgetCollectorError(f"unsupported budget document status: {label!r}")


def _extract_budget_table(
    page_text: str, *, document: BudgetDocument, page_number: int
) -> list[dict[str, Any]]:
    if not isinstance(page_text, str):
        raise BudgetCollectorError("budget PDF page text must be text")
    normalized_page = _compact_text(page_text)
    if TABLE_TITLE not in normalized_page or UNIT_LABEL not in normalized_page or "%" not in normalized_page:
        raise BudgetCollectorError("target budget table title or unit is missing")
    lines = [re.sub(r"\s+", " ", unicodedata.normalize("NFKC", line)).strip() for line in page_text.splitlines()]
    lines = [line for line in lines if line]
    header_index = _find_header_index(lines)
    if header_index is None:
        raise BudgetCollectorError("target budget table header is missing")

    rows: list[dict[str, Any]] = []
    for line in lines[header_index + 1 :]:
        parsed = _parse_budget_row(line)
        if parsed is None:
            continue
        row_type, business_plan, work_plan, amount, ratio = parsed
        rows.append(
            {
                "budget_year_roc": document.budget_year_roc,
                "document_status": document.document_status,
                "document_status_label": document.document_status_label,
                "row_type": row_type,
                "business_plan": business_plan,
                "work_plan": work_plan,
                "budget_amount": amount,
                "ratio_percent": ratio,
                "unit_label": UNIT_LABEL,
                "table_title": TABLE_TITLE,
                "source_page_number": page_number,
                "source_document_url": document.detail_url,
                "source_row_text": line,
            }
        )
    total_count = sum(row["row_type"] == "total" for row in rows)
    if total_count != 1:
        raise BudgetCollectorError("target budget table must contain exactly one total row")
    if not rows:
        raise BudgetCollectorError("target budget table contains no rows")
    return rows


def _find_header_index(lines: Sequence[str]) -> int | None:
    candidates: list[int] = []
    for index, _line in enumerate(lines):
        window = _compact_text(" ".join(lines[index : index + 4]))
        if all(token in window for token in ("業務計畫", "工作計畫", "本年度預算數", "比率")):
            candidates.append(index)
    return candidates[-1] if candidates else None


def _parse_budget_row(line: str) -> tuple[str, str, str | None, str, str] | None:
    match = _AMOUNT_RATIO_PATTERN.search(line)
    if match is None:
        if _looks_like_budget_row(line):
            raise BudgetCollectorError(f"budget row has invalid numeric cells: {line}")
        return None
    prefix = line[: match.start()].strip()
    if not prefix:
        return None
    if "合計" in prefix:
        return "total", _compact_text(prefix), None, match.group("amount"), match.group("ratio")
    parts = [_compact_text(part) for part in prefix.split()]
    if len(parts) < 2:
        for plan in _CONCATENATED_PLANS:
            if prefix == plan + plan:
                return "detail", plan, plan, match.group("amount"), match.group("ratio")
        raise BudgetCollectorError(f"budget detail row is missing business/work plan: {line}")
    return (
        "detail",
        parts[0],
        " ".join(parts[1:]),
        match.group("amount"),
        match.group("ratio"),
    )


def _looks_like_budget_row(line: str) -> bool:
    return any(token in line for token in ("合計", *_CONCATENATED_PLANS))


def _find_budget_table(
    pages: Sequence[str], *, document: BudgetDocument
) -> tuple[list[dict[str, Any]], int]:
    saw_target = False
    errors: list[str] = []
    for index, page_text in enumerate(pages, start=1):
        normalized = _compact_text(page_text)
        if TABLE_TITLE not in normalized:
            continue
        saw_target = True
        try:
            return (
                _extract_budget_table(page_text, document=document, page_number=index),
                index,
            )
        except BudgetCollectorError as exc:
            errors.append(f"page {index}: {exc}")
    if saw_target and errors:
        raise BudgetCollectorError("; ".join(errors))
    raise BudgetCollectorError("target budget table was not found in PDF")


def _extract_settlement_table(
    pages: Sequence[str], *, document: BudgetDocument
) -> tuple[list[dict[str, Any]], int]:
    """Extract the paired source/result pages of the official settlement table."""

    pairs: list[tuple[int, list[dict[str, str]], list[dict[str, str]]]] = []
    for index, page_text in enumerate(pages):
        normalized = _compact_text(page_text)
        if "原預算數" not in normalized or "歲出機關" not in normalized:
            continue
        if index + 1 >= len(pages):
            continue
        source_rows = _parse_settlement_source_rows(page_text)
        result_rows = _parse_settlement_result_rows(pages[index + 1])
        if source_rows and result_rows:
            pairs.append((index + 1, source_rows, result_rows))

    if not pairs:
        raise BudgetCollectorError("target settlement table was not found in PDF")

    selected_rows: list[dict[str, Any]] = []
    seen_plan_names: set[str] = set()
    for page_number, source_rows, result_rows in pairs:
        if len(source_rows) != len(result_rows):
            raise BudgetCollectorError(
                "settlement source/result row counts do not match "
                f"on page {page_number}: {len(source_rows)} != {len(result_rows)}"
            )
        for source_row, result_row in zip(source_rows, result_rows, strict=True):
            plan_name = _compact_text(source_row["plan_name"])
            if plan_name not in _SETTLEMENT_PLAN_NAMES or plan_name in seen_plan_names:
                continue
            seen_plan_names.add(plan_name)
            selected_rows.append(
                {
                    "budget_year_roc": document.budget_year_roc,
                    "document_status": document.document_status,
                    "document_status_label": document.document_status_label,
                    "row_type": "total" if plan_name == "合計" else "detail",
                    "business_plan": plan_name,
                    "work_plan": None,
                    "budget_amount": source_row["budget"],
                    "original_budget_amount": source_row["original"],
                    "budget_adjustment_amount": source_row["adjustment"],
                    "realized_amount": result_row["realized"],
                    "payable_amount": result_row["payable"],
                    "reserved_amount": result_row["reserved"],
                    "settlement_amount": result_row["settlement"],
                    "surplus_amount": result_row["difference"],
                    "source_execution_ratio_percent": result_row["ratio"],
                    "unit_label": SETTLEMENT_UNIT_LABEL,
                    "table_title": SETTLEMENT_TABLE_TITLE,
                    "source_page_number": page_number,
                    "source_document_url": document.detail_url,
                    "source_row_text": source_row["source_row_text"],
                    "source_result_row_text": result_row["source_row_text"],
                }
            )
    if not selected_rows or selected_rows[0]["row_type"] != "total":
        raise BudgetCollectorError("settlement table has no total row")
    return selected_rows, selected_rows[0]["source_page_number"]


def _parse_settlement_source_rows(page_text: str) -> list[dict[str, str]]:
    lines = _normalized_lines(page_text)
    rows: list[dict[str, str]] = []
    pending_plan: str | None = None
    for line in lines:
        match = _SETTLEMENT_SOURCE_ROW_PATTERN.search(line)
        if match is not None:
            prefix = line[: match.start()].strip()
            plan_name = prefix or pending_plan
            pending_plan = None
            if not plan_name:
                continue
            rows.append(
                {
                    "plan_name": plan_name,
                    "original": match.group("original"),
                    "adjustment": match.group("adjustment"),
                    "budget": match.group("budget"),
                    "source_row_text": line,
                }
            )
            continue
        normalized = _compact_text(line)
        if (
            _is_settlement_code_line(line)
            or normalized in {"中華民國", "增減數", "合計(1)", "預算增減數"}
            or "原預算數" in normalized
            or "名稱及編號" in normalized
            or normalized.isdigit()
        ):
            continue
        pending_plan = line.strip()
    return rows


def _parse_settlement_result_rows(page_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in _normalized_lines(page_text):
        match = _SETTLEMENT_RESULT_ROW_PATTERN.match(line)
        if match is None:
            continue
        rows.append(
            {
                "realized": match.group("realized"),
                "payable": match.group("payable"),
                "reserved": match.group("reserved"),
                "settlement": match.group("settlement"),
                "difference": match.group("difference"),
                "ratio": match.group("ratio"),
                "source_row_text": line,
            }
        )
    return rows


def _normalized_lines(page_text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", unicodedata.normalize("NFKC", line)).strip()
        for line in page_text.splitlines()
        if line.strip()
    ]


def _is_settlement_code_line(line: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}\s+\d[\da-zA-Z]+", line.strip()))


def _extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    if PdfReader is None:
        raise BudgetCollectorError("pypdf is required to parse budget PDFs")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise BudgetCollectorError(f"PDF text extraction failed: {exc}") from exc


def _build_source_artifact(document: BudgetDocument, pdf_bytes: bytes) -> SourceArtifact:
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
        raise BudgetCollectorError("downloaded budget document is not a PDF")
    digest = "sha256:" + hashlib.sha256(pdf_bytes).hexdigest()
    filename = f"{document.budget_year_roc}_{document.document_status}_{digest[7:19]}.pdf"
    return SourceArtifact(
        filename=filename,
        content=pdf_bytes,
        media_type="application/pdf",
        sha256=digest,
    )


def _request_text(url: str, *, open_url: OpenURL) -> str:
    raw = _request_bytes(
        url,
        open_url=open_url,
        accept="text/html,application/xhtml+xml",
    )
    return _decode_html(raw)


def _request_bytes(
    url: str,
    *,
    open_url: OpenURL,
    accept: str,
    limit: int | None = None,
) -> bytes:
    request = Request(url, headers={"Accept": accept})
    try:
        return _read_response(
            open_url(request, timeout=REQUEST_TIMEOUT_SECONDS),
            limit=limit,
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise BudgetCollectorError(f"budget source request failed: {exc}") from exc


def _decode_html(raw: bytes) -> str:
    for encoding in ("utf-8", "cp950", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise BudgetCollectorError("budget source returned unsupported HTML encoding")


def _request_pdf(url: str, *, open_url: OpenURL) -> bytes:
    raw = _request_bytes(
        url,
        open_url=open_url,
        accept="application/pdf",
        limit=MAX_PDF_BYTES + 1,
    )
    return _validate_pdf_bytes(raw)


def _validate_pdf_bytes(raw: bytes) -> bytes:
    if not raw:
        raise BudgetCollectorError("downloaded budget PDF is empty")
    if len(raw) > MAX_PDF_BYTES:
        raise BudgetCollectorError("downloaded budget PDF exceeds size limit")
    if not raw.startswith(b"%PDF-"):
        raise BudgetCollectorError("downloaded budget document is not a PDF")
    return raw


def _read_response(response: Any, *, limit: int | None = None) -> bytes:
    try:
        if hasattr(response, "__enter__"):
            with response as active:
                return active.read() if limit is None else active.read(limit)
        return response.read() if limit is None else response.read(limit)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _normalize_years(years: Sequence[str] | None) -> set[str] | None:
    if years is None:
        return None
    normalized = {str(year).strip() for year in years}
    if not normalized or any(not re.fullmatch(r"\d{3}", year) for year in normalized):
        raise BudgetCollectorError("years must contain three-digit ROC years")
    return normalized


def _visible_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))
