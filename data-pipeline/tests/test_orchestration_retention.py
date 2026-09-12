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

    def test_preserves_protected_historical_population_partition(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            strategies = {"population": PeriodStrategy.MONTHLY}
            for category in ("raw", "curated", "quality", "quarantine"):
                if category == "raw":
                    protected_path = root / category / "population" / "10312_20260912T000000Z.json"
                    self._write_json(protected_path, {"period": "10312", "records": []})
                else:
                    protected_path = root / category / "population" / "10312.json"
                    self._write_json(protected_path, {"period": "10312"})
            self._write_json(
                root / "quality" / "collection" / "10312.json",
                {"period": "10312"},
            )
            self._write_json(
                root / "quality" / "dataset_index.json",
                {
                    "schema_version": 1,
                    "datasets": {
                        "population": [
                            {
                                "output_key": "10312",
                                "path": "curated/population/10312.json",
                                "period_strategy": "monthly",
                            }
                        ]
                    },
                },
            )

            report = prune_local_data(
                root,
                current_period="11509",
                period_strategies=strategies,
                protected_periods={"population": {"10312"}},
            )

            self.assertTrue((root / "curated/population/10312.json").exists())
            self.assertTrue((root / "quality/population/10312.json").exists())
            self.assertTrue((root / "quarantine/population/10312.json").exists())
            self.assertTrue(
                (root / "raw/population/10312_20260912T000000Z.json").exists()
            )
            self.assertTrue((root / "quality/collection/10312.json").exists())
            self.assertNotIn("curated/population/10312.json", report["deleted_paths"])
            index = json.loads(
                (root / "quality/dataset_index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                index["datasets"]["population"][0]["output_key"], "10312"
            )

    def test_keeps_unknown_index_shapes_when_rewriting(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            strategies = {"population": PeriodStrategy.MONTHLY}
            self._write_json(
                root / "curated" / "population" / "10912.json", {"period": "10912"}
            )
            self._write_json(
                root / "quality" / "dataset_index.json",
                {
                    "schema_version": 2,
                    "datasets": {
                        # Stale partition: forces the index to be rewritten.
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
                        ],
                        # Shapes retention does not understand must survive.
                        "join_proposals": {
                            "output_key": "all",
                            "path": "curated/join_proposals/all.json",
                        },
                        "youth_council_minutes": None,
                    },
                },
            )

            prune_local_data(
                root,
                current_period="11509",
                period_strategies=strategies,
            )

            index = json.loads(
                (root / "quality/dataset_index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [entry["output_key"] for entry in index["datasets"]["population"]],
                ["11001"],
            )
            self.assertEqual(
                index["datasets"]["join_proposals"],
                {
                    "output_key": "all",
                    "path": "curated/join_proposals/all.json",
                },
            )
            self.assertIn("youth_council_minutes", index["datasets"])
            self.assertIsNone(index["datasets"]["youth_council_minutes"])

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

    def test_filters_year_roc_records_inside_all_available_json(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            records = [
                {"year_roc": "109", "value": 109},
                {"year_roc": "110", "value": 110},
                {"year_roc": "115", "value": 115},
            ]
            path = root / "curated/join_proposals/all.json"
            raw_path = root / "raw/join_proposals/11509_20260909T000000Z.json"
            self._write_json(path, {"records": records})
            self._write_json(raw_path, {"records": records, "documents": records})

            prune_local_data(
                root,
                current_period="11509",
                period_strategies={"join_proposals": PeriodStrategy.ALL_AVAILABLE},
            )

            self.assertEqual(
                [row["year_roc"] for row in json.loads(path.read_text(encoding="utf-8"))["records"]],
                ["110", "115"],
            )
            self.assertEqual(
                [row["year_roc"] for row in json.loads(raw_path.read_text(encoding="utf-8"))["records"]],
                ["110", "115"],
            )

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

    def test_preserves_selected_election_terms_in_all_available_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            records = [
                {
                    "election_term": "2014",
                    "period_start": "2014-11-29",
                    "period_type": "snapshot",
                },
                {
                    "election_term": "2022",
                    "period_start": "2022-11-26",
                    "period_type": "snapshot",
                },
            ]
            path = root / "curated/elections/all.json"
            raw_path = root / "raw/elections/11509_20260909T000000Z.json"
            self._write_json(path, {"records": records})
            self._write_json(raw_path, {"records": records, "documents": records})

            report = prune_local_data(
                root,
                current_period="11509",
                period_strategies={"elections": PeriodStrategy.ALL_AVAILABLE},
            )

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["records"], records
            )
            self.assertEqual(
                json.loads(raw_path.read_text(encoding="utf-8"))["documents"], records
            )
            self.assertNotIn("curated/elections/all.json", report["rewritten_paths"])


if __name__ == "__main__":
    unittest.main()
