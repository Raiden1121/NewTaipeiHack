import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.published_snapshot import publish_homepage_snapshot  # noqa: E402


class TestPublishedSnapshot(unittest.TestCase):
    def test_publishes_named_analysis_and_records_quality_in_manifest(self):
        homepage = {
            "metric_id": "homepage",
            "calculation_version": "1",
            "generated_at": "2026-09-11T09:39:13.190552+00:00",
            "time_policy": {"annual_years_roc": [110, 111, 112, 113, 114]},
            "kpi": {},
            "districts": [],
            "annual": {},
            "policy": {},
            "elections": {},
            "service_coverage": {},
        }
        analysis = {
            "metric_id": "employment",
            "generated_at": "2026-09-11T09:39:13.190552+00:00",
            "districts": [],
        }
        analysis_quality = {
            "source_periods": {"job_vacancies": ["11509"]},
            "coverage": {"district_count": 29, "plot1_regression_sample_size": 29},
            "warnings": ["wage_proxy"],
        }

        with tempfile.TemporaryDirectory() as tempdir:
            result = publish_homepage_snapshot(
                homepage,
                {},
                output_dir=tempdir,
                snapshot_id="dev-employment",
                analyses={"employment": analysis},
                analysis_quality={"employment": analysis_quality},
            )

            analysis_path = result.snapshot_dir / "analyses" / "employment.json"
            self.assertTrue(analysis_path.is_file())
            self.assertEqual(json.loads(analysis_path.read_text(encoding="utf-8")), analysis)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["artifacts"]["analyses"],
                {"employment": "analyses/employment.json"},
            )
            entry = next(item for item in manifest["datasets"] if item["dataset"] == "employment")
            self.assertEqual(entry["source_period"], {"job_vacancies": ["11509"]})
            self.assertEqual(entry["coverage"]["district_count"], 29)
            self.assertEqual(entry["quality_flags"], ["wage_proxy"])

    def test_publishes_homepage_artifacts_and_switches_current_pointer_last(self):
        homepage = {
            "metric_id": "homepage",
            "calculation_version": "1",
            "generated_at": "2026-09-11T09:39:13.190552+00:00",
            "time_policy": {"annual_years_roc": [110, 111, 112, 113, 114]},
            "kpi": {"cityYouthPopulation": 123},
            "districts": [
                {
                    "district_id": "65000010",
                    "district_name": "板橋區",
                    "opportunityIndex": 46.17,
                    "fertilityRate": None,
                }
            ],
            "annual": {"fertility": {"years": []}},
            "policy": {"budgetTrend": []},
            "elections": {"borough_chief_v1": []},
            "service_coverage": {"status": "partial"},
        }
        quality = {
            "warnings": ["incomplete_village_population_coverage"],
            "blocking_reasons": ["incomplete_village_population_coverage"],
            "source_periods": {"population": ["11401", "11402"]},
        }

        with tempfile.TemporaryDirectory() as tempdir:
            result = publish_homepage_snapshot(
                homepage,
                quality,
                output_dir=tempdir,
                snapshot_id="dev-snapshot",
            )

            snapshot_dir = Path(tempdir) / "analytics" / "published" / "dev-snapshot"
            self.assertEqual(result.snapshot_id, "dev-snapshot")
            self.assertTrue((snapshot_dir / "manifest.json").is_file())
            self.assertTrue((snapshot_dir / "dashboard_overview.json").is_file())
            self.assertTrue((snapshot_dir / "district_details.json").is_file())

            current = json.loads(
                (Path(tempdir) / "analytics" / "published" / "current.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(current, {"snapshot_id": "dev-snapshot"})

            manifest = json.loads(
                (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["snapshot_id"], "dev-snapshot")
            self.assertEqual(
                manifest["artifacts"],
                {
                    "dashboard_overview": "dashboard_overview.json",
                    "district_details": "district_details.json",
                    "analyses": {},
                },
            )
            self.assertEqual(manifest["warnings"], ["incomplete_village_population_coverage"])

            overview = json.loads(
                (snapshot_dir / "dashboard_overview.json").read_text(encoding="utf-8")
            )
            self.assertEqual(overview["kpis"], {"cityYouthPopulation": 123})
            self.assertEqual(overview["districts"][0]["district_id"], "65000010")
            self.assertEqual(overview["availability"]["fertility"], "unavailable")

            details = json.loads(
                (snapshot_dir / "district_details.json").read_text(encoding="utf-8")
            )
            self.assertEqual(details["districts"][0]["district_id"], "65000010")
            self.assertEqual(details["districts"][0]["metrics"]["fertilityRate"], None)

    def test_rejects_unsafe_snapshot_id(self):
        with self.assertRaises(ValueError):
            publish_homepage_snapshot(
                {"metric_id": "homepage", "districts": []},
                {},
                output_dir=tempfile.mkdtemp(),
                snapshot_id="../outside",
            )

    def test_rejects_unsafe_analysis_name(self):
        with self.assertRaises(ValueError):
            publish_homepage_snapshot(
                {"metric_id": "homepage", "districts": []},
                {},
                output_dir=tempfile.mkdtemp(),
                analyses={"../employment": {}},
            )


if __name__ == "__main__":
    unittest.main()
