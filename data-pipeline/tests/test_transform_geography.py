import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_PATH = PROJECT_DIR / "data-pipeline" / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.geography import DistrictResolver  # noqa: E402


class TestDistrictResolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_contains_all_29_map_districts(self):
        self.assertEqual(len(self.resolver.districts), 29)
        self.assertEqual(
            {row["district_id"] for row in self.resolver.districts},
            {
                "65000010", "65000020", "65000030", "65000040", "65000050",
                "65000060", "65000070", "65000080", "65000090", "65000100",
                "65000110", "65000120", "65000130", "65000140", "65000150",
                "65000160", "65000170", "65000180", "65000190", "65000200",
                "65000210", "65000220", "65000230", "65000240", "65000250",
                "65000260", "65000270", "65000280", "65000290",
            },
        )

    def test_resolves_canonical_names_and_explicit_aliases(self):
        expected = ("65000010", "板橋區")
        self.assertEqual(self.resolver.resolve_name("板橋區"), expected)
        self.assertEqual(self.resolver.resolve_name("新北市板橋區"), expected)
        self.assertEqual(self.resolver.resolve_name("臺北縣板橋市"), expected)
        self.assertIsNone(self.resolver.resolve_name("未知區"))

    def test_resolves_verified_official_and_postal_codes(self):
        expected = ("65000010", "板橋區")
        self.assertEqual(self.resolver.resolve_code("65000010"), expected)
        self.assertEqual(self.resolver.resolve_code("65000010001"), expected)
        self.assertEqual(self.resolver.resolve_zip(220), expected)
        self.assertIsNone(self.resolver.resolve_code("65099999"))
        self.assertIsNone(self.resolver.resolve_zip("999"))

    def test_resolves_only_points_inside_one_boundary(self):
        self.assertEqual(
            self.resolver.resolve_point(25.0114, 121.4618),
            ("65000010", "板橋區"),
        )
        self.assertIsNone(self.resolver.resolve_point(24.0, 120.0))
        self.assertIsNone(self.resolver.resolve_point(float("nan"), 121.5))


if __name__ == "__main__":
    unittest.main()
