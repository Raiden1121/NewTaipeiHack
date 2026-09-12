import csv
import io
import ssl
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.errors import CollectorNoDataError  # noqa: E402
from collectors.historical_population import (  # noqa: E402
    HISTORICAL_POPULATION_RESOURCE_URLS,
    HistoricalPopulationCollectorError,
    _open_url,
    fetch_historical_population,
)
from collectors.population_collector import (  # noqa: E402
    fetch_population_for_period,
)
from orchestration.contracts import CollectorSpec, PeriodStrategy  # noqa: E402


class FakeResponse:
    def __init__(self, content: bytes):
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._content


def archive_bytes(*, statistic_month: str = "10312") -> bytes:
    fieldnames = ["統計年月", "區域別", "村里", "戶數", "人口數", "人口數-男", "人口數-女"]
    for age in range(18, 36):
        fieldnames.extend((f"{age}歲-男", f"{age}歲-女"))
    row = {
        "統計年月": statistic_month,
        "區域別": "新北市板橋區",
        "村里": "中山里",
        "戶數": "1493",
        "人口數": "3917",
        "人口數-男": "1983",
        "人口數-女": "1934",
    }
    for age in range(18, 36):
        row[f"{age}歲-男"] = str(age)
        row[f"{age}歲-女"] = str(age + 1)

    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"opendata-{statistic_month}_age_cityname/opendata-{statistic_month}_age-65000.csv",
            "\ufeff" + csv_buffer.getvalue(),
        )
    return zip_buffer.getvalue()


def fake_open_url(content: bytes, requests: list | None = None):
    def open_url(request, timeout):
        if requests is not None:
            requests.append((request, timeout))
        return FakeResponse(content)

    return open_url


class TestHistoricalPopulationCollector(unittest.TestCase):
    def test_normalizes_single_age_archive_to_population_raw_contract(self):
        payload = fetch_historical_population(
            "10312", open_url=fake_open_url(archive_bytes())
        )

        self.assertEqual(len(payload.records), 1)
        record = payload.records[0]
        self.assertEqual(record["statistic_yyymm"], "10312")
        self.assertEqual(record["site_id"], "新北市板橋區")
        self.assertEqual(record["village"], "中山里")
        self.assertEqual(record["people_total"], "3917")
        self.assertEqual(record["people_age_018_m"], "18")
        self.assertEqual(record["people_age_035_f"], "36")
        self.assertEqual(record["source_dataset"], "moi_village_population")
        self.assertEqual(record["source_row"], "2")
        self.assertEqual(payload.metadata["source_period"], "10312")
        self.assertEqual(payload.metadata["record_count"], 1)
        self.assertEqual(len(payload.artifacts), 1)
        self.assertEqual(payload.artifacts[0].media_type, "application/zip")
        self.assertTrue(payload.artifacts[0].sha256.startswith("sha256:"))

    def test_routes_10312_through_archive_instead_of_odrp014(self):
        requests = []
        payload = fetch_population_for_period(
            "10312", open_url=fake_open_url(archive_bytes(), requests)
        )

        self.assertEqual(len(payload.records), 1)
        self.assertEqual(requests[0][0].full_url, HISTORICAL_POPULATION_RESOURCE_URLS["10312"])
        self.assertEqual(requests[0][1], 30)

    def test_period_router_uses_historical_tls_opener_by_default(self):
        with patch("collectors.population_collector.fetch_historical_population") as fetch:
            fetch_population_for_period("10312")

        self.assertIs(fetch.call_args.kwargs["open_url"], _open_url)

    def test_rejects_unsupported_historical_period_as_no_data(self):
        with self.assertRaises(CollectorNoDataError):
            fetch_historical_population("10311", open_url=fake_open_url(archive_bytes()))

    def test_rejects_archive_without_required_age_columns(self):
        invalid_archive = io.BytesIO()
        with zipfile.ZipFile(invalid_archive, "w") as archive:
            archive.writestr(
                "opendata-10312_age_cityname/opendata-10312_age-65000.csv",
                "統計年月,區域別,村里,人口數\n10312,新北市板橋區,中山里,1\n",
            )

        with self.assertRaises(HistoricalPopulationCollectorError):
            fetch_historical_population(
                "10312", open_url=fake_open_url(invalid_archive.getvalue())
            )

    def test_default_https_opener_disables_only_openssl_strict_flag(self):
        with patch("collectors.historical_population.urlopen") as open_url:
            _open_url(Request("https://example.test/source.zip"), timeout=30)

        context = open_url.call_args.kwargs["context"]
        strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
        if strict_flag is not None:
            self.assertFalse(context.verify_flags & strict_flag)

    def test_pipeline_population_collector_uses_period_aware_route(self):
        import run_pipeline  # noqa: WPS433, E402

        with patch.object(run_pipeline, "fetch_population_for_period") as collect:
            run_pipeline._collect_population("10312")

        collect.assert_called_once_with("10312", county="新北市")

    def test_pipeline_retention_protects_registered_historical_population(self):
        import run_pipeline  # noqa: WPS433, E402

        spec = CollectorSpec("population", lambda _period: [], PeriodStrategy.MONTHLY)
        with patch.object(run_pipeline, "prune_local_data", return_value={}) as prune:
            run_pipeline._run_retention(
                output_dir="/tmp/test-output",
                specs=(spec,),
                statuses=({"status": "ok"},),
                current_period="11509",
                retention_years=5,
            )

        self.assertEqual(
            prune.call_args.kwargs["protected_periods"],
            {"population": {"10312", "10712", "11112"}},
        )


if __name__ == "__main__":
    unittest.main()
