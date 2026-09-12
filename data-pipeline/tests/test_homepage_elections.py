import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.elections import calculate_youth_candidacy  # noqa: E402


class TestHomepageElections(unittest.TestCase):
    def test_t1_keeps_election_grain_and_v1_uses_district_grain(self):
        records = [
            {"election_type": "city_councilor", "source_code": "T1", "election_roc_year": "111", "election_district_code": "01", "election_district_name": "新北市第01選區", "election_date": "2022-11-26", "birth_date": "1990-01-01", "elected": True},
            {"election_type": "borough_chief", "source_code": "V1", "election_roc_year": "111", "district_id": "65000010", "district_name": "板橋區", "election_date": "2022-11-26", "birth_year_roc": "080", "elected": False},
        ]
        population = [
            {"metric_id": "youth_18_35_total", "district_id": "65000010", "period_start": "2022-12-01", "period_end": "2022-12-31", "value": 100},
            {"metric_id": "youth_18_35_total", "district_id": "65000020", "period_start": "2022-12-01", "period_end": "2022-12-31", "value": 100},
        ]

        result = calculate_youth_candidacy(records, population, election_years_roc=[111])

        self.assertEqual(result["city_councilor_t1"][0]["district_id"], None)
        self.assertEqual(result["city_councilor_t1"][0]["election_district_code"], "01")
        self.assertEqual(result["borough_chief_v1"][0]["district_id"], "65000010")
        self.assertEqual(result["borough_chief_v1"][0]["youth_candidate_count"], 1)
        self.assertEqual(result["borough_chief_v1"][0]["youth_candidacy_rate"], 1000)


if __name__ == "__main__":
    unittest.main()
