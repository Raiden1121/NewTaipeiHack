import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_DIR = PROJECT_DIR / "data-pipeline" / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from orchestration.contracts import CollectorSpec, ExecutionUnit, PeriodStrategy  # noqa: E402
from run_pipeline import _run_execution_unit, main  # noqa: E402
from transform.io import write_raw  # noqa: E402


def population_row() -> dict[str, str]:
    row = {
        "statistic_yyymm": "11507",
        "district_code": "65000010001",
        "site_id": "板橋區",
        "village": "甲里",
        "people_total": "100",
    }
    for age in range(18, 36):
        row[f"people_age_{age:03d}_m"] = "1" if age == 18 else "0"
        row[f"people_age_{age:03d}_f"] = "1" if age == 35 else "0"
    return row


class TestLegacyRawReplay(unittest.TestCase):
    def test_replay_enriches_curated_without_modifying_legacy_raw(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            raw_path = write_raw(
                {
                    "dataset": "population",
                    "period": "11507",
                    "fetched_at": "2026-09-12T02:00:00+00:00",
                    "records": [population_row()],
                },
                dataset="population",
                snapshot="11507_20260912T020000Z",
                output_dir=root / "input",
            )
            before_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            output_dir = root / "replay"

            exit_code = main(
                [
                    "--dataset",
                    "population",
                    "--input",
                    str(raw_path),
                    "--output-dir",
                    str(output_dir),
                    "--config-dir",
                    str(CONFIG_DIR),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                hashlib.sha256(raw_path.read_bytes()).hexdigest(), before_hash
            )
            curated = json.loads(
                (output_dir / "curated" / "population.json").read_text(encoding="utf-8")
            )
            self.assertEqual(curated["records"][0]["source"], "moi_household_registration")
            self.assertEqual(
                curated["records"][0]["source_url"],
                "https://www.ris.gov.tw/rs-opendata/",
            )
            self.assertFalse((output_dir / "raw").exists())

    def test_resume_enriches_a_legacy_raw_record_list(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            raw_path = root / "raw" / "population" / "11507_20260912T020000000000Z.json"
            raw_path.parent.mkdir(parents=True)
            raw_path.write_text(
                json.dumps([population_row()], ensure_ascii=False),
                encoding="utf-8",
            )

            unit = ExecutionUnit(
                spec=CollectorSpec(
                    dataset="population",
                    collect=lambda _period: self.fail("collector should not run"),
                    period_strategy=PeriodStrategy.MONTHLY,
                ),
                source_period="11507",
                output_key="11507",
            )

            status = _run_execution_unit(
                unit,
                output_dir=root,
                config_dir=CONFIG_DIR,
                strict=False,
                resume=True,
                force=False,
                period_partitioned=True,
            )

            self.assertEqual(status["status"], "ok")
            curated = json.loads(
                Path(status["curated_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(
                curated["records"][0]["source"], "moi_household_registration"
            )

    def test_checked_in_legacy_population_sample_replays_without_raw_changes(self):
        raw_path = PROJECT_DIR / "data-pipeline" / "data" / "raw" / "population" / "11202_20260901T155328601881Z.json"
        before_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()

        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            exit_code = main(
                [
                    "--dataset",
                    "population",
                    "--input",
                    str(raw_path),
                    "--output-dir",
                    str(output_dir),
                    "--config-dir",
                    str(CONFIG_DIR),
                ]
            )

            self.assertEqual(exit_code, 0)
            curated = json.loads(
                (output_dir / "curated" / "population.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                curated["records"][0]["source"], "moi_household_registration"
            )
            self.assertEqual(
                hashlib.sha256(raw_path.read_bytes()).hexdigest(), before_hash
            )


if __name__ == "__main__":
    unittest.main()
