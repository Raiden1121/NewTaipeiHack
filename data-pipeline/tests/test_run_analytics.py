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
    def test_all_metric_publishes_one_complete_snapshot(self):
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
                        "village_population_reference_period": "11507",
                        "budget_allocation_reference_year_roc": 116,
                        "election_years_roc": [103, 107, 111],
                        "service_radius_m": 2500,
                        "normalization": {"method": "p5_p95", "constant_value": 50},
                        "yoi_weights": {
                            "job": 0.25,
                            "salary": 0.25,
                            "talent": 0.05,
                            "housing": 0.25,
                            "transport": 0.2,
                        },
                    }
                ),
                encoding="utf-8",
            )
            generated_at = "2026-09-12T03:00:00+00:00"
            homepage = {
                "metric_id": "homepage",
                "generated_at": generated_at,
                "districts": [],
                "_quality": {"source_periods": {}},
            }
            results = {
                "employment": {"metric_id": "employment", "generated_at": generated_at, "_quality": {}},
                "fertility": {"metric_id": "fertility", "generated_at": generated_at, "_quality": {}},
                "participation": {
                    "metric_id": "youth_participation",
                    "generated_at": generated_at,
                    "_quality": {},
                },
                "policy_support": {
                    "metric_id": "policy_support",
                    "generated_at": generated_at,
                    "_quality": {},
                },
                "keyword_frequency": {
                    "metric_id": "youth_keyword_frequency",
                    "generated_at": generated_at,
                    "_quality": {},
                },
                "topic_weight": {
                    "metric_id": "youth_topic_weight",
                    "generated_at": generated_at,
                    "_quality": {},
                },
            }

            with patch.object(run_analytics, "HomepageInputResolver") as resolver:
                with patch.object(run_analytics, "load_topic_weights", return_value=object()):
                    with patch.object(run_analytics, "load_topic_rules", return_value=object()):
                        with patch.object(run_analytics, "load_keyword_config", return_value=object()):
                            with patch.object(run_analytics, "generate_homepage_data", return_value=homepage):
                                with patch.object(
                                    run_analytics,
                                    "generate_employment_data",
                                    return_value=results["employment"],
                                ):
                                    with patch.object(
                                        run_analytics,
                                        "generate_fertility_data",
                                        return_value=results["fertility"],
                                    ):
                                        with patch.object(
                                            run_analytics,
                                            "generate_youth_participation_data",
                                            return_value=results["participation"],
                                        ):
                                            with patch.object(
                                                run_analytics,
                                                "generate_policy_support_data",
                                                return_value=results["policy_support"],
                                            ):
                                                with patch.object(
                                                    run_analytics,
                                                    "calculate_youth_keyword_frequency",
                                                    return_value=results["keyword_frequency"],
                                                ):
                                                    with patch.object(
                                                        run_analytics,
                                                        "calculate_youth_topic_weights",
                                                        return_value=results["topic_weight"],
                                                    ):
                                                        with patch.object(run_analytics, "publish_homepage_snapshot") as publish:
                                                            for writer_name in (
                                                                "write_homepage_data",
                                                                "write_employment_data",
                                                                "write_fertility_data",
                                                                "write_youth_participation_data",
                                                                "write_policy_support_data",
                                                                "write_youth_keyword_frequency",
                                                                "write_youth_topic_weights",
                                                            ):
                                                                patcher = patch.object(
                                                                    run_analytics,
                                                                    writer_name,
                                                                    return_value=(root / f"{writer_name}.json", root / "quality.json"),
                                                                )
                                                                patcher.start()
                                                                self.addCleanup(patcher.stop)

                                                            data_loader = patch.object(
                                                                run_analytics,
                                                                "_load_indexed_dataset",
                                                                return_value=[],
                                                            )
                                                            data_loader.start()
                                                            self.addCleanup(data_loader.stop)

                                                            self.assertEqual(
                                                                run_analytics.main(
                                                                    [
                                                                        "--metric",
                                                                        "all",
                                                                        "--output-dir",
                                                                        str(root / "data"),
                                                                        "--config-dir",
                                                                        str(config_dir),
                                                                        "--publish",
                                                                        "--snapshot-id",
                                                                        "dev-full-20260912",
                                                                    ]
                                                                ),
                                                                0,
                                                            )

            resolver.from_paths.assert_called_once()
            publish.assert_called_once()
            self.assertEqual(
                set(publish.call_args.kwargs["analyses"]),
                {
                    "employment",
                    "fertility",
                    "participation",
                    "policy_support",
                    "keyword_frequency",
                    "topic_weight",
                },
            )
            self.assertEqual(publish.call_args.kwargs["snapshot_id"], "dev-full-20260912")

    def test_policy_support_branch_embeds_analysis_in_snapshot(self):
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
                        "village_population_reference_period": "11507",
                        "budget_allocation_reference_year_roc": 116,
                        "election_years_roc": [103, 107, 111],
                        "service_radius_m": 2500,
                        "normalization": {"method": "p5_p95", "constant_value": 50},
                        "yoi_weights": {"job": 0.25, "salary": 0.25, "talent": 0.05, "housing": 0.25, "transport": 0.2},
                    }
                ),
                encoding="utf-8",
            )
            homepage = {
                "metric_id": "homepage",
                "generated_at": "2026-09-11T09:39:13.190552+00:00",
                "districts": [],
                "_quality": {"source_periods": {}},
            }
            policy_support = {
                "metric_id": "policy_support",
                "generated_at": "2026-09-11T09:39:13.190552+00:00",
                "policyOutcomes": {"wageTrend": [], "populationTrend": []},
                "_quality": {"source_periods": {}, "coverage": {}},
            }
            with patch.object(run_analytics, "HomepageInputResolver"):
                with patch.object(run_analytics, "generate_homepage_data", return_value=homepage) as generate_homepage:
                    with patch.object(
                        run_analytics,
                        "generate_policy_support_data",
                        return_value=policy_support,
                    ) as generate:
                        with patch.object(
                            run_analytics,
                            "write_policy_support_data",
                            return_value=(root / "policy_support.json", root / "quality.json"),
                        ) as write:
                            with patch.object(run_analytics, "publish_homepage_snapshot") as publish:
                                self.assertEqual(
                                    run_analytics.main(
                                        [
                                            "--metric",
                                            "policy_support",
                                            "--output-dir",
                                            str(root / "data"),
                                            "--config-dir",
                                            str(config_dir),
                                            "--publish",
                                            "--snapshot-id",
                                            "dev-policy-support",
                                        ]
                                    ),
                                    0,
                                )
            generate.assert_called_once()
            write.assert_called_once()
            generate_homepage.assert_called_once()
            publish.assert_called_once()
            self.assertEqual(
                publish.call_args.kwargs["analyses"]["policy_support"]["metric_id"],
                "policy_support",
            )
            self.assertNotIn(
                "_quality", publish.call_args.kwargs["analyses"]["policy_support"]
            )

    def test_fertility_branch_embeds_analysis_in_snapshot(self):
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
                        "village_population_reference_period": "11507",
                        "budget_allocation_reference_year_roc": 116,
                        "election_years_roc": [103, 107, 111],
                        "service_radius_m": 2500,
                        "normalization": {"method": "p5_p95", "constant_value": 50},
                        "yoi_weights": {"job": 0.25, "salary": 0.25, "talent": 0.05, "housing": 0.25, "transport": 0.2},
                    }
                ),
                encoding="utf-8",
            )
            homepage = {
                "metric_id": "homepage",
                "generated_at": "2026-09-11T09:39:13.190552+00:00",
                "districts": [],
                "_quality": {"source_periods": {}},
            }
            fertility = {
                "metric_id": "fertility",
                "generated_at": "2026-09-11T09:39:13.190552+00:00",
                "districts": [],
                "_quality": {"source_periods": {}, "coverage": {}},
            }
            with patch.object(run_analytics, "HomepageInputResolver"):
                with patch.object(run_analytics, "generate_homepage_data", return_value=homepage):
                    with patch.object(
                        run_analytics,
                        "generate_fertility_data",
                        return_value=fertility,
                    ) as generate:
                        with patch.object(
                            run_analytics,
                            "write_fertility_data",
                            return_value=(root / "fertility.json", root / "quality.json"),
                        ) as write:
                            with patch.object(run_analytics, "publish_homepage_snapshot") as publish:
                                self.assertEqual(
                                    run_analytics.main(
                                        [
                                            "--metric",
                                            "fertility",
                                            "--output-dir",
                                            str(root / "data"),
                                            "--config-dir",
                                            str(config_dir),
                                            "--publish",
                                            "--snapshot-id",
                                            "dev-fertility",
                                        ]
                                    ),
                                    0,
                                )
            generate.assert_called_once()
            write.assert_called_once()
            publish.assert_called_once()
            self.assertEqual(
                publish.call_args.kwargs["analyses"]["fertility"]["metric_id"],
                "fertility",
            )
            self.assertNotIn("_quality", publish.call_args.kwargs["analyses"]["fertility"])

    def test_youth_participation_branch_embeds_analysis_in_snapshot(self):
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
                        "village_population_reference_period": "11507",
                        "budget_allocation_reference_year_roc": 116,
                        "election_years_roc": [103, 107, 111],
                        "service_radius_m": 2500,
                        "normalization": {"method": "p5_p95", "constant_value": 50},
                        "yoi_weights": {"job": 0.25, "salary": 0.25, "talent": 0.05, "housing": 0.25, "transport": 0.2},
                    }
                ),
                encoding="utf-8",
            )
            homepage = {
                "metric_id": "homepage",
                "generated_at": "2026-09-11T09:39:13.190552+00:00",
                "districts": [],
                "_quality": {"source_periods": {}},
            }
            participation = {
                "metric_id": "youth_participation",
                "generated_at": "2026-09-11T09:39:13.190552+00:00",
                "elections": {},
                "_quality": {"source_periods": {}, "coverage": {}},
            }
            with patch.object(run_analytics, "HomepageInputResolver"):
                with patch.object(run_analytics, "generate_homepage_data", return_value=homepage):
                    with patch.object(
                        run_analytics,
                        "generate_youth_participation_data",
                        return_value=participation,
                    ) as generate:
                        with patch.object(
                            run_analytics,
                            "write_youth_participation_data",
                            return_value=(root / "participation.json", root / "quality.json"),
                        ) as write:
                            with patch.object(run_analytics, "publish_homepage_snapshot") as publish:
                                self.assertEqual(
                                    run_analytics.main(
                                        [
                                            "--metric",
                                            "youth_participation",
                                            "--output-dir",
                                            str(root / "data"),
                                            "--config-dir",
                                            str(config_dir),
                                            "--publish",
                                            "--snapshot-id",
                                            "dev-youth-participation",
                                        ]
                                    ),
                                    0,
                                )
            generate.assert_called_once()
            write.assert_called_once()
            publish.assert_called_once()
            self.assertEqual(
                publish.call_args.kwargs["analyses"]["participation"]["metric_id"],
                "youth_participation",
            )
            self.assertNotIn("_quality", publish.call_args.kwargs["analyses"]["participation"])

    def test_employment_branch_writes_and_publishes_analysis(self):
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
                        "village_population_reference_period": "11507",
                        "budget_allocation_reference_year_roc": 116,
                        "election_years_roc": [103, 107, 111],
                        "service_radius_m": 2500,
                        "normalization": {"method": "p5_p95", "constant_value": 50},
                        "yoi_weights": {"job": 0.25, "salary": 0.25, "talent": 0.05, "housing": 0.25, "transport": 0.2},
                    }
                ),
                encoding="utf-8",
            )
            homepage = {
                "metric_id": "homepage",
                "generated_at": "2026-09-11T09:39:13.190552+00:00",
                "districts": [],
                "_quality": {"source_periods": {}},
            }
            employment = {
                "metric_id": "employment",
                "generated_at": "2026-09-11T09:39:13.190552+00:00",
                "districts": [],
                "_quality": {"source_periods": {}, "coverage": {}},
            }
            with patch.object(run_analytics, "HomepageInputResolver") as resolver:
                with patch.object(run_analytics, "generate_homepage_data", return_value=homepage):
                    with patch.object(run_analytics, "generate_employment_data", return_value=employment) as generate:
                        with patch.object(
                            run_analytics,
                            "write_employment_data",
                            return_value=(root / "employment.json", root / "employment-quality.json"),
                        ) as write:
                            with patch.object(run_analytics, "publish_homepage_snapshot") as publish:
                                self.assertEqual(
                                    run_analytics.main(
                                        [
                                            "--metric",
                                            "employment",
                                            "--output-dir",
                                            str(root / "data"),
                                            "--config-dir",
                                            str(config_dir),
                                            "--publish",
                                            "--snapshot-id",
                                            "dev-employment",
                                        ]
                                    ),
                                    0,
                                )
            resolver.from_paths.assert_called_once()
            generate.assert_called_once()
            write.assert_called_once()
            publish.assert_called_once()
            self.assertEqual(publish.call_args.kwargs["snapshot_id"], "dev-employment")
            self.assertFalse(publish.call_args.kwargs["update_current"])
            self.assertEqual(publish.call_args.kwargs["analyses"]["employment"]["metric_id"], "employment")
            self.assertNotIn("_quality", publish.call_args.kwargs["analyses"]["employment"])

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
                        "village_population_reference_period": "11507",
                        "budget_allocation_reference_year_roc": 116,
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
