import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from orchestration.contracts import PeriodStrategy
from orchestration.retention import (
    build_retention_window,
    period_is_retained,
    prune_local_data,
)


class RetentionWindowTests(unittest.TestCase):
    def test_window_keeps_five_completed_years_plus_current_year(self):
        window = build_retention_window("11509", years=5)

        self.assertEqual(window.monthly_cutoff, "11001")
        self.assertEqual(window.annual_cutoff, 110)
        self.assertFalse(
            period_is_retained("10912", PeriodStrategy.MONTHLY, window)
        )
        self.assertTrue(
            period_is_retained("11001", PeriodStrategy.MONTHLY, window)
        )
        self.assertFalse(period_is_retained("109", PeriodStrategy.ANNUAL, window))
        self.assertTrue(period_is_retained("110", PeriodStrategy.ANNUAL, window))
        self.assertTrue(period_is_retained("115", PeriodStrategy.ANNUAL, window))

    def test_rejects_non_positive_retention_years(self):
        with self.assertRaises(ValueError):
            build_retention_window("11509", years=0)


class LocalRetentionTests(unittest.TestCase):
    def _write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_prunes_old_partitioned_files_and_index_entries(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            strategies = {"population": PeriodStrategy.MONTHLY}
            for category in ("raw", "curated", "quality", "quarantine"):
                if category == "raw":
                    old_path = root / category / "population" / "10912_20260101T000000Z.json"
                    new_path = root / category / "population" / "11001_20260101T000000Z.json"
                    self._write_json(old_path, {"period": "10912", "records": []})
                    self._write_json(new_path, {"period": "11001", "records": []})
                else:
                    old_path = root / category / "population" / "10912.json"
                    new_path = root / category / "population" / "11001.json"
                    self._write_json(old_path, {"period": "10912"})
                    self._write_json(new_path, {"period": "11001"})

            self._write_json(
                root / "quality" / "dataset_index.json",
                {
                    "schema_version": 1,
                    "datasets": {
                        "population": [
                            {
                                "output_key": "10912",
                                "path": "curated/population/10912.json",
                                "period_strategy": "monthly",
                            },
                            {
                                "output_key": "11001",
                                "path": "curated/population/11001.json",
                                "period_strategy": "monthly",
                            },
                        ]
                    },
                },
            )

            report = prune_local_data(
                root,
                current_period="11509",
                period_strategies=strategies,
            )

            self.assertFalse((root / "curated/population/10912.json").exists())
            self.assertTrue((root / "curated/population/11001.json").exists())
            self.assertFalse(
                (root / "raw/population/10912_20260101T000000Z.json").exists()
            )
            self.assertTrue(
                (root / "raw/population/11001_20260101T000000Z.json").exists()
            )
            self.assertIn("curated/population/10912.json", report["deleted_paths"])

            index = json.loads(
                (root / "quality/dataset_index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [entry["output_key"] for entry in index["datasets"]["population"]],
                ["11001"],
            )

    def test_filters_old_records_inside_all_available_json(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            strategies = {"youth_budgets": PeriodStrategy.ALL_AVAILABLE}
            records = [
                {"budget_year_roc": "109", "value": 109},
                {"budget_year_roc": "110", "value": 110},
                {"budget_year_roc": "111", "value": 111},
                {"budget_year_roc": "115", "value": 115},
                {"budget_year_roc": "116", "value": 116},
            ]
            curated_path = root / "curated/youth_budgets/all.json"
            raw_path = root / "raw/youth_budgets/11509_20260909T000000Z.json"
            self._write_json(curated_path, {"records": records})
            self._write_json(raw_path, {"records": records, "documents": records})

            report = prune_local_data(
                root,
                current_period="11509",
                period_strategies=strategies,
            )

            curated = json.loads(curated_path.read_text(encoding="utf-8"))
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [record["budget_year_roc"] for record in curated["records"]],
                ["110", "111", "115", "116"],
            )
            self.assertEqual(
                [record["budget_year_roc"] for record in raw["documents"]],
                ["110", "111", "115", "116"],
            )
            self.assertIn("curated/youth_budgets/all.json", report["rewritten_paths"])

    def test_preserves_records_without_a_recognizable_period(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "curated/youth_budgets/all.json"
            payload = {"records": [{"value": 1, "note": "unknown period"}]}
            self._write_json(path, payload)

            prune_local_data(
                root,
                current_period="11509",
                period_strategies={"youth_budgets": PeriodStrategy.ALL_AVAILABLE},
            )

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                payload,
            )


if __name__ == "__main__":
    unittest.main()
