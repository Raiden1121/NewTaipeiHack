import json
import os
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
