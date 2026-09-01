"""Collect DGBAS Table 6 annual wage data.

The official source is an annual XLSX/ODS download page rather than a JSON
API.  This collector discovers the current spreadsheet link at runtime,
extracts the selected county and age groups, and keeps download metadata for
traceability.
"""

from __future__ import annotations

import hashlib
import io
import json
import posixpath
import re
import ssl
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


TABLE6_PAGE_URL = "https://www.stat.gov.tw/News_Content.aspx?n=4580&s=232642"
DEFAULT_COUNTY = "新北市"
DEFAULT_CACHE_DIR = Path(tempfile.gettempdir()) / "newtaipei_hack_wage_cache"
REQUEST_TIMEOUT_SECONDS = 120
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; NewTaipeiHack/1.0)"

# The DGBAS file host currently sends the leaf certificate without this AIA
# intermediate. It is public, source-specific, and used only to complete the
# normal certificate chain; hostname and certificate verification stay enabled.
TWCA_SECURE_SSL_INTERMEDIATE_PEM = """-----BEGIN CERTIFICATE-----
MIIFxjCCA66gAwIBAgIQQAE0s2gAAAAAAAAM0KoI7DANBgkqhkiG9w0BAQsFADBR
MQswCQYDVQQGEwJUVzESMBAGA1UEChMJVEFJV0FOLUNBMRAwDgYDVQQLEwdSb290
IENBMRwwGgYDVQQDExNUV0NBIEdsb2JhbCBSb290IENBMB4XDTIzMTAxNjA5MDEw
NFoXDTMwMTAxNjE1NTk1OVowUzELMAkGA1UEBhMCVFcxEjAQBgNVBAoTCVRBSVdB
Ti1DQTEwMC4GA1UEAxMnVFdDQSBTZWN1cmUgU1NMIENlcnRpZmljYXRpb24gQXV0
aG9yaXR5MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyS5amjYQhd10
hZs00r7RXdI3ASka2AQmJnOyA6bqvAYOMlMECUdlsjDccdmMdHx8YTYYMtmCy+UB
RJZ/ytVANVQlfcUvXzWfauFs8XpCC/Th+Ed2tIEEGK218QsBebImAHPGDvp2Yglj
XVaQR/0FeN1lIzQ3iUkad0dCsC/bxFiWsmsjeSscTaxrYzHFADUhK0qj4W5PmOuw
lAR3C4XXgzPAI3V0qBpQ7sqgNLaNBFTZkP6AVryZC+DapfWBIMmIxIOg8g25MKb4
XvXkCLYKIxi8Djhv1zSmLLrKbQFZrjWlD/OWqInPPmSwBrKZ13EMQhoRRi1pXfN+
J2ugR/PUQQIDAQABo4IBljCCAZIwHwYDVR0jBBgwFoAUSNvN3o7pSXJaiOix2D0H
s7lrZlAwHQYDVR0OBBYEFJLn+mIWcYzzl3FCxgan4EZhS1y2MA4GA1UdDwEB/wQE
AwIBhjAdBgNVHSUEFjAUBggrBgEFBQcDAQYIKwYBBQUHAwIwSgYDVR0gBEMwQTA1
BgsrBgEEAYK/JQEBFTAmMCQGCCsGAQUFBwIBFhhodHRwczovL3d3dy50d2NhLmNv
bS50dy8wCAYGZ4EMAQICMEkGA1UdHwRCMEAwPqA8oDqGOGh0dHA6Ly9yb290Y2Eu
dHdjYS5jb20udHcvVFdDQVJDQS9nbG9iYWxfcmV2b2tlXzQwOTYuY3JsMBIGA1Ud
EwEB/wQIMAYBAf8CAQAwdgYIKwYBBQUHAQEEajBoMDwGCCsGAQUFBzAChjBodHRw
Oi8vc3Nsc2VydmVyLnR3Y2EuY29tLnR3L2NhY2VydC9yb290NDA5Ni5jcnQwKAYI
KwYBBQUHMAGGHGh0dHA6Ly9yb290b2NzcC50d2NhLmNvbS50dy8wDQYJKoZIhvcN
AQELBQADggIBADVzQW2rRsMiWoVrBdZX1BiOgN6B/Ryt2zpq8uRxFQspvGYfUVIm
4uU4AaPR7aQ5KwpKjDWv2ncvX2ssCY54B82g2mxEEVEdu5PFl0jkuk4LmPsClYZc
6J6odUbVI3wtv2yF6+fqQrO+gDhEIhlg3IqWICfiyJZS+p2TirMszGzs4a+K9tZX
rS2W/jKsSt4bSmcIzDpwm2gSaSuLDIAwq0WrD29kA7+N+rMMs4zBIVKyYm9r08q4
UOGU16J7mKBrF0KYDZFyT9Hq5HAX2uwYoQJxQ5Z0BR8eZH8AIIi2vsFC8pkv2ra1
2dldd3Pivm0mdratbn1Z6MQ71FKR9Ui3L8P+0xu8DkhhxE11Ogpl+aquBUqGcvlD
0SgpXy+eoeFaRhFXRUkWtH/3XYo+h+N+4jZmgjCLd4+YI+u5tbUGpyBMABmUDiqZ
xcrPGc4cvXExqYePUg6cFCDcjqGCxqSu5BPbA5R+DSTkn5Sc1WQzORJpD5b7pcEq
8msolev88dcmddLXMyWzXQfPHA4vaQD74lr5LIzn6BRjVv+ZB7Y0ZTnnOimDXxn7
Cxqd+1/8ldRis/tO/JWZsMm5ruvCppwCZUdXjSNI5R1OxzVwTVLzsCoiSYPV0agd
a5dQ9wayB6OohBK7+ZU2V3sZwE2xwHdDzfhbdzmI++TxtOurDHbkfkED
-----END CERTIFICATE-----"""

AGE_GROUPS = (
    "總計",
    "未滿30歲",
    "未滿25歲",
    "25-29歲",
    "30-39歲",
    "40-49歲",
    "50-64歲",
    "65歲以上",
)
MEASURES = ("平均數", "中位數")

OpenURL = Callable[..., Any]

XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ODS_OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
ODS_TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
ODS_TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


class WageCollectorError(RuntimeError):
    """Raised when the official Table 6 source cannot be parsed safely."""


def _open_url(request: Request, *, timeout: int) -> Any:
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=TWCA_SECURE_SSL_INTERMEDIATE_PEM)
    return urlopen(request, timeout=timeout, context=context)


class _DownloadLinkParser(HTMLParser):
    """Collect anchor hrefs and visible text from the official download page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        self._href = attributes.get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        self.links.append((self._href, "".join(self._text).strip()))
        self._href = None
        self._text = []


def fetch_wage(
    county: str | None = DEFAULT_COUNTY,
    year: str | int | None = None,
    *,
    cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
    page_url: str = TABLE6_PAGE_URL,
    open_url: OpenURL = _open_url,
) -> dict[str, Any]:
    """Fetch DGBAS Table 6 records for a county and year.

    ``county`` defaults to ``新北市``.  Pass ``county=None`` to return every
    county row in the selected worksheet.  ``year`` accepts ``"113年"`` or
    ``113`` and defaults to the newest worksheet in the downloaded file.

    The response is an envelope with long-form records and download metadata.
    The cache stores all county records for the selected worksheet so a later
    county filter does not require another spreadsheet parse.
    """

    normalized_county = _normalize_county(county)
    normalized_year = _normalize_year(year)
    cache_path = Path(cache_dir) if cache_dir is not None else None

    page_request = Request(
        page_url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": USER_AGENT,
        },
    )
    page_bytes = _request_bytes(
        page_request,
        open_url=open_url,
        description="DGBAS Table 6 download page",
    )
    links = _discover_download_links(page_bytes, page_url=page_url)
    if not links:
        raise WageCollectorError(
            "DGBAS Table 6 download page does not expose an XLSX or ODS link"
        )

    errors: list[str] = []
    for source_url, file_format in links:
        try:
            spreadsheet_bytes = _request_bytes(
                Request(
                    source_url,
                    headers={
                        "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.oasis.opendocument.spreadsheet",
                        "User-Agent": USER_AGENT,
                    },
                ),
                open_url=open_url,
                description=f"DGBAS Table 6 {file_format} file",
            )
            file_hash = "sha256:" + hashlib.sha256(spreadsheet_bytes).hexdigest()

            cached = _load_cache(
                cache_path,
                file_hash=file_hash,
                file_format=file_format,
                requested_year=normalized_year,
            )
            if cached is None:
                sheets = _read_spreadsheet(spreadsheet_bytes, file_format)
                selected_sheet, published_year = _select_sheet(
                    sheets,
                    requested_year=normalized_year,
                )
                records = _parse_sheet(
                    sheets[selected_sheet],
                    sheet_name=selected_sheet,
                    published_year=published_year,
                )
                _save_cache(
                    cache_path,
                    file_hash=file_hash,
                    file_format=file_format,
                    published_year=published_year,
                    records=records,
                )
            else:
                published_year, records = cached

            filtered_records = [
                record
                for record in records
                if normalized_county is None
                or record["縣市別"] == normalized_county
            ]
            if normalized_county is not None and not filtered_records:
                raise WageCollectorError(
                    f"DGBAS Table 6 does not contain county {normalized_county}"
                )

            return {
                "records": filtered_records,
                "metadata": {
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "published_year": published_year,
                    "source_url": source_url,
                    "file_hash": file_hash,
                },
            }
        except WageCollectorError as exc:
            errors.append(str(exc))

    detail = "; ".join(errors)
    raise WageCollectorError(
        "Unable to download or parse any DGBAS Table 6 XLSX/ODS file"
        + (f": {detail}" if detail else "")
    )


def _normalize_county(county: str | None) -> str | None:
    if county is None:
        return None
    if not isinstance(county, str) or not county.strip():
        raise WageCollectorError("county must be a non-empty string or None")
    return county.strip()


def _normalize_year(year: str | int | None) -> str | None:
    if year is None:
        return None
    if isinstance(year, bool) or not isinstance(year, (str, int)):
        raise WageCollectorError("year must be a ROC year such as 113 or 113年")
    value = str(year).strip()
    if value.endswith("年"):
        value = value[:-1].strip()
    if not value.isdigit():
        raise WageCollectorError("year must be a ROC year such as 113 or 113年")
    return value + "年"


def _request_bytes(
    request: Request,
    *,
    open_url: OpenURL,
    description: str,
) -> bytes:
    try:
        with open_url(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
    except HTTPError as exc:
        raise WageCollectorError(
            f"{description} HTTP error: {exc.code} {exc.reason}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise WageCollectorError(f"{description} request failed: {exc}") from exc

    if not isinstance(body, bytes):
        raise WageCollectorError(f"{description} returned non-byte content")
    if not body:
        raise WageCollectorError(f"{description} returned an empty response")
    if len(body) > MAX_DOWNLOAD_BYTES:
        raise WageCollectorError(
            f"{description} exceeds the {MAX_DOWNLOAD_BYTES} byte limit"
        )
    return body


def _discover_download_links(page_bytes: bytes, *, page_url: str) -> list[tuple[str, str]]:
    parser = _DownloadLinkParser()
    try:
        parser.feed(page_bytes.decode("utf-8", errors="replace"))
        parser.close()
    except Exception as exc:  # HTMLParser can fail on malformed page markup.
        raise WageCollectorError(
            "DGBAS Table 6 download page contains invalid HTML"
        ) from exc

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, text in parser.links:
        absolute_url = _encode_url_path(urljoin(page_url, href))
        path = urlsplit(absolute_url).path.lower()
        if not path.endswith((".xlsx", ".ods")):
            continue
        if "表6" not in text and "表6" not in href and "薪資統計" not in text:
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        file_format = ".xlsx" if path.endswith(".xlsx") else ".ods"
        candidates.append((absolute_url, file_format))

    return sorted(candidates, key=lambda item: 0 if item[1] == ".xlsx" else 1)


def _encode_url_path(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/%:@"),
            parts.query,
            parts.fragment,
        )
    )


def _read_spreadsheet(data: bytes, file_format: str) -> dict[str, list[list[Any]]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if file_format == ".xlsx":
                return _read_xlsx(archive)
            if file_format == ".ods":
                return _read_ods(archive)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
        raise WageCollectorError(
            f"DGBAS Table 6 {file_format} file is not a valid spreadsheet"
        ) from exc

    raise WageCollectorError(f"Unsupported DGBAS Table 6 format: {file_format}")


def _read_xlsx(archive: zipfile.ZipFile) -> dict[str, list[list[Any]]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relationship_targets = {
        relationship.attrib["Id"]: relationship.attrib["Target"]
        for relationship in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }
    shared_strings = _read_shared_strings(archive)

    sheets_element = workbook.find(f"{{{XLSX_MAIN_NS}}}sheets")
    if sheets_element is None:
        raise WageCollectorError("XLSX workbook is missing sheets")

    sheets: dict[str, list[list[Any]]] = {}
    for sheet in sheets_element:
        name = sheet.attrib.get("name", "").strip()
        relationship_id = sheet.attrib.get(f"{{{XLSX_REL_NS}}}id")
        if not name or not relationship_id or relationship_id not in relationship_targets:
            raise WageCollectorError("XLSX workbook contains an invalid sheet reference")
        target = relationship_targets[relationship_id].lstrip("/")
        sheet_path = target if target.startswith("xl/") else posixpath.join("xl", target)
        sheets[name] = _read_xlsx_sheet(archive.read(sheet_path), shared_strings)

    if not sheets:
        raise WageCollectorError("XLSX workbook contains no worksheets")
    return sheets


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(text.text or "" for text in item.findall(f".//{{{XLSX_MAIN_NS}}}t"))
        for item in root.findall(f"{{{XLSX_MAIN_NS}}}si")
    ]


def _read_xlsx_sheet(data: bytes, shared_strings: list[str]) -> list[list[Any]]:
    root = ET.fromstring(data)
    sheet_data = root.find(f"{{{XLSX_MAIN_NS}}}sheetData")
    if sheet_data is None:
        return []

    rows: list[list[Any]] = []
    for row_element in sheet_data.findall(f"{{{XLSX_MAIN_NS}}}row"):
        cells: dict[int, Any] = {}
        for cell in row_element.findall(f"{{{XLSX_MAIN_NS}}}c"):
            reference = cell.attrib.get("r", "")
            column_index = _column_index(reference)
            cells[column_index] = _read_xlsx_cell(cell, shared_strings)
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(index, "") for index in range(width)])
        else:
            rows.append([])
    return rows


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha()).upper()
    if not letters:
        raise WageCollectorError(f"XLSX cell has an invalid reference: {reference!r}")
    index = 0
    for character in letters:
        index = index * 26 + ord(character) - ord("A") + 1
    return index - 1


def _read_xlsx_cell(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(f".//{{{XLSX_MAIN_NS}}}t"))

    value = cell.find(f"{{{XLSX_MAIN_NS}}}v")
    raw_value = value.text if value is not None else ""
    if cell_type == "s" and raw_value:
        try:
            return shared_strings[int(raw_value)]
        except (IndexError, ValueError) as exc:
            raise WageCollectorError("XLSX cell references an invalid shared string") from exc
    if cell_type == "b":
        return raw_value == "1"
    return raw_value


def _read_ods(archive: zipfile.ZipFile) -> dict[str, list[list[Any]]]:
    root = ET.fromstring(archive.read("content.xml"))
    spreadsheet = root.find(f".//{{{ODS_OFFICE_NS}}}spreadsheet")
    if spreadsheet is None:
        raise WageCollectorError("ODS document is missing a spreadsheet body")

    sheets: dict[str, list[list[Any]]] = {}
    for table in spreadsheet.findall(f"{{{ODS_TABLE_NS}}}table"):
        name = table.attrib.get(f"{{{ODS_TABLE_NS}}}name", "").strip()
        if not name:
            continue
        rows: list[list[Any]] = []
        for row in table.findall(f"{{{ODS_TABLE_NS}}}table-row"):
            values: list[Any] = []
            for cell in row:
                if cell.tag not in {
                    f"{{{ODS_TABLE_NS}}}table-cell",
                    f"{{{ODS_TABLE_NS}}}covered-table-cell",
                }:
                    continue
                repeated = _positive_repeat(
                    cell.attrib.get(f"{{{ODS_TABLE_NS}}}number-columns-repeated", "1")
                )
                value = _read_ods_cell(cell)
                values.extend([value] * repeated)
            repeated_rows = _positive_repeat(
                row.attrib.get(f"{{{ODS_TABLE_NS}}}number-rows-repeated", "1")
            )
            rows.extend([values.copy() for _ in range(repeated_rows)])
        sheets[name] = rows

    if not sheets:
        raise WageCollectorError("ODS document contains no worksheets")
    return sheets


def _positive_repeat(value: str) -> int:
    try:
        repeated = int(value)
    except ValueError as exc:
        raise WageCollectorError(f"Spreadsheet repetition count is invalid: {value!r}") from exc
    if not 1 <= repeated <= 10000:
        raise WageCollectorError(f"Spreadsheet repetition count is out of range: {value!r}")
    return repeated


def _read_ods_cell(cell: ET.Element) -> Any:
    value_type = cell.attrib.get(f"{{{ODS_OFFICE_NS}}}value-type")
    raw_value = cell.attrib.get(f"{{{ODS_OFFICE_NS}}}value")
    text = "\n".join(
        "".join(node.itertext())
        for node in cell.findall(f".//{{{ODS_TEXT_NS}}}p")
    )
    if value_type in {"float", "currency", "percentage"} and raw_value is not None:
        return raw_value
    return text


def _select_sheet(
    sheets: dict[str, list[list[Any]]],
    *,
    requested_year: str | None,
) -> tuple[str, str]:
    sheet_years: list[tuple[int, str, str]] = []
    for name, rows in sheets.items():
        year = _extract_year(name, rows)
        if year is not None:
            sheet_years.append((int(year[:-1]), name, year))

    if not sheet_years:
        raise WageCollectorError("Table 6 workbook contains no recognizable ROC year")

    if requested_year is not None:
        for _, name, year in sheet_years:
            if year == requested_year:
                return name, year
        available = ", ".join(year for _, _, year in sorted(sheet_years))
        raise WageCollectorError(
            f"Table 6 does not contain year {requested_year}; available years: {available}"
        )

    _, name, year = max(sheet_years)
    return name, year


def _extract_year(sheet_name: str, rows: Iterable[list[Any]]) -> str | None:
    match = re.search(r"(\d{2,3})年", sheet_name)
    if match:
        return match.group(1) + "年"
    for row in rows:
        for value in row:
            text = _clean_text(value)
            if re.fullmatch(r"\d{2,3}年", text):
                return text
    return None


def _parse_sheet(
    rows: list[list[Any]],
    *,
    sheet_name: str,
    published_year: str,
) -> list[dict[str, Any]]:
    if len(rows) < 8:
        raise WageCollectorError(f"Table 6 worksheet {sheet_name} has too few rows")

    average_start = _find_header_column(rows[:8], "平均數")
    median_start = _find_header_column(rows[:8], "中位數")
    if average_start is None or median_start is None:
        raise WageCollectorError(
            f"Table 6 worksheet {sheet_name} is missing average or median headers"
        )

    unit = _find_unit(rows[:8])
    if unit is None:
        raise WageCollectorError(f"Table 6 worksheet {sheet_name} is missing its unit")

    if not _headers_contain_age_groups(rows[:8], average_start):
        raise WageCollectorError(
            f"Table 6 worksheet {sheet_name} is missing expected age headers"
        )

    regions: list[tuple[str, list[Any]]] = []
    for row in rows[7:]:
        if not row:
            continue
        county = _clean_text(row[0] if len(row) > 0 else "")
        if not county or not _looks_like_region(county):
            continue
        if county == "總計":
            continue
        regions.append((county, row))

    if not regions:
        raise WageCollectorError(f"Table 6 worksheet {sheet_name} has no county rows")

    records: list[dict[str, Any]] = []
    for county, row in regions:
        for measure, start in (("平均數", average_start), ("中位數", median_start)):
            assert start is not None
            for offset, age_group in enumerate(AGE_GROUPS):
                value = row[start + offset] if start + offset < len(row) else ""
                records.append(
                    {
                        "資料年度": published_year,
                        "縣市別": county,
                        "統計方式": measure,
                        "年齡別": age_group,
                        "薪資": _coerce_number(value),
                        "單位": unit,
                        "原始欄位": f"{measure}／{age_group}",
                    }
                )
    return records


def _find_header_column(rows: list[list[Any]], label: str) -> int | None:
    for row in rows:
        for index, value in enumerate(row):
            if _clean_text(value) == label:
                return index
    return None


def _find_unit(rows: list[list[Any]]) -> str | None:
    for row in rows:
        for value in row:
            match = re.search(r"單位\s*[:：]\s*(.+)", _clean_text(value))
            if match:
                return match.group(1).strip()
    return None


def _headers_contain_age_groups(rows: list[list[Any]], average_start: int | None) -> bool:
    if average_start is None:
        return False
    values = {
        _clean_text(row[index])
        for row in rows
        for index in range(average_start, min(average_start + 8, len(row)))
        if _clean_text(row[index])
    }
    return set(AGE_GROUPS).issubset(values)


def _looks_like_region(value: str) -> bool:
    return value.endswith(("市", "縣"))


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _coerce_number(value: Any) -> int | float | None:
    text = _clean_text(value).replace(",", "")
    if text in {"", "-", "—", "－", "NA", "N/A"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise WageCollectorError(f"Table 6 contains a non-numeric wage value: {value!r}") from exc
    rounded = round(number, 10)
    return int(rounded) if rounded.is_integer() else rounded


def _load_cache(
    cache_dir: Path | None,
    *,
    file_hash: str,
    file_format: str,
    requested_year: str | None,
) -> tuple[str, list[dict[str, Any]]] | None:
    if cache_dir is None:
        return None
    metadata_path = cache_dir / "metadata.json"
    records_path = cache_dir / "records.json"
    if not metadata_path.exists() or not records_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        records = json.loads(records_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, dict) or not isinstance(records, list):
        return None
    if metadata.get("file_hash") != file_hash or metadata.get("file_format") != file_format:
        return None
    published_year = metadata.get("published_year")
    if not isinstance(published_year, str):
        return None
    if requested_year is not None and published_year != requested_year:
        return None
    if not all(isinstance(record, dict) for record in records):
        return None
    return published_year, records


def _save_cache(
    cache_dir: Path | None,
    *,
    file_hash: str,
    file_format: str,
    published_year: str,
    records: list[dict[str, Any]],
) -> None:
    if cache_dir is None:
        return
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "file_hash": file_hash,
                    "file_format": file_format,
                    "published_year": published_year,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (cache_dir / "records.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise WageCollectorError(f"Unable to write Table 6 cache: {exc}") from exc
