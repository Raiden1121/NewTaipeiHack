import math
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.homepage_math import (  # noqa: E402
    calculate_ols_regression,
    calculate_quartile_risk,
    normalize_minmax,
    normalize_p5_p95,
    shannon_entropy,
    weighted_score,
)


class TestHomepageMath(unittest.TestCase):
    def test_ols_regression_returns_line_and_fit(self):
        result = calculate_ols_regression([(1, 3), (2, 5), (3, 7)])

        self.assertEqual(result["method"], "ols")
        self.assertEqual(result["sample_size"], 3)
        self.assertAlmostEqual(result["slope"], 2)
        self.assertAlmostEqual(result["intercept"], 1)
        self.assertAlmostEqual(result["r_squared"], 1)

    def test_ols_regression_ignores_missing_non_finite_and_handles_degenerate_inputs(self):
        result = calculate_ols_regression(
            [(1, 3), (2, None), (None, 5), (float("nan"), 7), (3, float("inf")), (3, 7)]
        )
        self.assertEqual(result["sample_size"], 2)
        self.assertAlmostEqual(result["slope"], 2)
        self.assertAlmostEqual(result["intercept"], 1)
        self.assertAlmostEqual(result["r_squared"], 1)

        for points in ([], [(1, 2)], [(1, 2), (1, 3)]):
            degenerate = calculate_ols_regression(points)
            self.assertIsNone(degenerate["slope"])
            self.assertIsNone(degenerate["intercept"])
            self.assertIsNone(degenerate["r_squared"])

        constant_y = calculate_ols_regression([(1, 2), (2, 2), (3, 2)])
        self.assertAlmostEqual(constant_y["slope"], 0)
        self.assertAlmostEqual(constant_y["intercept"], 2)
        self.assertIsNone(constant_y["r_squared"])

    def test_p5_p95_clips_inverse_and_preserves_missing(self):
        values = {"a": 0, "b": 10, "c": 20, "d": 30, "e": 100, "missing": None}
        normalized = normalize_p5_p95(values)
        inverse = normalize_p5_p95(values, inverse=True)

        self.assertEqual(normalized["missing"], None)
        self.assertEqual(inverse["a"], 100 - normalized["a"])
        self.assertGreaterEqual(normalized["a"], 0)
        self.assertLessEqual(normalized["e"], 100)
        self.assertFalse(any(math.isnan(value) for value in normalized.values() if value is not None))
        self.assertEqual(normalize_p5_p95({"a": 3, "b": 3})["a"], 50)

    def test_minmax_does_not_clip_percentiles_and_preserves_missing(self):
        values = {str(value): value for value in range(101)}
        values["missing"] = None

        normalized = normalize_minmax(values)
        inverse = normalize_minmax(values, inverse=True)

        self.assertIsNone(normalized["missing"])
        self.assertAlmostEqual(normalized["1"], 1.0)
        self.assertAlmostEqual(normalized["99"], 99.0)
        self.assertAlmostEqual(inverse["1"], 99.0)
        self.assertAlmostEqual(inverse["99"], 1.0)
        self.assertEqual(normalize_minmax({"a": 3, "b": 3})["a"], 50)

    def test_entropy_and_quartile_risk(self):
        self.assertEqual(shannon_entropy({"only": 10}), 0)
        self.assertAlmostEqual(shannon_entropy({"a": 1, "b": 1}), 1)
        risk = calculate_quartile_risk({"a": 1, "b": 2, "c": 3, "d": 4})
        self.assertEqual(risk["a"], "high")
        self.assertEqual(risk["d"], "low")
        self.assertEqual(risk["b"], "medium")

    def test_weighted_score_ignores_unavailable_parts_without_nan(self):
        self.assertEqual(weighted_score({"a": 80, "b": 40}, {"a": 0.75, "b": 0.25}), 70)
        self.assertEqual(weighted_score({"a": None}, {"a": 1}), None)


if __name__ == "__main__":
    unittest.main()
