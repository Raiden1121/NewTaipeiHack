import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_PATH = PROJECT_DIR / "data-pipeline" / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.geography import DistrictResolver  # noqa: E402
from transform.housing import transform_house_prices, transform_rentals  # noqa: E402


class TestTransformHousing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_house_price_keeps_transaction_row_and_explicit_units(self):
        raw = {
            "district": "板橋區",
            "rps07_yyymmddroc": "1140521",
            "rps21_amountsunitdollars": "12,000,000",
            "rps15_area": "30.5",
            "rps22_amountsunitdollars": "393443",
            "transaction_date": "1140521",
            "total_price": 12000000,
            "building_area_sqm": 30.5,
            "price_per_sqm": 393443,
            "price_per_ping": 1300640,
            "transaction_type": "房地(土地+建物)",
            "snapshot_fetched_at": "2026-09-01T00:00:00+00:00",
        }

        result = transform_house_prices([raw], resolver=self.resolver)

        record = result.records[0]
        self.assertEqual(record["period_start"], "2025-05-21")
        self.assertEqual(record["total_price"], 12000000)
        self.assertEqual(record["total_price_unit"], "TWD")
        self.assertEqual(record["building_area_unit"], "square_metre")
        self.assertEqual(record["price_per_ping_unit"], "TWD_per_ping")
        self.assertEqual(record["raw_record"], raw)
        self.assertEqual(record["age_scope"], "not_age_specific")
        self.assertEqual(record["youth_eligibility"], "context_only")

    def test_rental_missing_values_stay_null_without_overwriting_raw_value(self):
        raw = {
            "district": "新北市中和區",
            "rps07_yyymmddroc": "1140601",
            "rps22_amountsunitdollars": "面議",
            "rental_date": "1140601",
            "rent_total": None,
            "building_area_sqm": 20,
            "rent_per_sqm": None,
            "rent_per_sqm_source": "missing",
            "rent_per_ping": None,
            "rental_type": "整戶",
            "snapshot_fetched_at": "2026-09-01T00:00:00+00:00",
        }

        result = transform_rentals([raw], resolver=self.resolver)

        record = result.records[0]
        self.assertIsNone(record["rent_total"])
        self.assertIsNone(record["rent_per_sqm"])
        self.assertEqual(record["raw_record"]["rps22_amountsunitdollars"], "面議")
        self.assertEqual(record["rent_total_unit"], "TWD")
        self.assertGreaterEqual(result.quality["missing_value_count"], 2)


if __name__ == "__main__":
    unittest.main()
