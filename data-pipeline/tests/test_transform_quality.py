import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.quality import QualityCollector  # noqa: E402


class TestQualityCollector(unittest.TestCase):
    def test_finish_reports_all_required_quality_counters(self):
        quality = QualityCollector(rows_in=3)
        quality.accept()
        quality.accept()
        quality.reject(2, {"site_id": "未知區"}, "unmapped_district")
        quality.record_duplicate()
        quality.record_unmapped_district()
        quality.record_numeric_error("people_total")
        quality.record_missing("period")
        quality.warn("query_truncated")
        quality.warn("query_truncated")

        report = quality.finish()

        self.assertEqual(report["rows_in"], 3)
        self.assertEqual(report["rows_out"], 2)
        self.assertEqual(report["rows_rejected"], 1)
        self.assertEqual(report["duplicate_count"], 1)
        self.assertEqual(report["unmapped_district_count"], 1)
        self.assertEqual(report["numeric_parse_errors"], 1)
        self.assertEqual(report["missing_value_count"], 1)
        self.assertEqual(report["warnings"], ["query_truncated"])
        self.assertEqual(report["reject_reasons"], {"unmapped_district": 1})

    def test_quarantine_preserves_input_index_raw_record_and_reason(self):
        quality = QualityCollector(rows_in=1)
        raw = {"people_total": "invalid"}

        quality.reject(0, raw, "invalid_numeric")

        self.assertEqual(
            quality.quarantine,
            [{"input_index": 0, "raw_record": raw, "reason": "invalid_numeric"}],
        )


if __name__ == "__main__":
    unittest.main()
