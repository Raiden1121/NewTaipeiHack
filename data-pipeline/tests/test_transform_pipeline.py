import hashlib
import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from functools import partial
from io import StringIO
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_DIR = PROJECT_DIR / "data-pipeline" / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from run_pipeline import (  # noqa: E402
    CollectorSpec,
    DEFAULT_COLLECTOR_SPECS,
    main,
    run_full_pipeline,
    run_period_range,
)
from collectors.errors import CollectorNoDataError  # noqa: E402
from orchestration.contracts import PeriodStrategy  # noqa: E402
from orchestration.retry import collect_with_retry  # noqa: E402
from transform.geography import DistrictResolver  # noqa: E402
from transform.io import (  # noqa: E402
    write_source_artifacts,
    write_curated,
    write_period_range_report,
    write_raw,
)
from collectors.contracts import CollectedPayload, SourceArtifact  # noqa: E402
from run_pipeline import _raw_and_transform_payload  # noqa: E402
from transform.pipeline import (  # noqa: E402
    UnsupportedDatasetError,
    canonicalize_dataset,
    run_transform,
)


def population_row():
    row = {
        "statistic_yyymm": "11405",
        "district_code": "65000010001",
        "site_id": "板橋區",
        "village": "甲里",
        "people_total": "100",
    }
    for age in range(18, 36):
        row[f"people_age_{age:03d}_m"] = "1" if age == 18 else "0"
        row[f"people_age_{age:03d}_f"] = "1" if age == 35 else "0"
    return row


def house_price_row():
    return {
        "district": "板橋區",
        "transaction_date": "1140521",
        "total_price": 12000000,
        "building_area_sqm": 30.5,
        "price_per_sqm": 393443,
        "price_per_ping": 1300640,
        "transaction_type": "房地(土地+建物)",
        "snapshot_fetched_at": "2025-05-22T00:00:00+00:00",
    }


def youth_budget_row():
    return {
        "document_id": "youth_budgets:115:legal_budget:abc",
        "budget_year_roc": "115",
        "document_status": "legal_budget",
        "document_status_label": "法定預算",
        "row_type": "total",
        "business_plan": "新北市政府青年局合計",
        "work_plan": None,
        "budget_amount": "213,022",
        "ratio_percent": "100.00",
        "unit_label": "新臺幣千元",
        "table_title": "計畫及預算統計表",
        "source_page_number": 28,
        "source_document_url": "https://example.test/115",
        "source_pdf_sha256": "sha256:abc",
    }


class TestTransformPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_DIR / "districts.json")

    def test_dispatches_population_and_rejects_unknown_dataset(self):
        result = run_transform("population", [population_row()], resolver=self.resolver)

        self.assertEqual(len(result.records), 4)
        self.assertEqual(result.records[-1]["metric_id"], "youth_18_35_total")
        with self.assertRaisesRegex(UnsupportedDatasetError, "unknown_dataset"):
            run_transform("unknown_dataset", [])

    def test_dispatches_youth_topic_transforms_with_config_dir(self):
        join_result = run_transform(
            "join_proposals",
            [
                {
                    "proposal_id": "p-1",
                    "title": "青年居住",
                    "content": "社宅",
                    "submitted_at": "1140102",
                }
            ],
            config_dir=CONFIG_DIR,
        )
        self.assertEqual(join_result.records[0]["dataset"], "join_proposals")

        minutes_result = run_transform(
            "youth_council_minutes",
            [
                {
                    "meeting_id": "m-1",
                    "meeting_name": "青年會議",
                    "meeting_date": "1140102",
                    "year_roc": "114",
                    "page_texts": ["提案事項\n一、社宅\n決議事項\n提請市議會"],
                }
            ],
            config_dir=CONFIG_DIR,
        )
        self.assertEqual(minutes_result.records[0]["dataset"], "youth_council_minutes")

    def test_youth_service_transform_loads_static_location_reference(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_dir = Path(tempdir)
            reference_dir = config_dir / "reference"
            reference_dir.mkdir()
            (reference_dir / "youth_service_points_locations.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "records": [
                            {
                                "point_id": "innovation",
                                "address": "新北市三重區重新路一段108號3樓",
                                "source_district_name": "三重區",
                                "x_3826": 300530.403775,
                                "y_3826": 2772867.4135083,
                                "source_url": "https://example.test/address",
                                "source_type": "official_manual_reference",
                                "verified_at": "2026-09-11",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = run_transform(
                "youth_service_points",
                [
                    {
                        "point_id": "innovation",
                        "point_type": "startup_base",
                        "name": "新北創力坊",
                        "address": None,
                        "latitude": None,
                        "longitude": None,
                        "geocode_status": "not_attempted",
                    }
                ],
                resolver=self.resolver,
                config_dir=config_dir,
            )

            self.assertEqual(result.records[0]["geocode_status"], "matched")
            self.assertEqual(result.records[0]["address"], "新北市三重區重新路一段108號3樓")

    def test_writes_hash_checked_source_artifact_with_relative_metadata(self):
        content = b"%PDF-test"
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        artifact = SourceArtifact(
            filename="115_legal_budget_abc.pdf",
            content=content,
            media_type="application/pdf",
            sha256=digest,
        )

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            metadata = write_source_artifacts(
                [artifact], dataset="youth_budgets", output_dir=output_dir
            )

            artifact_path = output_dir / "raw" / "youth_budgets" / "artifacts" / artifact.filename
            self.assertEqual(artifact_path.read_bytes(), content)
            self.assertEqual(
                metadata,
                [
                    {
                        "path": "raw/youth_budgets/artifacts/115_legal_budget_abc.pdf",
                        "media_type": "application/pdf",
                        "sha256": digest,
                        "size_bytes": len(content),
                    }
                ],
            )

    def test_source_artifact_writer_rejects_path_traversal_and_hash_mismatch(self):
        content = b"%PDF-test"
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaises(ValueError):
                write_source_artifacts(
                    [
                        SourceArtifact(
                            filename="../escape.pdf",
                            content=content,
                            media_type="application/pdf",
                            sha256="sha256:" + hashlib.sha256(content).hexdigest(),
                        )
                    ],
                    dataset="youth_budgets",
                    output_dir=Path(tempdir),
                )
            with self.assertRaises(ValueError):
                write_source_artifacts(
                    [
                        SourceArtifact(
                            filename="safe.pdf",
                            content=content,
                            media_type="application/pdf",
                            sha256="sha256:" + "0" * 64,
                        )
                    ],
                    dataset="youth_budgets",
                    output_dir=Path(tempdir),
                )

    def test_collected_payload_keeps_records_metadata_and_artifacts_separate(self):
        content = b"%PDF-test"
        artifact = SourceArtifact(
            filename="115_legal_budget_abc.pdf",
            content=content,
            media_type="application/pdf",
            sha256="sha256:" + hashlib.sha256(content).hexdigest(),
        )
        collected = CollectedPayload(
            records=[{"budget_year_roc": "115"}],
            metadata={"documents": [{"document_id": "doc-115"}]},
            artifacts=(artifact,),
        )

        raw_payload, transform_input, artifacts = _raw_and_transform_payload(
            "youth_budgets",
            collected,
            period="11601",
            fetched_at="2026-09-09T00:00:00+00:00",
        )

        self.assertEqual(raw_payload["records"], collected.records)
        self.assertEqual(raw_payload["documents"], collected.metadata["documents"])
        self.assertEqual(transform_input, collected.records)
        self.assertEqual(artifacts, collected.artifacts)

    def test_college_dispatch_accepts_two_source_envelope(self):
        result = run_transform(
            "college_majors",
            {"overview_records": [], "detail_records": []},
        )

        self.assertEqual(result.records, [])
        self.assertEqual(result.quality["rows_in"], 0)

    def test_collector_aliases_use_one_canonical_dataset_identity(self):
        bus = {
            "StopUID": "NWT1001",
            "StopPosition": {"PositionLat": 25.0114, "PositionLon": 121.4618},
        }

        result = run_transform("bus_stop", [bus], resolver=self.resolver)

        self.assertEqual(canonicalize_dataset("bus_stop"), "bus_stops")
        self.assertEqual(canonicalize_dataset("job_vacancy_salary"), "job_vacancy_salaries")
        self.assertEqual(result.records[0]["dataset"], "bus_stops")

    def test_default_specs_cover_non_tdx_collectors(self):
        datasets = {spec.dataset for spec in DEFAULT_COLLECTOR_SPECS}

        self.assertTrue({
            "population", "movement", "births", "marriages",
            "house_prices", "rentals", "job_vacancies",
            "job_vacancy_salaries", "wages", "college_majors",
            "graduate_majors", "vt_courses", "training_numbers",
            "talent_demand", "babysitting_places",
        }.issubset(datasets))

    def test_all_available_typed_payload_writes_raw_artifact_and_all_output(self):
        content = b"%PDF-test"
        artifact = SourceArtifact(
            filename="115_legal_budget_abc.pdf",
            content=content,
            media_type="application/pdf",
            sha256="sha256:" + hashlib.sha256(content).hexdigest(),
        )
        calls = []

        def collect(period):
            calls.append(period)
            return CollectedPayload(
                records=[youth_budget_row()],
                metadata={"documents": [{"document_id": "doc-115"}]},
                artifacts=(artifact,),
            )

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            report = run_period_range(
                "11501",
                "11601",
                output_dir=output_dir,
                config_dir=CONFIG_DIR,
                collector_specs=[
                    CollectorSpec("youth_budgets", collect, PeriodStrategy.ALL_AVAILABLE)
                ],
            )

            self.assertEqual(report["status"], "ok")
            self.assertEqual(calls, ["11601"])
            raw_paths = list((output_dir / "raw" / "youth_budgets").glob("*.json"))
            self.assertEqual(len(raw_paths), 1)
            raw = json.loads(raw_paths[0].read_text())
            self.assertEqual(raw["documents"], [{"document_id": "doc-115"}])
            self.assertEqual(raw["source_artifacts"][0]["size_bytes"], len(content))
            self.assertEqual(
                (output_dir / "raw" / "youth_budgets" / "artifacts" / artifact.filename).read_bytes(),
                content,
            )
            self.assertTrue((output_dir / "curated" / "youth_budgets" / "all.json").exists())
            self.assertTrue((output_dir / "quality" / "youth_budgets" / "all.json").exists())
            self.assertTrue((output_dir / "quarantine" / "youth_budgets" / "all.json").exists())

    def test_youth_budget_raw_replay_does_not_call_collector(self):
        content = b"%PDF-test"
        artifact = SourceArtifact(
            filename="115_legal_budget_abc.pdf",
            content=content,
            media_type="application/pdf",
            sha256="sha256:" + hashlib.sha256(content).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            raw_path = write_raw(
                {
                    "dataset": "youth_budgets",
                    "period": "11601",
                    "fetched_at": "2026-09-09T00:00:00+00:00",
                    "documents": [{"document_id": "doc-115"}],
                    "source_artifacts": [{"path": "raw/youth_budgets/artifacts/115_legal_budget_abc.pdf"}],
                    "records": [youth_budget_row()],
                },
                dataset="youth_budgets",
                snapshot="11601_20260909T000000Z",
                output_dir=root / "data",
            )

            from unittest.mock import patch

            with patch("run_pipeline.fetch_youth_budgets", side_effect=AssertionError("must not collect")):
                exit_code = main(
                    [
                        "--dataset", "youth_budgets",
                        "--input", str(raw_path),
                        "--output-dir", str(root / "replay"),
                        "--config-dir", str(CONFIG_DIR),
                    ]
                )

            curated = json.loads(
                (root / "replay" / "curated" / "youth_budgets.json").read_text()
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(curated["records"][0]["value"], 213022)

    def test_youth_topic_raw_replay_writes_all_available_output_without_collecting(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            raw_path = write_raw(
                {
                    "dataset": "join_proposals",
                    "period": "11509",
                    "fetched_at": "2026-09-09T00:00:00+00:00",
                    "records": [
                        {
                            "proposal_id": "p-1",
                            "title": "青年社宅",
                            "content": "居住正義",
                            "submitted_at": "1140102",
                        }
                    ],
                },
                dataset="join_proposals",
                snapshot="11509_20260909T000000Z",
                output_dir=root / "data",
            )

            from unittest.mock import patch

            with patch("run_pipeline.fetch_join_proposals", side_effect=AssertionError("must not collect")):
                exit_code = main(
                    [
                        "--dataset", "join_proposals",
                        "--input", str(raw_path),
                        "--output-dir", str(root / "replay"),
                        "--config-dir", str(CONFIG_DIR),
                    ]
                )

            curated_path = root / "replay" / "curated" / "join_proposals" / "all.json"
            curated = json.loads(curated_path.read_text())

        self.assertEqual(exit_code, 0)
        self.assertTrue(curated["records"][0]["youth_topic_proxy"])

    def test_writes_raw_curated_quality_and_quarantine_json(self):
        result = run_transform("population", [population_row()], resolver=self.resolver)
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)

            raw_path = write_raw(
                {"dataset": "population", "records": [population_row()]},
                dataset="population",
                snapshot="20260901T000000Z",
                output_dir=output_dir,
            )
            curated_path, quality_path, quarantine_path = write_curated(
                result,
                dataset="population",
                output_dir=output_dir,
            )

            self.assertEqual(raw_path, output_dir / "raw" / "population" / "20260901T000000Z.json")
            self.assertEqual(curated_path, output_dir / "curated" / "population.json")
            self.assertEqual(quality_path, output_dir / "quality" / "population.json")
            self.assertEqual(quarantine_path, output_dir / "quarantine" / "population.json")
            self.assertEqual(json.loads(curated_path.read_text())["records"][-1]["value"], 2)
            self.assertEqual(json.loads(quality_path.read_text())["rows_in"], 1)
            self.assertEqual(json.loads(quarantine_path.read_text()), [])

    def test_cli_reads_saved_raw_without_fetching_live_data(self):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            raw_path = temp_path / "raw.json"
            raw_path.write_text(
                json.dumps({"dataset": "population", "records": [population_row()]}, ensure_ascii=False),
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "--dataset", "population",
                    "--input", str(raw_path),
                    "--output-dir", str(temp_path / "data"),
                    "--config-dir", str(CONFIG_DIR),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((temp_path / "data" / "curated" / "population.json").exists())
            self.assertTrue((temp_path / "data" / "quality" / "population.json").exists())
            self.assertTrue((temp_path / "data" / "quarantine" / "population.json").exists())

    def test_full_run_collects_writes_raw_and_transforms_each_dataset(self):
        specs = [CollectorSpec("population", lambda period: [population_row()])]

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            report = run_full_pipeline(
                "11507",
                output_dir=output_dir,
                config_dir=CONFIG_DIR,
                collector_specs=specs,
            )

            self.assertEqual(report["datasets"]["population"]["status"], "ok")
            raw_paths = list((output_dir / "raw" / "population").glob("*.json"))
            self.assertEqual(len(raw_paths), 1)
            raw_payload = json.loads(raw_paths[0].read_text())
            self.assertEqual(raw_payload["period"], "11507")
            self.assertEqual(raw_payload["records"][0]["site_id"], "板橋區")
            self.assertEqual(
                json.loads((output_dir / "curated" / "population.json").read_text())["records"][-1]["value"],
                2,
            )
            self.assertTrue((output_dir / "quality" / "population.json").exists())
            self.assertTrue((output_dir / "quarantine" / "population.json").exists())
            self.assertTrue((output_dir / "quality" / "collection.json").exists())

    def test_full_run_skips_empty_period_and_records_reason(self):
        specs = [CollectorSpec("population", lambda period: [])]

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            report = run_full_pipeline(
                "11507",
                output_dir=output_dir,
                config_dir=CONFIG_DIR,
                collector_specs=specs,
            )

            self.assertEqual(report["datasets"]["population"]["status"], "skipped")
            self.assertEqual(report["datasets"]["population"]["reason"], "no_data")
            self.assertFalse((output_dir / "curated" / "population.json").exists())
            self.assertEqual(
                json.loads((output_dir / "quality" / "collection.json").read_text())["period"],
                "11507",
            )

    def test_period_range_includes_periods_and_does_not_overwrite_outputs(self):
        def collect(period):
            return [population_row()] if period == "11507" else []

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            report = run_period_range(
                "11506",
                "11508",
                output_dir=output_dir,
                config_dir=CONFIG_DIR,
                collector_specs=[CollectorSpec("population", collect)],
            )

            self.assertEqual(report["periods"], ["11506", "11507", "11508"])
            self.assertEqual(report["period_reports"][0]["datasets"]["population"]["status"], "skipped")
            self.assertEqual(report["period_reports"][1]["datasets"]["population"]["status"], "ok")
            self.assertEqual(report["period_reports"][2]["datasets"]["population"]["status"], "skipped")
            curated_path = output_dir / "curated" / "population" / "11507.json"
            quality_path = output_dir / "quality" / "population" / "11507.json"
            self.assertTrue(curated_path.exists())
            self.assertEqual(json.loads(curated_path.read_text())["period"], "11507")
            self.assertEqual(json.loads(quality_path.read_text())["period"], "11507")
            self.assertEqual(list((output_dir / "curated" / "population").glob("*.json")), [curated_path])
            self.assertTrue((output_dir / "quality" / "collection_range.json").exists())

    def test_period_range_runs_annual_sources_once_per_roc_year(self):
        calls = []

        def collect(period):
            calls.append(period)
            return [population_row()]

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            report = run_period_range(
                "11411",
                "11502",
                output_dir=output_dir,
                config_dir=CONFIG_DIR,
                collector_specs=[
                    CollectorSpec("population", collect, PeriodStrategy.ANNUAL),
                ],
            )

            self.assertEqual(report["periods"], ["11411", "11412", "11501", "11502"])
            self.assertEqual(calls, ["11401", "11501"])
            self.assertTrue((output_dir / "curated" / "population" / "114.json").exists())
            self.assertTrue((output_dir / "curated" / "population" / "115.json").exists())

    def test_period_range_persists_source_aware_snapshot_and_all_available_units(self):
        snapshot_calls = []
        all_available_calls = []
        house_price = {
            "district": "板橋區",
            "transaction_date": "1140521",
            "total_price": 12000000,
            "building_area_sqm": 30.5,
            "price_per_sqm": 393443,
            "price_per_ping": 1300640,
            "transaction_type": "房地(土地+建物)",
            "snapshot_fetched_at": "2025-05-22T00:00:00+00:00",
        }
        talent_demand = {
            "統計期": "112年",
            "職業別": "技術員及助理專業人員",
            "新登記求才人數（人次）": "100",
            "新登記求才僱用人數（人次）": "70",
            "有效求才僱用人數（人次）": "60",
        }

        def collect_house_prices(period):
            snapshot_calls.append(period)
            return [house_price]

        def collect_talent_demand(period):
            all_available_calls.append(period)
            return [talent_demand]

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            report = run_period_range(
                "11411",
                "11502",
                output_dir=output_dir,
                config_dir=CONFIG_DIR,
                collector_specs=[
                    CollectorSpec(
                        "house_prices",
                        collect_house_prices,
                        PeriodStrategy.SNAPSHOT,
                    ),
                    CollectorSpec(
                        "talent_demand",
                        collect_talent_demand,
                        PeriodStrategy.ALL_AVAILABLE,
                    ),
                ],
            )

            self.assertEqual(report["status"], "ok")
            self.assertEqual(snapshot_calls, ["11502"])
            self.assertEqual(all_available_calls, ["11502"])
            for output_kind in ("curated", "quality", "quarantine"):
                self.assertEqual(
                    [
                        path.name
                        for path in (output_dir / output_kind / "house_prices").glob("*.json")
                    ],
                    ["latest.json"],
                )
                self.assertEqual(
                    [
                        path.name
                        for path in (output_dir / output_kind / "talent_demand").glob("*.json")
                    ],
                    ["all.json"],
                )

            house_record = json.loads(
                (output_dir / "curated" / "house_prices" / "latest.json").read_text()
            )["records"][0]
            talent_record = json.loads(
                (output_dir / "curated" / "talent_demand" / "all.json").read_text()
            )["records"][0]
            self.assertEqual(
                (house_record["period_start"], house_record["period_end"]),
                ("2025-05-21", "2025-05-21"),
            )
            self.assertEqual(
                (talent_record["period_start"], talent_record["period_end"]),
                ("2023-01-01", "2023-12-31"),
            )

    def test_single_period_resume_does_not_reuse_flat_output_from_another_period(self):
        calls = []

        def collect_population(period):
            calls.append(period)
            row = population_row()
            row["statistic_yyymm"] = period
            return [row]

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            common_args = [
                "--output-dir", str(output_dir),
                "--config-dir", str(CONFIG_DIR),
            ]

            from unittest.mock import patch

            with patch(
                "run_pipeline.DEFAULT_COLLECTOR_SPECS",
                (CollectorSpec("population", collect_population),),
            ):
                first_exit = main(["--period", "11506", *common_args])
                resume_exit = main(
                    ["--period", "11507", *common_args, "--resume"]
                )

            report = json.loads(
                (output_dir / "quality" / "collection.json").read_text()
            )
            curated = json.loads(
                (output_dir / "curated" / "population.json").read_text()
            )
            index = json.loads(
                (output_dir / "quality" / "dataset_index.json").read_text()
            )

        status = report["datasets"]["population"]
        index_entry = index["datasets"]["population"][0]
        self.assertEqual((first_exit, resume_exit), (0, 0))
        self.assertEqual(calls, ["11506", "11507"])
        self.assertEqual(
            (status["source_period"], status["output_key"]),
            ("11507", "11507"),
        )
        self.assertEqual(status["action"], "download")
        self.assertTrue(status["downloaded"])
        self.assertFalse(status["reused_output"])
        self.assertEqual(curated["records"][0]["period_start"], "2026-07-01")
        self.assertEqual(
            (index_entry["source_period"], index_entry["output_key"]),
            ("11507", "11507"),
        )

    def test_cli_resume_reuses_success_retries_failure_and_force_downloads_all(self):
        calls = {"population": 0, "house_prices": 0}

        def collect_population(_period):
            calls["population"] += 1
            return [population_row()]

        def collect_house_prices(_period):
            calls["house_prices"] += 1
            if calls["house_prices"] == 1:
                raise RuntimeError("temporary source failure")
            return [house_price_row()]

        specs = (
            CollectorSpec("population", collect_population),
            CollectorSpec(
                "house_prices", collect_house_prices, PeriodStrategy.SNAPSHOT
            ),
        )
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            legacy_path = output_dir / "curated" / "house_prices" / "11001.json"
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text("{}", encoding="utf-8")
            args = [
                "--start-period", "11507",
                "--end-period", "11507",
                "--output-dir", str(output_dir),
                "--config-dir", str(CONFIG_DIR),
            ]
            terminal = StringIO()

            from unittest.mock import patch

            with redirect_stderr(terminal):
                with patch("run_pipeline.DEFAULT_COLLECTOR_SPECS", specs):
                    first_exit = main(args)
                    first_index = json.loads(
                        (output_dir / "quality" / "dataset_index.json").read_text()
                    )
                    resume_exit = main([*args, "--resume"])
                    calls_after_resume = dict(calls)
                    resume_report = json.loads(
                        (output_dir / "quality" / "collection_range.json").read_text()
                    )
                    resumed_index = json.loads(
                        (output_dir / "quality" / "dataset_index.json").read_text()
                    )
                    force_exit = main([*args, "--force"])

        self.assertEqual((first_exit, resume_exit, force_exit), (0, 0, 0))
        self.assertEqual(calls_after_resume, {"population": 1, "house_prices": 2})
        self.assertEqual(calls, {"population": 2, "house_prices": 3})
        self.assertEqual(list(first_index["datasets"]), ["population"])
        self.assertEqual(
            set(resumed_index["datasets"]), {"population", "house_prices"}
        )
        self.assertNotIn("11001.json", json.dumps(resumed_index))
        statuses = {
            entry["dataset"]: entry for entry in resume_report["execution_units"]
        }
        self.assertTrue(statuses["population"]["reused_output"])
        self.assertFalse(statuses["population"]["downloaded"])
        self.assertTrue(statuses["house_prices"]["downloaded"])
        self.assertEqual(statuses["house_prices"]["attempts"], 1)

    def test_cli_resume_replays_legacy_raw_without_calling_collector(self):
        calls = 0

        def collect_population(_period):
            nonlocal calls
            calls += 1
            return [population_row()]

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            raw_path = write_raw(
                {
                    "dataset": "population",
                    "period": "11507",
                    "fetched_at": "2026-09-01T00:00:00+00:00",
                    "records": [population_row()],
                },
                dataset="population",
                snapshot="11507_20260901T000000Z",
                output_dir=output_dir,
            )
            legacy_curated = output_dir / "curated" / "population" / "11507.json"
            legacy_curated.parent.mkdir(parents=True)
            legacy_curated.write_text('{"legacy": true}', encoding="utf-8")
            write_period_range_report(
                {
                    "execution_units": [
                        {
                            "dataset": "population",
                            "source_period": "11507",
                            "output_key": "11507",
                            "status": "ok",
                            "raw_path": str(raw_path),
                            "curated_path": str(legacy_curated),
                        }
                    ]
                },
                output_dir=output_dir,
            )
            terminal = StringIO()

            from unittest.mock import patch

            with redirect_stderr(terminal):
                with patch(
                    "run_pipeline.DEFAULT_COLLECTOR_SPECS",
                    (CollectorSpec("population", collect_population),),
                ):
                    exit_code = main(
                        [
                            "--start-period", "11507",
                            "--end-period", "11507",
                            "--output-dir", str(output_dir),
                            "--config-dir", str(CONFIG_DIR),
                            "--resume",
                        ]
                    )

            report = json.loads(
                (output_dir / "quality" / "collection_range.json").read_text()
            )
            curated = json.loads(legacy_curated.read_text())

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls, 0)
        self.assertNotIn("legacy", curated)
        self.assertTrue(report["execution_units"][0]["reused_raw"])
        self.assertEqual(report["execution_units"][0]["attempts"], 0)

    def test_typed_timeout_retry_records_three_attempts_after_success(self):
        attempts = 0

        def collect_population(_period):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TimeoutError("read timed out")
            return [population_row()]

        with tempfile.TemporaryDirectory() as tempdir:
            from unittest.mock import patch

            with patch(
                "run_pipeline.collect_with_retry",
                partial(collect_with_retry, sleep=lambda _delay: None),
            ):
                report = run_period_range(
                    "11507",
                    "11507",
                    output_dir=Path(tempdir) / "data",
                    config_dir=CONFIG_DIR,
                    collector_specs=[CollectorSpec("population", collect_population)],
                )

        unit_status = report["execution_units"][0]
        self.assertEqual(attempts, 3)
        self.assertEqual(unit_status["status"], "ok")
        self.assertEqual(unit_status["attempts"], 3)
        self.assertTrue(unit_status["downloaded"])

    def test_typed_no_data_stays_skipped_in_strict_resume_without_recollection(self):
        calls = 0

        def no_data(_period):
            nonlocal calls
            calls += 1
            raise CollectorNoDataError("ODRP014 has no data for 10501")

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            terminal = StringIO()

            from unittest.mock import patch

            with redirect_stderr(terminal):
                with patch(
                    "run_pipeline.DEFAULT_COLLECTOR_SPECS",
                    (CollectorSpec("population", no_data),),
                ):
                    first_exit = main(
                        [
                            "--start-period", "10501",
                            "--end-period", "10501",
                            "--output-dir", str(output_dir),
                            "--config-dir", str(CONFIG_DIR),
                            "--strict",
                        ]
                    )
                    resume_exit = main(
                        [
                            "--start-period", "10501",
                            "--end-period", "10501",
                            "--output-dir", str(output_dir),
                            "--config-dir", str(CONFIG_DIR),
                            "--strict",
                            "--resume",
                        ]
                    )

            report = json.loads(
                (output_dir / "quality" / "collection_range.json").read_text()
            )

        unit_status = report["execution_units"][0]
        self.assertEqual((first_exit, resume_exit), (0, 0))
        self.assertEqual(calls, 1)
        self.assertEqual(unit_status["status"], "skipped")
        self.assertEqual(unit_status["reason"], "no_data")
        self.assertEqual(unit_status["source_message"], "ODRP014 has no data for 10501")
        self.assertEqual(unit_status["attempts"], 0)

    def test_cli_rejects_resume_and_force_together(self):
        terminal = StringIO()

        with redirect_stderr(terminal):
            with self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "--start-period", "11507",
                        "--end-period", "11507",
                        "--resume",
                        "--force",
                    ]
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            "argument --force: not allowed with argument --resume",
            terminal.getvalue(),
        )

    def test_full_run_reports_collection_error_and_continues(self):
        def fail(_period):
            raise RuntimeError("source unavailable")

        specs = [
            CollectorSpec("population", lambda period: [population_row()]),
            CollectorSpec("broken_dataset", fail),
        ]

        with tempfile.TemporaryDirectory() as tempdir:
            report = run_full_pipeline(
                "11507",
                output_dir=Path(tempdir) / "data",
                config_dir=CONFIG_DIR,
                collector_specs=specs,
            )

            self.assertEqual(report["datasets"]["broken_dataset"]["status"], "error")
            self.assertIn("source unavailable", report["datasets"]["broken_dataset"]["error"])
            self.assertEqual(report["datasets"]["population"]["status"], "ok")

    def test_cli_period_mode_runs_full_pipeline_with_injected_specs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            from unittest.mock import patch

            with patch("run_pipeline.DEFAULT_COLLECTOR_SPECS", (CollectorSpec("population", lambda period: [population_row()]),)):
                exit_code = main([
                    "--period", "11507",
                    "--output-dir", str(output_dir),
                    "--config-dir", str(CONFIG_DIR),
                ])

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "raw" / "population").exists())
            self.assertTrue((output_dir / "curated" / "population.json").exists())

    def test_cli_prints_only_concise_terminal_progress_and_summary(self):
        def no_data(_period):
            raise CollectorNoDataError("source has no data")

        def fail(_period):
            raise RuntimeError("source unavailable")

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir) / "data"
            terminal = StringIO()
            from unittest.mock import patch

            with redirect_stderr(terminal):
                with patch(
                    "run_pipeline.DEFAULT_COLLECTOR_SPECS",
                    (
                        CollectorSpec("population", lambda period: [population_row()]),
                        CollectorSpec("births", no_data),
                        CollectorSpec("broken_dataset", fail),
                    ),
                ):
                    exit_code = main([
                        "--period", "11507",
                        "--output-dir", str(output_dir),
                        "--config-dir", str(CONFIG_DIR),
                    ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                terminal.getvalue().splitlines(),
                [
                    "[1/3] 正在處理 population（期間 11507）",
                    "[1/3] ✓ population 完成：1 → 4 筆",
                    "[2/3] 正在處理 births（期間 11507）",
                    "[2/3] - births 無資料，已跳過",
                    "[3/3] 正在處理 broken_dataset（期間 11507）",
                    "[3/3] ✗ broken_dataset 失敗：RuntimeError: source unavailable",
                    "全部完成：成功 1、無資料 1、失敗 1",
                ],
            )

    def test_cli_does_not_load_district_config_for_national_dataset(self):
        envelope = {
            "records": [{
                "資料年度": "113年", "縣市別": "新北市", "統計方式": "平均數",
                "年齡別": "25-29歲", "薪資": 60, "單位": "萬元",
            }],
            "metadata": {"fetched_at": "2026-09-01T00:00:00+00:00"},
        }
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            raw_path = temp_path / "wages.json"
            raw_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")

            exit_code = main([
                "--dataset", "wage",
                "--input", str(raw_path),
                "--output-dir", str(temp_path / "data"),
                "--config-dir", str(temp_path / "missing-config"),
            ])

            self.assertEqual(exit_code, 0)
            self.assertTrue((temp_path / "data" / "curated" / "wages.json").exists())


if __name__ == "__main__":
    unittest.main()
