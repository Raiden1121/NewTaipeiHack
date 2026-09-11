import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import run_analytics  # noqa: E402


class TestRunAnalytics(unittest.TestCase):
    def test_homepage_branch_does_not_load_text_analytics_inputs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            config_dir = root / "config"
            config_dir.mkdir()
            (config_dir / "homepage_analytics.json").write_text(
                json.dumps(
                    {
                        "version": "1",
                        "annual_years_roc": [110, 111, 112, 113, 114],
                        "population_reference_year_roc": 114,
                        "election_years_roc": [103, 107, 111],
                        "service_radius_m": 2500,
                        "normalization": {"method": "p5_p95", "constant_value": 50},
                        "yoi_weights": {"job": 0.25, "salary": 0.25, "talent": 0.05, "housing": 0.25, "transport": 0.2},
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(run_analytics, "HomepageInputResolver") as resolver:
                with patch.object(run_analytics, "generate_homepage_data", return_value={"_quality": {}}) as generate:
                    with patch.object(run_analytics, "load_curated_dataset", side_effect=AssertionError("text inputs must not load")):
                        self.assertEqual(
                            run_analytics.main(
                                [
                                    "--metric",
                                    "homepage",
                                    "--output-dir",
                                    str(root / "data"),
                                    "--config-dir",
                                    str(config_dir),
                                ]
                            ),
                            0,
                        )
            resolver.from_paths.assert_called_once()
            generate.assert_called_once()
            self.assertTrue((root / "data" / "analytics" / "homepage" / "all.json").is_file())


if __name__ == "__main__":
    unittest.main()
