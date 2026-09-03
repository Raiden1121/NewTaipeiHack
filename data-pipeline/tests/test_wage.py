from __future__ import annotations

import io
import json
import ssl
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import wage  # noqa: E402
from collectors.errors import CollectorNoDataError  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._body


def _cell(column: str, row: int, value) -> str:
    reference = f"{column}{row}"
    if isinstance(value, (int, float)):
        return f'<c r="{reference}"><v>{value}</v></c>'
    escaped = (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        f'<c r="{reference}" t="inlineStr">'
        f"<is><t>{escaped}</t></is></c>"
    )


def _xlsx_sheet(year: str, rows: list[list[object]]) -> bytes:
    xml_rows = []
    columns = [
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
        "O",
        "P",
        "Q",
    ]
    for row_number, values in enumerate(rows, start=1):
        cells = "".join(
            _cell(column, row_number, year if value == "{year}" else value)
            for column, value in zip(columns, values)
            if value != ""
        )
        xml_rows.append(f'<row r="{row_number}">{cells}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(xml_rows)}</sheetData>"
        "</worksheet>"
    ).encode("utf-8")


def make_xlsx(*years: str) -> bytes:
    rows = [
        ["表6　工業及服務業全年總薪資統計－本國籍全時受僱員工按工作場所所在縣市別及年齡別分"],
        [],
        ["", "", "", "", "", "", "", "", "{year}", "", "", "", "", "", "", "", "單位：萬元"],
        ["", "平均數", "", "", "", "", "", "", "", "中位數"],
        ["", "總計", "未滿30歲", "", "", "30-39歲", "40-49歲", "50-64歲", "65歲以上", "總計", "未滿30歲", "", "", "30-39歲", "40-49歲", "50-64歲", "65歲以上"],
        ["", "", "", "未滿25歲", "25-29歲", "", "", "", "", "", "", "未滿25歲", "25-29歲", "", "", "", ""],
        [],
        ["總計", 80.0, 60.0, 50.0, 65.0, 75.0, 85.0, 86.0, 64.0, 60.0, 51.0, 45.0, 55.0, 62.0, 65.0, 60.0, 46.0],
        ["新北市", 71.1, 56.7, 48.3, 59.9, 69.0, 77.2, 76.2, 60.1, 55.7, 50.0, 45.1, 52.4, 57.3, 59.8, 56.6, 45.2],
        ["臺北市", 94.7, 65.5, 52.3, 69.7, 87.7, 106.6, 111.8, 78.4, 73.5, 57.5, 49.1, 61.5, 75.3, 87.0, 81.4, 49.5],
    ]

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        sheets = []
        relationships = []
        for index, sheet_year in enumerate(years, start=1):
            sheets.append(
                f'<sheet name="表6({sheet_year})" sheetId="{index}" '
                f'r:id="rId{index}"/>'
            )
            relationships.append(
                f'<Relationship Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
            )
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _xlsx_sheet(sheet_year, rows),
            )

        archive.writestr(
            "xl/workbook.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f"<sheets>{''.join(sheets)}</sheets></workbook>"
            ).encode(),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f"{''.join(relationships)}</Relationships>"
            ).encode(),
        )
    return output.getvalue()


def make_ods() -> bytes:
    rows = [
        ["表6　工業及服務業全年總薪資統計－本國籍全時受僱員工按工作場所所在縣市別及年齡別分"],
        [],
        ["", "", "", "", "", "", "", "", "113年", "", "", "", "", "", "", "", "單位：萬元"],
        ["", "平均數", "", "", "", "", "", "", "", "中位數"],
        ["", "總計", "未滿30歲", "", "", "30-39歲", "40-49歲", "50-64歲", "65歲以上", "總計", "未滿30歲", "", "", "30-39歲", "40-49歲", "50-64歲", "65歲以上"],
        ["", "", "", "未滿25歲", "25-29歲", "", "", "", "", "", "", "未滿25歲", "25-29歲", "", "", "", ""],
        [],
        ["新北市", 71.1, 56.7, 48.3, 59.9, 69.0, 77.2, 76.2, 60.1, 55.7, 50.0, 45.1, 52.4, 57.3, 59.8, 56.6, 45.2],
    ]

    def cell(value) -> str:
        if value == "":
            return "<table:table-cell/>"
        if isinstance(value, (int, float)):
            return (
                '<table:table-cell office:value-type="float" '
                f'office:value="{value}"><text:p>{value}</text:p></table:table-cell>'
            )
        escaped = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return (
            '<table:table-cell office:value-type="string">'
            f"<text:p>{escaped}</text:p></table:table-cell>"
        )

    table_rows = "".join(
        f"<table:table-row>{''.join(cell(value) for value in row)}</table:table-row>"
        for row in rows
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        "<office:body><office:spreadsheet>"
        f'<table:table table:name="表6(113年)">{table_rows}</table:table>'
        "</office:spreadsheet></office:body></office:document-content>"
    ).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("content.xml", content)
    return output.getvalue()


def _page(*links: tuple[str, str]) -> bytes:
    anchors = "".join(f'<a href="{href}">{text}</a>' for href, text in links)
    return f"<html><body>{anchors}</body></html>".encode()


def fake_table6_source(calls: list[str]):
    xlsx = make_xlsx("113年")

    def open_url(request, timeout):
        if urlsplit(request.full_url).path.endswith(".xlsx"):
            calls.append("spreadsheet")
            return FakeResponse(xlsx)
        return FakeResponse(_page(("https://example.test/table6.xlsx", "表6 XLSX")))

    return open_url


class TestWageCollector(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def cache_path(self, name: str) -> Path:
        return Path(self.tempdir.name) / name

    def test_fetches_latest_xlsx_from_discovered_link(self):
        xlsx = make_xlsx("112年", "113年")
        requests = []
        request_headers = []

        def open_url(request, timeout):
            requests.append(request.full_url)
            request_headers.append(dict(request.headers))
            if request.full_url == wage.TABLE6_PAGE_URL:
                return FakeResponse(
                    _page(
                        ("https://example.test/files/table6.xlsx", "表6 XLSX"),
                        ("https://example.test/files/table6.ods", "表6 ODS"),
                    )
                )
            return FakeResponse(xlsx)

        result = wage.fetch_wage(cache_dir=self.cache_path("latest"), open_url=open_url)

        self.assertEqual(result["metadata"]["published_year"], "113年")
        self.assertEqual(result["metadata"]["source_url"], "https://example.test/files/table6.xlsx")
        self.assertTrue(result["metadata"]["file_hash"].startswith("sha256:"))
        self.assertEqual(len(result["records"]), 16)
        self.assertTrue(request_headers[0]["User-agent"].startswith("Mozilla/5.0"))
        self.assertEqual(
            result["records"][2],
            {
                "資料年度": "113年",
                "縣市別": "新北市",
                "統計方式": "平均數",
                "年齡別": "未滿25歲",
                "薪資": 48.3,
                "單位": "萬元",
                "原始欄位": "平均數／未滿25歲",
            },
        )
        self.assertEqual(requests, [wage.TABLE6_PAGE_URL, "https://example.test/files/table6.xlsx"])

    def test_default_http_client_loads_official_intermediate_certificate(self):
        captured = {}

        def fake_urlopen(request, timeout, context):
            captured["request"] = request
            captured["timeout"] = timeout
            captured["context"] = context
            return FakeResponse(b"ok")

        original_urlopen = wage.urlopen
        wage.urlopen = fake_urlopen
        self.addCleanup(setattr, wage, "urlopen", original_urlopen)

        with wage._open_url(wage.Request("https://example.test"), timeout=7) as response:
            self.assertEqual(response.read(), b"ok")

        self.assertEqual(captured["timeout"], 7)
        self.assertEqual(captured["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(captured["context"].check_hostname)
        self.assertTrue(
            any(
                "TWCA Secure SSL Certification Authority" in str(certificate)
                for certificate in captured["context"].get_ca_certs()
            )
        )

    def test_encodes_non_ascii_download_paths(self):
        links = wage._discover_download_links(
            _page(("https://example.test/files/表6.xlsx", "表6 XLSX")),
            page_url=wage.TABLE6_PAGE_URL,
        )

        self.assertEqual(
            links,
            [("https://example.test/files/%E8%A1%A86.xlsx", ".xlsx")],
        )

    def test_supports_all_counties_and_selected_historical_year(self):
        xlsx = make_xlsx("112年", "113年")

        def open_url(request, timeout):
            if urlsplit(request.full_url).path.endswith(".xlsx"):
                return FakeResponse(xlsx)
            return FakeResponse(_page(("https://example.test/table6.xlsx", "表6")))

        all_counties = wage.fetch_wage(county=None, cache_dir=self.cache_path("all"), open_url=open_url)
        historical = wage.fetch_wage(
            year="112年",
            cache_dir=self.cache_path("historical"),
            open_url=open_url,
        )

        self.assertEqual({record["縣市別"] for record in all_counties["records"]}, {"新北市", "臺北市"})
        self.assertNotIn("總計", {record["縣市別"] for record in all_counties["records"]})
        self.assertEqual(historical["metadata"]["published_year"], "112年")
        self.assertEqual(historical["records"][0]["資料年度"], "112年")

    def test_supports_ods_when_xlsx_is_not_available(self):
        ods = make_ods()

        def open_url(request, timeout):
            if urlsplit(request.full_url).path.endswith(".ods"):
                return FakeResponse(ods)
            return FakeResponse(_page(("https://example.test/table6.ods", "表6 ODS")))

        result = wage.fetch_wage(cache_dir=self.cache_path("ods"), open_url=open_url)

        self.assertEqual(result["metadata"]["source_url"], "https://example.test/table6.ods")
        self.assertEqual(result["metadata"]["published_year"], "113年")
        self.assertEqual(result["records"][2]["薪資"], 48.3)

    def test_reuses_cached_records_when_source_hash_is_unchanged(self):
        xlsx = make_xlsx("113年")
        cache_dir = self.cache_path("cache")
        calls = {"file": 0}

        def open_url(request, timeout):
            if urlsplit(request.full_url).path.endswith(".xlsx"):
                calls["file"] += 1
                return FakeResponse(xlsx)
            return FakeResponse(_page(("https://example.test/table6.xlsx", "表6")))

        first = wage.fetch_wage(cache_dir=cache_dir, open_url=open_url)

        original_read_spreadsheet = wage._read_spreadsheet

        def fail_if_reparsed(*args, **kwargs):
            raise AssertionError("unchanged spreadsheet should use the cache")

        wage._read_spreadsheet = fail_if_reparsed
        self.addCleanup(setattr, wage, "_read_spreadsheet", original_read_spreadsheet)
        second = wage.fetch_wage(cache_dir=cache_dir, open_url=open_url)

        self.assertEqual(first["records"], second["records"])
        self.assertEqual(first["metadata"]["file_hash"], second["metadata"]["file_hash"])
        self.assertEqual(calls["file"], 2)
        self.assertTrue((cache_dir / "records.json").exists())
        self.assertTrue((cache_dir / "metadata.json").exists())

    def test_rejects_page_without_table6_download_link(self):
        with self.assertRaises(wage.WageCollectorError):
            wage.fetch_wage(
                cache_dir=self.cache_path("invalid"),
                open_url=lambda request, timeout: FakeResponse(b"<html></html>"),
            )

    def test_missing_requested_year_stops_without_trying_fallback_format(self):
        calls = []

        with self.assertRaises(CollectorNoDataError):
            wage.fetch_wage(
                year="115",
                cache_dir=None,
                open_url=fake_table6_source(calls),
            )

        self.assertEqual(calls.count("spreadsheet"), 1)


if __name__ == "__main__":
    unittest.main()
