"""Collect New Taipei candidate rosters from the CEC election ZIP archive."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import ssl
from collections.abc import Callable, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from .contracts import CollectedPayload, SourceArtifact


CEC_VOTEDATA_URL = "https://data.cec.gov.tw/選舉資料庫/votedata.zip"
NEW_TAIPEI_CITY_CODE = "65"
REQUEST_TIMEOUT_SECONDS = 180
MAX_ZIP_BYTES = 512 * 1024 * 1024
OpenURL = Callable[..., Any]

_ELECTION_CONFIG: dict[str, dict[str, Any]] = {
    "2014": {
        "roc_year": "103",
        "election_date": "2014-11-29",
        "city_councilor_path": "直轄市區域議員",
        "borough_chief_path": "村里長",
    },
    "2018": {
        "roc_year": "107",
        "election_date": "2018-11-24",
        "city_councilor_path": "直轄市區域議員",
        "borough_chief_path": "直轄市村里長",
    },
    "2022": {
        "roc_year": "111",
        "election_date": "2022-11-26",
        "city_councilor_path": "/T1/prv/",
        "borough_chief_path": "/V1/",
    },
}

_FIELD_NAMES = (
    "city_code",
    "county_code",
    "election_district_code",
    "township_code",
    "village_code",
    "candidate_number",
    "candidate_name",
    "party_code",
    "sex_code",
    "birth_date_roc",
    "source_age",
    "birthplace",
    "education",
    "current_mark",
    "elected_mark",
    "deputy_name",
)


class ElectionCollectorError(RuntimeError):
    """Raised when the CEC archive cannot be safely parsed."""


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
            _encoded_url(url_or_request),
            headers={
                "Accept": "application/zip,application/octet-stream,*/*",
                "User-Agent": "NewTaipeiHack-data-pipeline/1.0",
            },
        )
    else:
        encoded_url = _encoded_url(url_or_request.full_url)
        if encoded_url != url_or_request.full_url:
            request = Request(
                encoded_url,
                headers=dict(url_or_request.header_items()),
                method=url_or_request.get_method(),
            )
    return urlopen(request, timeout=timeout, context=_create_ssl_context())


def _encoded_url(url: str) -> str:
    """Encode the Chinese path in the official CEC URL for HTTP transport."""

    return quote(url, safe=":/?=&%")


def fetch_elections(
    *,
    source_url: str = CEC_VOTEDATA_URL,
    election_terms: Sequence[str] = ("2014", "2018", "2022"),
    city_code: str = NEW_TAIPEI_CITY_CODE,
    open_url: OpenURL = _open_url,
) -> CollectedPayload:
    """Fetch T1 and V1 records for the selected New Taipei election terms."""

    terms = _normalize_terms(election_terms)
    normalized_city_code = _clean_code(city_code)
    if not normalized_city_code:
        raise ElectionCollectorError("city_code is required")

    archive_bytes = _request_bytes(source_url, open_url=open_url)
    digest = "sha256:" + hashlib.sha256(archive_bytes).hexdigest()
    artifact = SourceArtifact(
        filename=f"cec_votedata_{digest[7:19]}.zip",
        content=archive_bytes,
        media_type="application/zip",
        sha256=digest,
    )
    try:
        archive = ZipFile(io.BytesIO(archive_bytes))
    except BadZipFile as exc:
        raise ElectionCollectorError("CEC source is not a valid ZIP archive") from exc

    records: list[dict[str, Any]] = []
    file_metadata: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with archive:
        names = tuple(info.filename for info in archive.infolist())
        for term in terms:
            config = _ELECTION_CONFIG[term]
            term_prefix = _term_prefix(names, term, config["roc_year"])
            if term_prefix is None:
                failures.append({"term": term, "reason": "election term directory not found"})
                continue
            for election_type, path_fragment, office_name in (
                (
                    "city_councilor",
                    config["city_councilor_path"],
                    "直轄市區域議員",
                ),
                ("borough_chief", config["borough_chief_path"], "村里長"),
            ):
                candidate_path = _find_member_path(
                    names,
                    term_prefix=term_prefix,
                    path_fragment=path_fragment,
                    member="elcand.csv",
                )
                base_path = _find_member_path(
                    names,
                    term_prefix=term_prefix,
                    path_fragment=path_fragment,
                    member="elbase.csv",
                )
                if candidate_path is None or base_path is None:
                    failures.append(
                        {
                            "term": term,
                            "election_type": election_type,
                            "reason": "candidate or area file not found",
                        }
                    )
                    continue
                try:
                    base_names = _read_area_names(archive.read(base_path))
                    parsed_rows = _parse_candidate_rows(
                        archive.read(candidate_path),
                        term=term,
                        election_date=config["election_date"],
                        election_type=election_type,
                        office_name=office_name,
                        source_code="T1" if election_type == "city_councilor" else "V1",
                        source_path=candidate_path,
                        base_names=base_names,
                        city_code=normalized_city_code,
                        source_zip_sha256=digest,
                    )
                except ElectionCollectorError as exc:
                    failures.append(
                        {
                            "term": term,
                            "election_type": election_type,
                            "reason": str(exc),
                        }
                    )
                    continue
                records.extend(parsed_rows)
                file_metadata.append(
                    {
                        "election_term": term,
                        "election_type": election_type,
                        "source_code": "T1" if election_type == "city_councilor" else "V1",
                        "candidate_path": candidate_path,
                        "base_path": base_path,
                        "row_count": len(parsed_rows),
                    }
                )

    if not records:
        failure_text = "; ".join(
            f"{item.get('term', '')}/{item.get('election_type', '')}: {item['reason']}"
            for item in failures
        )
        raise ElectionCollectorError(
            f"CEC archive produced no New Taipei T1/V1 records"
            f"{': ' + failure_text if failure_text else ''}"
        )

    counts: dict[str, int] = {}
    for row in records:
        key = f"{row['election_term']}:{row['source_code']}"
        counts[key] = counts.get(key, 0) + 1
    return CollectedPayload(
        records=records,
        metadata={
            "source_url": source_url,
            "city_code": normalized_city_code,
            "selected_terms": list(terms),
            "source_zip_sha256": digest,
            "files": file_metadata,
            "record_counts": counts,
            "failures": failures,
        },
        artifacts=(artifact,),
    )


def _normalize_terms(terms: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in terms:
        text = str(value).strip()
        if len(text) == 3 and text.isdigit():
            text = str(int(text) + 1911)
        if text not in _ELECTION_CONFIG:
            raise ElectionCollectorError(
                f"unsupported election term {value!r}; supported terms: "
                f"{', '.join(sorted(_ELECTION_CONFIG))}"
            )
        if text not in normalized:
            normalized.append(text)
    if not normalized:
        raise ElectionCollectorError("election_terms must not be empty")
    return tuple(normalized)


def _term_prefix(names: Sequence[str], term: str, roc_year: str) -> str | None:
    marker = f"{term}-{roc_year}年地方公職人員選舉/"
    for name in names:
        prefix_index = name.find(marker)
        if prefix_index >= 0:
            return name[: prefix_index + len(marker)]
    return None


def _find_member_path(
    names: Sequence[str], *, term_prefix: str, path_fragment: str, member: str
) -> str | None:
    candidates = [
        name
        for name in names
        if name.startswith(term_prefix)
        and name.endswith(f"/{member}")
        and (path_fragment in name or name.endswith(f"{path_fragment}{member}"))
    ]
    if not candidates:
        return None
    return sorted(candidates, key=len)[0]


def _read_area_names(content: bytes) -> dict[tuple[str, ...], str]:
    rows = _read_csv(content, field_count=6)
    result: dict[tuple[str, ...], str] = {}
    for row in rows:
        key = tuple(_clean_code(value) for value in row[:5])
        name = _clean_text(row[5])
        if name:
            result[key] = name
    return result


def _parse_candidate_rows(
    content: bytes,
    *,
    term: str,
    election_date: str,
    election_type: str,
    office_name: str,
    source_code: str,
    source_path: str,
    base_names: dict[tuple[str, ...], str],
    city_code: str,
    source_zip_sha256: str,
) -> list[dict[str, Any]]:
    rows = _read_csv(content, field_count=len(_FIELD_NAMES))
    parsed: list[dict[str, Any]] = []
    for row in rows:
        values = [_clean_text(value) for value in row]
        fields = dict(zip(_FIELD_NAMES, values, strict=True))
        if _clean_code(fields["city_code"]) != city_code:
            continue
        key = tuple(_clean_code(fields[name]) for name in _FIELD_NAMES[:5])
        election_district_name = base_names.get(
            (key[0], key[1], key[2], "000", "0000")
        )
        if election_type == "borough_chief":
            district_name = base_names.get((key[0], key[1], "00", key[3], "0000"))
            village_name = base_names.get(key)
        else:
            district_name = None
            village_name = None
        candidate_id = (
            f"elections:{term}:{source_code}:{key[0]}:{key[2]}:{key[3]}:"
            f"{key[4]}:{fields['candidate_number']}:{fields['candidate_name']}"
        )
        parsed.append(
            {
                "source_record_id": candidate_id,
                "election_term": term,
                "election_roc_year": _ELECTION_CONFIG[term]["roc_year"],
                "election_date": election_date,
                "election_type": election_type,
                "election_type_label": office_name,
                "source_code": source_code,
                "office_name": office_name,
                "candidate_number": fields["candidate_number"],
                "candidate_name": fields["candidate_name"],
                "party_code": _clean_code(fields["party_code"]),
                "sex_code": _clean_code(fields["sex_code"]),
                "birth_date_roc": _clean_code(fields["birth_date_roc"]),
                "birth_year_roc": _birth_year(fields["birth_date_roc"]),
                "source_age": fields["source_age"],
                "birthplace": fields["birthplace"],
                "education": fields["education"],
                "current_mark": fields["current_mark"],
                "elected_mark": fields["elected_mark"],
                "deputy_name": fields["deputy_name"],
                "city_code": key[0],
                "county_code": key[1],
                "election_district_code": key[2],
                "election_district_name": election_district_name,
                "township_code": key[3],
                "village_code": key[4],
                "village_name": village_name,
                "district_name": district_name,
                "geography_type": (
                    "administrative_district" if election_type == "borough_chief" else "election_district"
                ),
                "source_zip_sha256": source_zip_sha256,
                "source_zip_member": source_path,
                "raw_fields": dict(fields),
            }
        )
    return parsed


def _read_csv(content: bytes, *, field_count: int) -> list[list[str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ElectionCollectorError("CEC CSV is not UTF-8 encoded") from exc
    rows: list[list[str]] = []
    for line_number, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != field_count:
            raise ElectionCollectorError(
                f"CEC CSV row {line_number} has {len(row)} fields; expected {field_count}"
            )
        rows.append(row)
    return rows


def _birth_year(value: str | None) -> str | None:
    text = _clean_code(value)
    if text and re.fullmatch(r"\d{3}(?:\d{4})?", text):
        return text[:3]
    return None


def _clean_code(value: Any) -> str:
    return _clean_text(value).lstrip("'") if _clean_text(value) else ""


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _request_bytes(url: str, *, open_url: OpenURL) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/zip,application/octet-stream,*/*",
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
        raise ElectionCollectorError(f"CEC source request failed: {exc}") from exc
    if len(content) > MAX_ZIP_BYTES:
        raise ElectionCollectorError("CEC ZIP exceeds size limit")
    return content
