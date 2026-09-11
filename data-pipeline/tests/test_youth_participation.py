import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.youth_participation import (  # noqa: E402
    calculate_grant_metrics,
    calculate_proposal_funnel,
    calculate_youth_borough_metrics,
)
from analytics.elections import calculate_youth_candidacy  # noqa: E402


class TestYouthParticipation(unittest.TestCase):
    def test_t1_missing_historical_population_does_not_reuse_latest_year(self):
        elections = [
            {
                "source_code": "T1",
                "election_type": "city_councilor",
                "election_roc_year": str(year),
                "election_district_code": "01",
                "election_district_name": "新北市第01選區",
                "election_date": f"{year + 1911}-11-01",
                "birth_date": "1990-01-01",
            }
            for year in (103, 107, 111)
        ]
        population = [
            {
                "metric_id": "youth_18_35_total",
                "district_id": "65000010",
                "period_start": "2022-11-01",
                "period_end": "2022-11-30",
                "value": 100,
            }
        ]

        result = calculate_youth_candidacy(
            elections, population, election_years_roc=[103, 107, 111]
        )
        denominator_by_year = {
            row["election_year_roc"]: row["youth_population_18_35"]
            for row in result["city_councilor_t1"]
        }

        self.assertIsNone(denominator_by_year[103])
        self.assertIsNone(denominator_by_year[107])
        self.assertEqual(denominator_by_year[111], 100)

    def test_v1_borough_ratio_and_yrr_use_population_proxy(self):
        elections = [
            {
                "source_code": "V1",
                "election_type": "borough_chief",
                "election_roc_year": "111",
                "district_id": "65000010",
                "district_name": "板橋區",
                "election_date": "2022-11-26",
                "birth_date": "1990-01-01",
                "elected": True,
            },
            {
                "source_code": "V1",
                "election_type": "borough_chief",
                "election_roc_year": "111",
                "district_id": "65000010",
                "district_name": "板橋區",
                "election_date": "2022-11-26",
                "birth_date": "1960-01-01",
                "elected": True,
            },
        ]
        population = [
            {
                "metric_id": "youth_18_35_total",
                "district_id": "65000010",
                "period_start": "2022-11-01",
                "period_end": "2022-11-30",
                "value": 100,
            },
            {
                "metric_id": "people_total",
                "district_id": "65000010",
                "period_start": "2022-11-01",
                "period_end": "2022-11-30",
                "value": 1000,
            },
        ]

        result = calculate_youth_borough_metrics(elections, population, election_years_roc=[111])

        row = result["years"][0]["districts"][0]
        self.assertEqual(row["youth_elected_count"], 1)
        self.assertEqual(row["elected_seat_count"], 2)
        self.assertEqual(row["youth_borough_chief_ratio"], 50.0)
        self.assertEqual(row["yrr"], 5.0)
        self.assertTrue(row["proxy"])

    def test_proposal_funnel_deduplicates_items_and_leaves_tracker_stages_null(self):
        records = [
            {
                "meeting_id": "meeting-1",
                "item_no": "一",
                "topic_text": "青年資料平台",
                "year_roc": "114",
                "discussed": True,
                "resolved": False,
                "escalated": False,
                "parse_status": "partial",
                "manual_review_required": True,
            },
            {
                "meeting_id": "meeting-1",
                "item_no": "一",
                "topic_text": "青年資料平台",
                "year_roc": "114",
                "discussed": True,
                "resolved": True,
                "escalated": True,
                "parse_status": "complete",
                "manual_review_required": False,
            },
            {
                "meeting_id": "meeting-1",
                "item_no": "二",
                "topic_text": "青年交通",
                "year_roc": "113",
                "discussed": True,
                "resolved": False,
                "escalated": False,
                "parse_status": "complete",
                "manual_review_required": False,
            },
        ]

        result = calculate_proposal_funnel(records, recent_year_count=3)

        self.assertEqual(result["stages"][0]["count"], 2)
        self.assertEqual(result["stages"][1]["count"], 2)
        self.assertEqual(result["stages"][2]["count"], 1)
        self.assertIsNone(result["stages"][3]["count"])
        self.assertIsNone(result["stages"][4]["count"])
        self.assertEqual(result["escalated_to_council"], 1)
        self.assertEqual(result["coverage_scope"], "meeting_records")
        self.assertEqual(result["status"], "partial")

    def test_grant_metrics_group_by_district_and_year(self):
        records = [
            {"year_roc": "113", "amount_twd_thousand": 10, "district_id": "65000010", "geo_basis": "project_location"},
            {"year_roc": "113", "amount_twd_thousand": 5, "district_id": "65000010", "geo_basis": "recipient_address"},
            {"year_roc": "114", "amount_twd_thousand": 7, "district_id": None, "geo_basis": "unresolved"},
        ]

        result = calculate_grant_metrics(records, annual_years_roc=[110, 111, 112, 113, 114])

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["by_district"]["113"][0]["amount_twd_thousand"], 15)
        self.assertEqual(result["trend"][-1]["year_roc"], 114)
        self.assertEqual(result["trend"][-1]["amount_twd_thousand"], 7)
        self.assertEqual(result["unresolved_district_row_count"], 1)


if __name__ == "__main__":
    unittest.main()
