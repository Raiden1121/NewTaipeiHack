import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.service_coverage import calculate_service_coverage  # noqa: E402


class TestServiceCoverage(unittest.TestCase):
    def test_union_buffer_allocates_youth_by_intersection_area_and_excludes_missing_point(self):
        boundaries = [
            {
                "village_code": "v1",
                "district_id": "d1",
                "district_name": "一區",
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]]},
            },
            {
                "village_code": "v2",
                "district_id": "d1",
                "district_name": "一區",
                "geometry": {"type": "Polygon", "coordinates": [[[100, 0], [200, 0], [200, 100], [100, 100], [100, 0]]]},
            },
        ]
        population = [
            {"village_code": "v1", "district_id": "d1", "district_name": "一區", "youth_18_35_total": 100},
            {"village_code": "v2", "district_id": "d1", "district_name": "一區", "youth_18_35_total": 100},
        ]
        points = [
            {"point_id": "p1", "geocode_status": "matched", "x_3826": 50, "y_3826": 50},
            {"point_id": "p2", "geocode_status": "matched", "x_3826": 50, "y_3826": 50},
            {"point_id": "p3", "geocode_status": "excluded_no_verified_coordinate", "x_3826": None, "y_3826": None},
        ]

        result = calculate_service_coverage(points, boundaries, population, radius_m=20)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["verified_point_count"], 2)
        self.assertEqual(result["excluded_point_count"], 1)
        self.assertEqual(result["joined_village_count"], 2)
        self.assertGreater(result["value"], 0)
        self.assertLess(result["value"], 100)
        self.assertAlmostEqual(result["districts"][0]["covered_youth"], result["villages"][0]["covered_youth"])

    def test_no_verified_point_is_unavailable_not_zero(self):
        result = calculate_service_coverage(
            [{"point_id": "p1", "geocode_status": "excluded_no_verified_coordinate"}],
            [],
            [],
        )

        self.assertIsNone(result["value"])
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("no_verified_service_points", result["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
