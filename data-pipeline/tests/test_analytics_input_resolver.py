import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.config import load_homepage_analytics_config  # noqa: E402
from analytics.io import (  # noqa: E402
    load_curated_period,
    load_curated_periods,
    load_latest_snapshot,
)


class TestAnalyticsInputResolver(unittest.TestCase):
    def test_loads_explicit_period_and_reports_missing_path(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = root / "curated" / "population" / "114.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"records": [{"period": "114"}]}), encoding="utf-8")

            selected = load_curated_period("population", "114", output_dir=root)

            self.assertEqual(selected.source_periods, ("114",))
            self.assertEqual(selected.period_type, "annual")
            self.assertEqual(selected.records, ({"period": "114"},))
            with self.assertRaisesRegex(ValueError, r"population.*115.*curated"):
                load_curated_period("population", "115", output_dir=root)

    def test_rejects_path_traversal_and_preserves_period_order(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            for period in ("110", "111"):
                path = root / "curated" / "population" / f"{period}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"records": [{"period": period}]}), encoding="utf-8")

            selected = load_curated_periods("population", ("111", "110"), output_dir=root)

            self.assertEqual(selected.source_periods, ("111", "110"))
            self.assertEqual([row["period"] for row in selected.records], ["111", "110"])
            with self.assertRaises(ValueError):
                load_curated_period("population", "../secret", output_dir=root)
            with self.assertRaises(ValueError):
                load_curated_period("../population", "110", output_dir=root)

    def test_latest_snapshot_uses_index_declared_path_only(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            curated = root / "curated" / "rentals" / "latest.json"
            curated.parent.mkdir(parents=True)
            curated.write_text(json.dumps({"records": [{"district_id": "65000010"}]}), encoding="utf-8")
            index = root / "quality" / "dataset_index.json"
            index.parent.mkdir(parents=True)
            index.write_text(
                json.dumps(
                    {
                        "datasets": {
                            "rentals": [
                                {
                                    "output_key": "latest",
                                    "path": "curated/rentals/latest.json",
                                    "source_period": "11509",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            selected = load_latest_snapshot("rentals", output_dir=root)

            self.assertEqual(selected.period_type, "snapshot")
            self.assertEqual(selected.source_periods, ("11509",))
            self.assertEqual(selected.paths, ("curated/rentals/latest.json",))
            self.assertEqual(len(selected.records), 1)

    def test_loads_homepage_policy(self):
        config = load_homepage_analytics_config(CONFIG_DIR / "homepage_analytics.json")

        self.assertEqual(config.annual_years_roc, (110, 111, 112, 113, 114))
        self.assertEqual(config.population_reference_year_roc, 114)
        self.assertEqual(config.village_population_reference_period, "11507")
        self.assertEqual(config.budget_allocation_reference_year_roc, 116)
        self.assertEqual(config.election_years_roc, (103, 107, 111))
        self.assertEqual(config.service_radius_m, 2500)
        self.assertEqual(config.normalization["method"], "min_max")
        self.assertEqual(config.yoi_weights["talent"], 0.15)
        self.assertEqual(config.yoi_weights["housing"], 0.2)
        self.assertEqual(config.yoi_weights["transport"], 0.15)


if __name__ == "__main__":
    unittest.main()
