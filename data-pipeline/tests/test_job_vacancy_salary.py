from __future__ import annotations

import csv
import importlib
import io
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

try:
    job_vacancy_salary = importlib.import_module("collectors.job_vacancy_salary")
except ImportError as exc:  # The RED phase expects the module to be absent.
    job_vacancy_salary = None
    _import_error = exc


def collector_module():
    if job_vacancy_salary is None:
        raise AssertionError(
            "collectors.job_vacancy_salary is not implemented"
        ) from _import_error
    return job_vacancy_salary


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._payload


def csv_payload(*rows):
    fieldnames = [
        "OCCU_DESC",
        "JOB_PERSON",
        "CITYNAME",
        "SALARYCD",
        "NT_L",
        "NT_U",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


class TestJobVacancySalaryCollector(unittest.TestCase):
    def test_normalizes_monthly_salary_range_without_dropping_raw_fields(self):
        records = collector_module().normalize_posted_salary_records(
            [
                {
                    "SALARYCD（薪資類別）": "月薪",
                    "NT_L（最低薪資）": "35,000",
                    "NT_U（最高薪資）": "45,000",
                    "CITYNAME（工作地點）": "新北市板橋區",
                    "district": "板橋區",
                    "query_truncated": False,
                }
            ],
            snapshot_fetched_at="2026-09-01T00:00:00+00:00",
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["NT_L（最低薪資）"], "35,000")
        self.assertEqual(records[0]["salary_type"], "月薪")
        self.assertEqual(records[0]["salary_lower"], 35000)
        self.assertEqual(records[0]["salary_upper"], 45000)
        self.assertEqual(records[0]["salary_midpoint"], 40000)
        self.assertEqual(records[0]["salary_estimate_type"], "range_midpoint")
        self.assertEqual(
            records[0]["snapshot_fetched_at"],
            "2026-09-01T00:00:00+00:00",
        )

    def test_filters_to_monthly_salary_and_marks_single_bounds(self):
        records = collector_module().normalize_posted_salary_records(
            [
                {
                    "SALARYCD": "月薪",
                    "NT_L": "35000",
                    "NT_U": "-",
                    "district": "板橋區",
                    "query_truncated": False,
                },
                {
                    "SALARYCD": "時薪",
                    "NT_L": "200",
                    "NT_U": "250",
                    "district": "板橋區",
                    "query_truncated": False,
                },
                {
                    "SALARYCD": "月薪",
                    "NT_L": "-",
                    "NT_U": "",
                    "district": "板橋區",
                    "query_truncated": False,
                },
            ]
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["salary_midpoint"], None)
        self.assertEqual(records[0]["salary_estimate_type"], "lower_bound")
        self.assertEqual(records[1]["salary_lower"], None)
        self.assertEqual(records[1]["salary_upper"], None)
        self.assertEqual(records[1]["salary_estimate_type"], "missing")

    def test_summarizes_only_complete_ranges_and_hides_truncated_median(self):
        records = collector_module().normalize_posted_salary_records(
            [
                {
                    "SALARYCD": "月薪",
                    "NT_L": "35000",
                    "NT_U": "45000",
                    "district": "板橋區",
                    "query_truncated": False,
                },
                {
                    "SALARYCD": "月薪",
                    "NT_L": "45000",
                    "NT_U": "55000",
                    "district": "板橋區",
                    "query_truncated": False,
                },
                {
                    "SALARYCD": "月薪",
                    "NT_L": "50000",
                    "NT_U": "60000",
                    "district": "中和區",
                    "query_truncated": True,
                },
            ]
        )

        summary = collector_module().summarize_posted_salary_by_district(records)

        self.assertEqual(summary["板橋區"]["vacancy_count"], 2)
        self.assertEqual(summary["板橋區"]["salary_valid_count"], 2)
        self.assertEqual(summary["板橋區"]["salary_coverage"], 1.0)
        self.assertEqual(summary["板橋區"]["salary_median"], 45000)
        self.assertFalse(summary["板橋區"]["query_truncated"])
        self.assertIsNone(summary["中和區"]["salary_median"])
        self.assertTrue(summary["中和區"]["query_truncated"])

    def test_fetches_vacancies_through_existing_collector(self):
        requests = []
        zip_codes = {"板橋區": "220", "中和區": "235"}

        def open_url(request, timeout):
            requests.append(request)
            district = "板橋區" if "zipno=220" in request.full_url else "中和區"
            return FakeResponse(
                csv_payload(
                    {
                        "OCCU_DESC": "測試職缺",
                        "JOB_PERSON": "1",
                        "CITYNAME": f"新北市{district}",
                        "SALARYCD": "月薪",
                        "NT_L": "35,000",
                        "NT_U": "45,000",
                    },
                    {
                        "OCCU_DESC": "時薪職缺",
                        "JOB_PERSON": "1",
                        "CITYNAME": f"新北市{district}",
                        "SALARYCD": "時薪",
                        "NT_L": "200",
                        "NT_U": "250",
                    },
                )
            )

        records = collector_module().fetch_job_posted_salaries(
            zip_codes=zip_codes,
            count=10,
            open_url=open_url,
        )

        self.assertEqual(len(requests), 2)
        self.assertEqual(len(records), 2)
        self.assertEqual(
            {record["district"] for record in records},
            {"板橋區", "中和區"},
        )
        self.assertTrue(all(record["salary_type"] == "月薪" for record in records))
        self.assertTrue(all(record["salary_midpoint"] == 40000 for record in records))

    def test_rejects_non_numeric_salary_bounds(self):
        with self.assertRaises(collector_module().JobVacancySalaryCollectorError):
            collector_module().normalize_posted_salary_records(
                [
                    {
                        "SALARYCD": "月薪",
                        "NT_L": "面議",
                        "NT_U": "45000",
                        "district": "板橋區",
                        "query_truncated": False,
                    }
                ]
            )


if __name__ == "__main__":
    unittest.main()
