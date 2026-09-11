import math
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.homepage_math import (  # noqa: E402
    calculate_quartile_risk,
    normalize_p5_p95,
    shannon_entropy,
    weighted_score,
)


class TestHomepageMath(unittest.TestCase):
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
