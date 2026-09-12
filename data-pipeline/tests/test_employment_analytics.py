import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
TESTS_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from analytics.config import load_homepage_analytics_config  # noqa: E402
from analytics.employment import generate_employment_data, write_employment_data  # noqa: E402
from analytics.io import CuratedSlice  # noqa: E402
from test_homepage_analytics import FakeHomepageResolver  # noqa: E402


class TestEmploymentAnalytics(unittest.TestCase):
    def setUp(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        self.config = load_homepage_analytics_config(config_path)

    def test_generates_29_district_contract_and_scatter_regressions(self):
        result = generate_employment_data(
            resolver=FakeHomepageResolver(),
            config=self.config,
        )

        self.assertEqual(result["metric_id"], "employment")
        self.assertEqual(len(result["districts"]), 29)
        first = result["districts"][0]
        self.assertEqual(first["score_job"], first["yoiComponents"]["job"])
        self.assertEqual(first["score_salary"], first["yoiComponents"]["salary"])
        self.assertEqual(first["score_talent"], first["yoiComponents"]["talent"])
        self.assertEqual(first["score_housing"], first["yoiComponents"]["housing"])
        self.assertEqual(first["score_transport"], first["yoiComponents"]["transport"])
        self.assertAlmostEqual(first["knowledge_job_ratio"], 100.0)
        self.assertEqual(result["districts"][1]["knowledge_job_ratio"], 0.0)
        self.assertEqual(first["estimated_monthly_wage"], first["estimated_wage"] / 12)

        for plot_key in ("knowledge_job_vs_estimated_wage", "monthly_wage_vs_house_price"):
            plot = result["scatter"][plot_key]
            self.assertEqual(len(plot["points"]), 29)
            self.assertEqual(plot["regression"]["sample_size"], 29)
            self.assertIsNotNone(plot["regression"]["slope"])
            self.assertIsNotNone(plot["regression"]["intercept"])
            self.assertIsNotNone(plot["regression"]["r_squared"])

        def assert_no_raw(value):
            if isinstance(value, dict):
                self.assertNotIn("raw_record", value)
                self.assertNotIn("raw_records", value)
                for item in value.values():
                    assert_no_raw(item)
            elif isinstance(value, list):
                for item in value:
                    assert_no_raw(item)

        assert_no_raw(result)

    def test_writes_public_data_and_quality_separately(self):
        result = generate_employment_data(
            resolver=FakeHomepageResolver(),
            config=self.config,
        )

        with tempfile.TemporaryDirectory() as tempdir:
            output_path, quality_path = write_employment_data(result, output_dir=tempdir)
            self.assertEqual(output_path, Path(tempdir) / "analytics" / "employment" / "all.json")
            self.assertEqual(quality_path, Path(tempdir) / "quality" / "analytics_employment.json")
            json.loads(output_path.read_text(encoding="utf-8"))
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            self.assertEqual(quality["metric_id"], "employment")
            self.assertIn("job_vacancies", quality["inputs"])

    def test_missing_vacancies_are_null_and_excluded_from_ols(self):
        class NoVacancyResolver(FakeHomepageResolver):
            def latest(self, dataset):
                if dataset == "job_vacancies":
                    return CuratedSlice(
                        dataset,
                        "snapshot",
                        ("11509",),
                        (),
                        ("curated/job_vacancies/latest.json",),
                    )
                return super().latest(dataset)

        result = generate_employment_data(
            resolver=NoVacancyResolver(),
            config=self.config,
        )

        self.assertTrue(all(row["knowledge_job_ratio"] is None for row in result["districts"]))
        regression = result["scatter"]["knowledge_job_vs_estimated_wage"]["regression"]
        self.assertEqual(regression["sample_size"], 0)
        self.assertIsNone(regression["slope"])


if __name__ == "__main__":
    unittest.main()
