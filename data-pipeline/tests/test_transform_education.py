import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.education import transform_college_majors, transform_graduate_majors  # noqa: E402
from transform.geography import DistrictResolver  # noqa: E402


def overview_record():
    return {
        "學年度": "114",
        "學校代碼": "0001",
        "學校名稱": "測試大學",
        "科系代碼": "01111001",
        "科系名稱": "測試科系",
        "日間∕進修別": "D 日",
        "等級別": "B 學士",
        "學生數": "10",
        "教師數": "1",
        "上學年度畢業生數": "2",
        "縣市名稱": "01 新北市",
        "體系別": "1 一般",
    }


def detail_record(*, school_code="1", department_code="1111001"):
    return {
        "學年度": "114",
        "學校代碼": school_code,
        "學校名稱": "測試大學",
        "科系代碼": department_code,
        "科系名稱": "測試科系",
        "日間∕進修別": "D 日",
        "等級別": "B 學士",
        "總計": "10",
        "男生計": "4",
        "女生計": "6",
        "縣市名稱": "01 新北市",
        "體系別": "1 一般",
    }


class TestTransformEducation(unittest.TestCase):
    def test_maps_college_records_to_district_using_school_code(self):
        resolver = DistrictResolver(
            [
                {
                    "district_id": "65000010",
                    "district_name": "板橋區",
                    "postal_code": "220",
                    "aliases": [],
                }
            ]
        )
        locations = [
            {
                "school_code": "1",
                "school_name": "測試大學",
                "county_name": "新北市",
                "district_name": "板橋區",
                "postal_code": "220",
                "school_address": "新北市板橋區測試路1號",
                "source": "moe_33207_108",
            }
        ]

        result = transform_college_majors(
            [overview_record()],
            [detail_record()],
            resolver=resolver,
            school_locations=locations,
        )

        record = result.records[0]
        self.assertEqual(record["geo_level"], "district")
        self.assertEqual(record["district_id"], "65000010")
        self.assertEqual(record["district_name"], "板橋區")
        self.assertEqual(record["school_address"], "新北市板橋區測試路1號")
        self.assertEqual(record["school_location_status"], "matched")

    def test_keeps_null_district_when_school_code_is_not_in_location_reference(self):
        resolver = DistrictResolver(
            [
                {
                    "district_id": "65000010",
                    "district_name": "板橋區",
                    "postal_code": "220",
                    "aliases": [],
                }
            ]
        )

        result = transform_college_majors(
            [overview_record()],
            resolver=resolver,
            school_locations=[],
        )

        record = result.records[0]
        self.assertEqual(record["geo_level"], "district")
        self.assertIsNone(record["district_id"])
        self.assertEqual(record["school_location_status"], "unmatched_school")
        self.assertIn("school_location_unmatched", record["quality_flags"])

    def test_joins_9621_and_9622_using_normalized_codes_but_preserves_sources(self):
        overview = overview_record()
        detail = detail_record()

        result = transform_college_majors([overview], [detail])

        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record["student_count"], 10)
        self.assertEqual(record["detail_student_count"], 10)
        self.assertEqual(record["male_student_count"], 4)
        self.assertEqual(record["female_student_count"], 6)
        self.assertEqual(record["overview_raw_record"]["學校代碼"], "0001")
        self.assertEqual(record["detail_raw_record"]["學校代碼"], "1")
        self.assertEqual(record["geo_level"], "county")
        self.assertEqual(record["county_name"], "新北市")

    def test_keeps_unmatched_9622_row_with_null_overview_values_and_warning(self):
        detail = detail_record(school_code="2")

        result = transform_college_majors([], [detail])

        self.assertEqual(len(result.records), 1)
        self.assertIsNone(result.records[0]["student_count"])
        self.assertEqual(result.records[0]["detail_student_count"], 10)
        self.assertIn("unmatched_student_detail", result.records[0]["quality_flags"])
        self.assertIn("unmatched_student_detail", result.quality["warnings"])

    def test_aggregates_all_9622_rows_for_same_join_key_and_keeps_provenance(self):
        first = detail_record()
        second = detail_record()
        first.update({"一年級男生": "2", "一年級女生": "3"})
        second.update({
            "科系名稱": "測試科系第二班",
            "總計": "20",
            "男生計": "8",
            "女生計": "12",
            "一年級男生": "4",
            "一年級女生": "6",
        })

        result = transform_college_majors([overview_record()], [first, second])

        record = result.records[0]
        self.assertEqual(record["detail_student_count"], 30)
        self.assertEqual(record["male_student_count"], 12)
        self.assertEqual(record["female_student_count"], 18)
        self.assertEqual(record["detail_counts"]["一年級男生"], 6)
        self.assertEqual(record["detail_counts"]["一年級女生"], 9)
        self.assertEqual(record["detail_raw_records"], [first, second])

    def test_invalid_9622_row_is_quarantined_without_aborting_valid_overview(self):
        malformed = detail_record()
        malformed["總計"] = "unknown"

        result = transform_college_majors([overview_record()], [malformed])

        self.assertEqual(len(result.records), 1)
        self.assertIsNone(result.records[0]["detail_student_count"])
        self.assertEqual(result.quality["rows_rejected"], 1)
        self.assertIn("invalid_detail", result.quarantine[0]["reason"])

    def test_9620_graduate_source_stays_national_even_if_record_has_county(self):
        raw = {
            "學年度": "113",
            "細學類": "1111",
            "細學類名稱": "綜合教育細學類",
            "科系名稱": "測試科系",
            "日間_進修別": "D 日",
            "等級別": "B 學士",
            "上學年畢業生人數男": "4",
            "上學年畢業生人數女": "6",
            "縣市名稱": "01 新北市",
        }

        result = transform_graduate_majors([raw])

        record = result.records[0]
        self.assertEqual(record["geo_level"], "national")
        self.assertIsNone(record["district_id"])
        self.assertEqual(record["graduate_count"], 10)
        self.assertEqual(record["youth_eligibility"], "context_only")


if __name__ == "__main__":
    unittest.main()
