import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from orchestration.contracts import CollectorSpec, PeriodStrategy
from run_pipeline import main, run_period_range, run_refresh


class RefreshRunnerTests(unittest.TestCase):
    def test_refresh_runs_only_due_selected_dataset(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            specs = (
                CollectorSpec(
                    "job_vacancies",
                    lambda period: [],
                    PeriodStrategy.SNAPSHOT,
                ),
            )
            profiles = {
                "daily": ("job_vacancies",),
                "weekly": (),
                "monthly": (),
            }
            status = {
                "status": "ok",
                "source_period": "11509",
                "output_key": "latest",
                "attempts": 1,
            }
            with patch("run_pipeline._run_execution_unit", return_value=status) as execute:
                report = run_refresh(
                    "daily",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    now=datetime(2026, 9, 9, tzinfo=timezone.utc),
                )

            self.assertEqual(report["status"], "ok")
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(execute.call_args.args[0].source_period, "11509")
            self.assertTrue((output_dir / "quality" / "refresh_state.json").is_file())
            self.assertTrue((output_dir / "quality" / "refresh_daily.json").is_file())

    def test_failed_only_does_not_run_successful_unit(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            state_dir = output_dir / "quality"
            state_dir.mkdir(parents=True)
            (state_dir / "refresh_state.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "units": {
                        "job_vacancies:latest": {
                            "dataset": "job_vacancies",
                            "output_key": "latest",
                            "status": "ok",
                            "last_success_at": "2026-09-09T00:00:00+00:00",
                        }
                    },
                }),
                encoding="utf-8",
            )
            specs = (
                CollectorSpec(
                    "job_vacancies",
                    lambda period: [],
                    PeriodStrategy.SNAPSHOT,
                ),
            )
            profiles = {
                "daily": ("job_vacancies",),
                "weekly": (),
                "monthly": (),
            }
            with patch("run_pipeline._run_execution_unit") as execute:
                report = run_refresh(
                    "daily",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    failed_only=True,
                    now=datetime(2026, 9, 9, 1, tzinfo=timezone.utc),
                )

            self.assertEqual(report["status"], "ok")
            execute.assert_not_called()

    def test_refresh_persists_unit_status_and_report(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            specs = (
                CollectorSpec(
                    "job_vacancies",
                    lambda period: [],
                    PeriodStrategy.SNAPSHOT,
                ),
            )
            profiles = {
                "daily": ("job_vacancies",),
                "weekly": (),
                "monthly": (),
            }
            status = {
                "status": "error",
                "source_period": "11509",
                "output_key": "latest",
                "attempts": 3,
                "error": "ConnectionResetError: reset",
            }
            now = datetime(2026, 9, 9, tzinfo=timezone.utc)
            with patch("run_pipeline._run_execution_unit", return_value=status):
                report = run_refresh(
                    "daily",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    strict=True,
                    now=now,
                )

            self.assertEqual(report["status"], "error")
            self.assertEqual(report["errors"], {"job_vacancies": status["error"]})
            self.assertEqual(report["selected_datasets"], ["job_vacancies"])
            self.assertEqual(report["execution_units"][0]["dataset"], "job_vacancies")
            state = json.loads(
                (output_dir / "quality" / "refresh_state.json").read_text(
                    encoding="utf-8"
                )
            )
            entry = state["units"]["job_vacancies:latest"]
            self.assertEqual(entry["status"], "error")
            self.assertEqual(entry["attempts"], 3)
            self.assertEqual(entry["last_started_at"], now.isoformat())
            refresh_report = json.loads(
                (output_dir / "quality" / "refresh_daily.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(refresh_report["state_path"], str(
                output_dir / "quality" / "refresh_state.json"
            ))

    def test_empty_due_refresh_is_a_successful_no_op(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            specs = (
                CollectorSpec(
                    "job_vacancies",
                    lambda period: [],
                    PeriodStrategy.SNAPSHOT,
                ),
            )
            profiles = {
                "daily": ("job_vacancies",),
                "weekly": (),
                "monthly": (),
            }
            state_dir = output_dir / "quality"
            state_dir.mkdir(parents=True)
            (state_dir / "refresh_state.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "units": {
                        "job_vacancies:latest": {
                            "dataset": "job_vacancies",
                            "output_key": "latest",
                            "status": "ok",
                            "last_checked_at": "2026-09-09T00:00:00+00:00",
                        }
                    },
                }),
                encoding="utf-8",
            )
            with patch("run_pipeline._run_execution_unit") as execute:
                report = run_refresh(
                    "daily",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    now=datetime(2026, 9, 9, 1, tzinfo=timezone.utc),
                )

            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["execution_units"], [])
            execute.assert_not_called()
            self.assertTrue((output_dir / "quality" / "refresh_daily.json").is_file())

    def test_empty_refresh_does_not_erase_existing_dataset_index(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            state_dir = output_dir / "quality"
            state_dir.mkdir(parents=True)
            existing_index = {
                "schema_version": 2,
                "datasets": {
                    "population": [
                        {
                            "output_key": "11509",
                            "path": "curated/population/11509.json",
                        }
                    ]
                },
            }
            index_path = state_dir / "dataset_index.json"
            index_path.write_text(
                json.dumps(existing_index),
                encoding="utf-8",
            )
            (state_dir / "refresh_state.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "units": {
                        "job_vacancies:latest": {
                            "dataset": "job_vacancies",
                            "output_key": "latest",
                            "status": "ok",
                            "last_checked_at": "2026-09-09T00:00:00+00:00",
                        }
                    },
                }),
                encoding="utf-8",
            )
            specs = (
                CollectorSpec(
                    "job_vacancies",
                    lambda period: [],
                    PeriodStrategy.SNAPSHOT,
                ),
            )
            profiles = {
                "daily": ("job_vacancies",),
                "weekly": (),
                "monthly": (),
            }
            with patch("run_pipeline._run_execution_unit") as execute:
                report = run_refresh(
                    "daily",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    now=datetime(2026, 9, 9, 1, tzinfo=timezone.utc),
                )

            self.assertEqual(report["status"], "ok")
            execute.assert_not_called()
            self.assertEqual(json.loads(index_path.read_text(encoding="utf-8")), existing_index)

    def test_refresh_merges_successful_curated_path_into_dataset_index(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            index_path = output_dir / "quality" / "dataset_index.json"
            index_path.parent.mkdir(parents=True)
            index_path.write_text(
                json.dumps({
                    "schema_version": 2,
                    "datasets": {
                        "population": [
                            {
                                "output_key": "11509",
                                "path": "curated/population/11509.json",
                            }
                        ],
                        "job_vacancies": [
                            {
                                "output_key": "latest",
                                "path": "curated/job_vacancies/old.json",
                            }
                        ],
                    },
                }),
                encoding="utf-8",
            )
            new_curated_path = output_dir / "curated" / "job_vacancies" / "latest.json"
            new_curated_path.parent.mkdir(parents=True)
            new_curated_path.write_text("{}", encoding="utf-8")
            specs = (
                CollectorSpec(
                    "job_vacancies",
                    lambda period: [],
                    PeriodStrategy.SNAPSHOT,
                ),
            )
            profiles = {
                "daily": ("job_vacancies",),
                "weekly": (),
                "monthly": (),
            }
            status = {
                "status": "ok",
                "source_period": "11509",
                "output_key": "latest",
                "curated_path": str(new_curated_path),
                "attempts": 1,
            }
            with patch("run_pipeline._run_execution_unit", return_value=status):
                report = run_refresh(
                    "daily",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    now=datetime(2026, 9, 9, tzinfo=timezone.utc),
                )

            self.assertEqual(report["status"], "ok")
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(
                index["datasets"]["population"],
                [{"output_key": "11509", "path": "curated/population/11509.json"}],
            )
            self.assertEqual(
                index["datasets"]["job_vacancies"],
                [{
                    "output_key": "latest",
                    "path": "curated/job_vacancies/latest.json",
                    "period_strategy": "snapshot",
                    "source_period": "11509",
                    "transform_version": "2026-09-02.1",
                }],
            )

    def test_cli_rejects_empty_dataset_name_before_refresh(self):
        with patch("run_pipeline.run_refresh") as execute:
            with self.assertRaises(SystemExit) as raised:
                main(["--refresh-profile", "daily", "--datasets", "job_vacancies,"])

        self.assertEqual(raised.exception.code, 2)
        execute.assert_not_called()

    def test_cli_rejects_datasets_without_refresh_even_when_empty(self):
        with patch("run_pipeline.run_period_range") as execute:
            with self.assertRaises(SystemExit) as raised:
                main(["--datasets", "", "--period", "11509"])

        self.assertEqual(raised.exception.code, 2)
        execute.assert_not_called()

    def test_cli_rejects_empty_historical_values_in_refresh_mode(self):
        for option in ("--input", "--period", "--start-period", "--end-period"):
            with self.subTest(option=option):
                with patch("run_pipeline.run_refresh") as execute:
                    with self.assertRaises(SystemExit) as raised:
                        main(["--refresh-profile", "daily", option, ""])

                self.assertEqual(raised.exception.code, 2)
                execute.assert_not_called()

    def test_successful_refresh_prunes_old_partition_and_writes_retention_report(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            old_path = output_dir / "curated" / "population" / "11009.json"
            current_path = output_dir / "curated" / "population" / "11509.json"
            old_path.parent.mkdir(parents=True)
            old_path.write_text("{}", encoding="utf-8")
            current_path.write_text("{}", encoding="utf-8")
            specs = (
                CollectorSpec("population", lambda period: [], PeriodStrategy.MONTHLY),
            )
            profiles = {"daily": (), "weekly": (), "monthly": ("population",)}
            status = {
                "status": "ok",
                "source_period": "11509",
                "output_key": "11509",
                "curated_path": str(current_path),
                "attempts": 1,
            }
            with patch("run_pipeline._run_execution_unit", return_value=status):
                report = run_refresh(
                    "monthly",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    now=datetime(2026, 9, 9, tzinfo=timezone.utc),
                )

            self.assertEqual(report["status"], "ok")
            self.assertFalse(old_path.exists())
            self.assertEqual(report["retention"]["deleted_count"], 1)
            retention = json.loads(
                (output_dir / "quality" / "retention_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(retention["status"], "ok")

    def test_refresh_error_keeps_old_data_and_skips_retention(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            old_path = output_dir / "curated" / "population" / "11009.json"
            old_path.parent.mkdir(parents=True)
            old_path.write_text("{}", encoding="utf-8")
            specs = (
                CollectorSpec("population", lambda period: [], PeriodStrategy.MONTHLY),
            )
            profiles = {"daily": (), "weekly": (), "monthly": ("population",)}
            status = {
                "status": "error",
                "source_period": "11509",
                "output_key": "11509",
                "attempts": 3,
                "error": "TimeoutError: timeout",
            }
            with patch("run_pipeline._run_execution_unit", return_value=status):
                report = run_refresh(
                    "monthly",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    strict=True,
                    now=datetime(2026, 9, 9, tzinfo=timezone.utc),
                )

            self.assertEqual(report["status"], "error")
            self.assertTrue(old_path.exists())
            self.assertEqual(report["retention"]["status"], "skipped")

    def test_historical_range_applies_retention_after_success(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            old_path = output_dir / "curated" / "population" / "11009.json"
            current_path = output_dir / "curated" / "population" / "11509.json"
            old_path.parent.mkdir(parents=True)
            old_path.write_text("{}", encoding="utf-8")
            current_path.write_text("{}", encoding="utf-8")
            specs = (
                CollectorSpec("population", lambda period: [], PeriodStrategy.MONTHLY),
            )
            status = {
                "status": "ok",
                "source_period": "11509",
                "output_key": "11509",
                "curated_path": str(current_path),
                "attempts": 1,
            }
            with patch("run_pipeline._run_execution_unit", return_value=status):
                report = run_period_range(
                    "11509",
                    "11509",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                )

            self.assertEqual(report["retention"]["status"], "ok")
            self.assertFalse(old_path.exists())


if __name__ == "__main__":
    unittest.main()
