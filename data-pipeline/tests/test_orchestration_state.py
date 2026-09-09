import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from orchestration.contracts import (  # noqa: E402
    CollectorSpec,
    ExecutionUnit,
    PeriodStrategy,
)
from orchestration.state import (  # noqa: E402
    SCHEMA_VERSION,
    TRANSFORM_VERSION,
    ResumeAction,
    choose_resume_action,
    find_latest_raw,
    is_refresh_due,
    load_refresh_state,
    refresh_state_key,
    write_refresh_state,
)
from transform.io import write_dataset_index  # noqa: E402


class TestResumeDecision(unittest.TestCase):
    def test_reuses_current_version_output_when_the_file_exists(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_path = Path(tempdir) / "curated" / "population" / "11507.json"
            output_path.parent.mkdir(parents=True)
            output_path.write_text("{}", encoding="utf-8")

            action = choose_resume_action(
                report={
                    "status": "ok",
                    "schema_version": SCHEMA_VERSION,
                    "transform_version": TRANSFORM_VERSION,
                },
                output_path=output_path,
                raw_path=None,
                resume=True,
                force=False,
            )

        self.assertEqual(action, ResumeAction.REUSE_OUTPUT)

    def test_legacy_report_reuses_raw_instead_of_trusting_output(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            output_path = root / "curated" / "population" / "11507.json"
            raw_path = root / "raw" / "population" / "11507_old.json"
            output_path.parent.mkdir(parents=True)
            raw_path.parent.mkdir(parents=True)
            output_path.write_text("{}", encoding="utf-8")
            raw_path.write_text("{}", encoding="utf-8")

            action = choose_resume_action(
                report={"status": "ok"},
                output_path=output_path,
                raw_path=raw_path,
                resume=True,
                force=False,
            )

        self.assertEqual(action, ResumeAction.REUSE_RAW)

    def test_previous_transform_version_reuses_raw_instead_of_stale_output(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            output_path = root / "curated" / "population" / "10701.json"
            raw_path = root / "raw" / "population" / "10701_snapshot.json"
            output_path.parent.mkdir(parents=True)
            raw_path.parent.mkdir(parents=True)
            output_path.write_text("{}", encoding="utf-8")
            raw_path.write_text("{}", encoding="utf-8")

            action = choose_resume_action(
                report={
                    "status": "ok",
                    "schema_version": SCHEMA_VERSION,
                    "transform_version": "2026-09-02",
                },
                output_path=output_path,
                raw_path=raw_path,
                resume=True,
                force=False,
            )

        self.assertEqual(action, ResumeAction.REUSE_RAW)

    def test_failed_unit_without_raw_downloads_again(self):
        action = choose_resume_action(
            report={"status": "error", "schema_version": SCHEMA_VERSION},
            output_path=Path("missing-output.json"),
            raw_path=None,
            resume=True,
            force=False,
        )

        self.assertEqual(action, ResumeAction.DOWNLOAD)

    def test_no_data_unit_stays_skipped_when_older_matching_raw_exists(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            raw_path = root / "raw" / "population" / "11507_old.json"
            raw_path.parent.mkdir(parents=True)
            raw_path.write_text("{}", encoding="utf-8")

            action = choose_resume_action(
                report={"status": "skipped", "reason": "no_data"},
                output_path=root / "curated" / "population" / "11507.json",
                raw_path=raw_path,
                resume=True,
                force=False,
            )

        self.assertEqual(action, ResumeAction.KEEP_NO_DATA)

    def test_force_downloads_even_when_current_output_and_raw_exist(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            output_path = root / "output.json"
            raw_path = root / "raw.json"
            output_path.write_text("{}", encoding="utf-8")
            raw_path.write_text("{}", encoding="utf-8")

            action = choose_resume_action(
                report={
                    "status": "ok",
                    "schema_version": SCHEMA_VERSION,
                    "transform_version": TRANSFORM_VERSION,
                },
                output_path=output_path,
                raw_path=raw_path,
                resume=False,
                force=True,
            )

        self.assertEqual(action, ResumeAction.DOWNLOAD)


class TestRawSelection(unittest.TestCase):
    @staticmethod
    def _unit(dataset, strategy, source_period, output_key):
        return ExecutionUnit(
            CollectorSpec(dataset, lambda _period: [], strategy),
            source_period=source_period,
            output_key=output_key,
        )

    @staticmethod
    def _create_raw(raw_dir, name):
        path = raw_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return path

    def test_monthly_raw_matches_exact_requested_month_and_uses_newest_fetch(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            raw_dir = output_dir / "raw" / "population"
            self._create_raw(raw_dir, "11506_20260902T030000Z.json")
            self._create_raw(raw_dir, "11507_20260902T010000Z.json")
            expected = self._create_raw(raw_dir, "11507_20260902T020000Z.json")
            unit = self._unit(
                "population", PeriodStrategy.MONTHLY, "11507", "11507"
            )

            selected = find_latest_raw(output_dir, "population", unit)

        self.assertEqual(selected, expected)

    def test_annual_raw_matches_any_month_in_year_and_uses_newest_fetch(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            raw_dir = output_dir / "raw" / "births"
            self._create_raw(raw_dir, "11412_20260902T090000Z.json")
            self._create_raw(raw_dir, "11501_20260902T010000Z.json")
            expected = self._create_raw(raw_dir, "11512_20260902T020000Z.json")
            unit = self._unit("births", PeriodStrategy.ANNUAL, "11501", "115")

            selected = find_latest_raw(output_dir, "births", unit)

        self.assertEqual(selected, expected)

    def test_snapshot_raw_ignores_requested_historical_month_and_uses_newest_fetch(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            raw_dir = output_dir / "raw" / "house_prices"
            self._create_raw(raw_dir, "11507_20260902T010000Z.json")
            expected = self._create_raw(raw_dir, "10501_20260902T030000Z.json")
            self._create_raw(raw_dir, "11412_20260902T020000Z.json")
            unit = self._unit(
                "house_prices", PeriodStrategy.SNAPSHOT, "10501", "latest"
            )

            selected = find_latest_raw(output_dir, "house_prices", unit)

        self.assertEqual(selected, expected)

    def test_valid_fetch_timestamp_beats_lexically_later_old_legacy_name(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            raw_dir = output_dir / "raw" / "population"
            expected = self._create_raw(
                raw_dir, "11507_20260902T020000Z.json"
            )
            lexical_trap = self._create_raw(
                raw_dir, "11507_zzzz-legacy.json"
            )
            old_mtime_ns = 1_546_300_800_000_000_000
            os.utime(lexical_trap, ns=(old_mtime_ns, old_mtime_ns))
            unit = self._unit(
                "population", PeriodStrategy.MONTHLY, "11507", "11507"
            )

            selected = find_latest_raw(output_dir, "population", unit)

        self.assertEqual(selected, expected)

    def test_nonstandard_names_use_mtime_then_name_as_deterministic_fallback(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            raw_dir = output_dir / "raw" / "population"
            self._create_raw(raw_dir, "11507_20200101T000000Z.json")
            lexical_trap = self._create_raw(
                raw_dir, "11507_zzzz-older.json"
            )
            tied_first = self._create_raw(
                raw_dir, "11507_aaaa-newest.json"
            )
            expected = self._create_raw(
                raw_dir, "11507_mmmm-newest.json"
            )
            old_mtime_ns = 1_546_300_800_000_000_000
            newest_mtime_ns = 1_893_456_000_000_000_000
            os.utime(lexical_trap, ns=(old_mtime_ns, old_mtime_ns))
            for path in (tied_first, expected):
                os.utime(path, ns=(newest_mtime_ns, newest_mtime_ns))
            unit = self._unit(
                "population", PeriodStrategy.MONTHLY, "11507", "11507"
            )

            selected = find_latest_raw(output_dir, "population", unit)

        self.assertEqual(selected, expected)


class TestDatasetIndex(unittest.TestCase):
    def test_writes_only_explicit_current_execution_unit_outputs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            current_paths = (
                output_dir / "curated" / "population" / "11507.json",
                output_dir / "curated" / "house_prices" / "latest.json",
            )
            legacy_path = output_dir / "curated" / "house_prices" / "11001.json"
            for path in (*current_paths, legacy_path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")

            index_path = write_dataset_index(
                [
                    {
                        "dataset": "population",
                        "output_key": "11507",
                        "path": "curated/population/11507.json",
                    },
                    {
                        "dataset": "house_prices",
                        "output_key": "latest",
                        "path": "curated/house_prices/latest.json",
                    },
                ],
                output_dir=output_dir,
            )

            index_text = index_path.read_text(encoding="utf-8")
            payload = json.loads(index_text)
            self.assertNotIn("11001.json", index_text)

        self.assertEqual(
            payload,
            {
                "schema_version": 2,
                "datasets": {
                    "population": [
                        {
                            "output_key": "11507",
                            "path": "curated/population/11507.json",
                        }
                    ],
                    "house_prices": [
                        {
                            "output_key": "latest",
                            "path": "curated/house_prices/latest.json",
                        }
                    ],
                },
            },
        )


class RefreshStateTests(unittest.TestCase):
    @staticmethod
    def _unit(dataset="job_vacancies", output_key="latest"):
        return ExecutionUnit(
            CollectorSpec(dataset, lambda _period: [], PeriodStrategy.SNAPSHOT),
            source_period="11509",
            output_key=output_key,
        )

    def test_refresh_state_round_trips_under_quality_directory(self):
        state = {
            "schema_version": 1,
            "units": {
                "job_vacancies:latest": {
                    "dataset": "job_vacancies",
                    "source_period": "11509",
                    "output_key": "latest",
                    "status": "ok",
                    "last_checked_at": "2026-09-09T00:00:03+00:00",
                    "attempts": 1,
                }
            },
        }
        with tempfile.TemporaryDirectory() as tempdir:
            path = write_refresh_state(state, tempdir)
            loaded = load_refresh_state(tempdir)

        self.assertEqual(path, Path(tempdir) / "quality" / "refresh_state.json")
        self.assertEqual(loaded, state)

    def test_refresh_state_key_uses_dataset_and_output_key(self):
        self.assertEqual(refresh_state_key(self._unit()), "job_vacancies:latest")

    def test_no_data_entry_is_due_again_after_monthly_window(self):
        old = {
            "status": "skipped",
            "reason": "no_data",
            "last_checked_at": "2026-08-01T00:00:00+00:00",
        }
        now = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(is_refresh_due(old, now=now, profile="monthly"))

    def test_failed_only_excludes_successful_entry(self):
        old = {
            "status": "ok",
            "last_success_at": "2026-09-08T00:00:00+00:00",
        }
        now = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(is_refresh_due(old, now=now, profile="daily", failed_only=True))

    def test_failed_only_selects_error_without_selecting_no_data(self):
        now = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(
            is_refresh_due(
                {"status": "error", "last_checked_at": "2026-09-09T00:00:00+00:00"},
                now=now,
                profile="daily",
                failed_only=True,
            )
        )
        self.assertFalse(
            is_refresh_due(
                {
                    "status": "skipped",
                    "reason": "no_data",
                    "last_checked_at": "2026-09-01T00:00:00+00:00",
                },
                now=now,
                profile="monthly",
                failed_only=True,
            )
        )

    def test_successful_entry_is_not_due_until_daily_interval_elapses(self):
        old = {
            "status": "ok",
            "last_checked_at": "2026-09-08T12:00:00+00:00",
        }
        before = datetime(2026, 9, 9, 11, 59, tzinfo=timezone.utc)
        after = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(is_refresh_due(old, now=before, profile="daily"))
        self.assertTrue(is_refresh_due(old, now=after, profile="daily"))


if __name__ == "__main__":
    unittest.main()
