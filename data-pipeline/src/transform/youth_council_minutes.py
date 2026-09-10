"""Parse meeting-record text into organization-level proposal items."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from analytics.config import YouthTopicRules

from .common import TransformValueError, build_common_metadata, clean_text
from .contracts import TransformResult
from .quality import QualityCollector


_ITEM_PATTERN = re.compile(r"^\s*(?P<number>[一二三四五六七八九十百\d]+)[、.．]\s*(?P<title>.+?)\s*$")
_DATE_PATTERN = re.compile(r"(?P<year>\d{2,3})\s*[年./-]\s*(?P<month>\d{1,2})\s*[月./-]\s*(?P<day>\d{1,2})\s*日?")
_COMPACT_DATE_PATTERN = re.compile(r"(?P<year>\d{3})(?P<month>\d{2})(?P<day>\d{2})")


def transform_youth_council_minutes(
    records: Iterable[Mapping[str, Any]],
    *,
    fetched_at: str | None = None,
    rules: YouthTopicRules,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        try:
            meeting_id = _required(raw, "meeting_id")
            meeting_name = _required(raw, "meeting_name")
            meeting_date = _required(raw, "meeting_date")
            year_roc, gregorian_year = _record_year(raw)
            page_texts = raw.get("page_texts")
            if not isinstance(page_texts, list) or not all(isinstance(page, str) for page in page_texts):
                raise TransformValueError("page_texts is required")
        except TransformValueError as exc:
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue

        items = _parse_items(page_texts, rules)
        if not items:
            quality.reject(index, raw, "no_meeting_items")
            continue
        for item_index, item in enumerate(items, start=1):
            source_id = f"{meeting_id}:item:{item_index}"
            curated = build_common_metadata(
                dataset="youth_council_minutes",
                source="ntpc_youth_bureau_meeting_minutes",
                source_record_id=source_id,
                geo_level="organization",
                district_id=None,
                district_name=None,
                period_start=f"{gregorian_year}-01-01",
                period_end=f"{gregorian_year}-12-31",
                period_type="year",
                metric_id=None,
                value=None,
                unit=None,
                age_scope="not_age_specific",
                age_min=None,
                age_max=None,
                youth_eligibility="context_only",
                fetched_at=fetched_at,
            )
            curated.update(
                {
                    "organization_name": "新北市青年局",
                    "meeting_id": meeting_id,
                    "meeting_name": meeting_name,
                    "meeting_date": meeting_date,
                    "term": clean_text(raw.get("term")),
                    "year_roc": year_roc,
                    "item_no": item["item_no"],
                    "section_type": "resolved" if item["resolved"] else "discussed",
                    "source_page_start": item["page_start"],
                    "source_page_end": item["page_end"],
                    "source_text": item["source_text"],
                    "discussed": True,
                    "resolved": item["resolved"],
                    "escalated": item["escalated"],
                    "parse_status": "complete" if item["resolved"] else "partial",
                    "manual_review_required": not item["resolved"],
                    "topic_text": item["topic_text"],
                    "discussion_text": item["discussion_text"],
                    "resolution_text": item["resolution_text"],
                    "source_pdf_sha256": clean_text(raw.get("source_pdf_sha256")),
                    "raw_record": deepcopy(raw),
                }
            )
            output.append(curated)
            quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _parse_items(page_texts: list[str], rules: YouthTopicRules) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_section: str | None = None
    def finalize() -> None:
        nonlocal current
        if current is None:
            return
        discussion = "\n".join(current["discussion_lines"]).strip()
        resolution = "\n".join(current["resolution_lines"]).strip()
        source_text = "\n".join(part for part in (discussion, resolution) if part).strip()
        current["topic_text"] = current["discussion_lines"][0].strip()
        current["discussion_text"] = discussion
        current["resolution_text"] = resolution
        current["source_text"] = source_text
        current["resolved"] = bool(current.get("resolved_header_seen"))
        current["escalated"] = any(phrase in resolution for phrase in rules.escalated_phrases)
        current["page_end"] = current.get("last_page", current["page_start"])
        items.append(current)
        current = None

    for page_index, page in enumerate(page_texts, start=1):
        for raw_line in page.splitlines():
            line = _normalize_line(raw_line)
            if not line:
                continue
            header = _section_kind(line, rules)
            if header == "discussed":
                current_section = "discussed"
                continue
            if header == "resolved":
                current_section = "resolved"
                if current is not None:
                    current["resolved_header_seen"] = True
                    current["last_page"] = page_index
                continue
            item_match = _ITEM_PATTERN.match(line)
            if current_section == "discussed" and item_match:
                finalize()
                current = {
                    "item_no": item_match.group("number"),
                    "discussion_lines": [item_match.group("title")],
                    "resolution_lines": [],
                    "resolved_header_seen": False,
                    "page_start": page_index,
                    "last_page": page_index,
                }
                continue
            if current is None:
                continue
            current["last_page"] = page_index
            if current_section == "resolved":
                current["resolution_lines"].append(line)
            else:
                current["discussion_lines"].append(line)
    finalize()
    return items


def _section_kind(line: str, rules: YouthTopicRules) -> str | None:
    for header in rules.section_headers.get("resolved", ()):
        if header in line:
            return "resolved"
    for header in rules.section_headers.get("discussed", ()):
        if header in line:
            return "discussed"
    return None


def _record_year(raw: Mapping[str, Any]) -> tuple[str, int]:
    raw_year = clean_text(raw.get("year_roc"))
    if raw_year and raw_year.isdigit():
        number = int(raw_year)
        return (str(number - 1911), number) if number > 1911 else (raw_year, number + 1911)
    value = clean_text(raw.get("meeting_date"))
    if not value:
        raise TransformValueError("meeting_date/year_roc is required")
    match = _COMPACT_DATE_PATTERN.search(value) or _DATE_PATTERN.search(value)
    if match is None:
        raise TransformValueError("meeting_date is not a supported date")
    number = int(match.group("year"))
    return (str(number - 1911), number) if number > 1911 else (str(number), number + 1911)


def _required(raw: Mapping[str, Any], field: str) -> str:
    value = clean_text(raw.get(field))
    if value is None:
        raise TransformValueError(f"{field} is required")
    return value


def _normalize_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
