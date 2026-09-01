import csv
import io
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import job_vacancy  # noqa: E402


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._payload


def csv_payload(*rows, descriptive_headers=False):
    fieldnames = ["OCCU_DESC", "JOB_PERSON", "CITYNAME", "URL_QUERY"]
    if descriptive_headers:
        headers = {
            "OCCU_DESC": "OCCU_DESC（職務名稱）",
            "JOB_PERSON": "JOB_PERSON（雇用人數）",
            "CITYNAME": "CITYNAME（工作地點）",
            "URL_QUERY": "URL_QUERY（職缺資料URL）",
        }
        fieldnames = [headers[field] for field in fieldnames]
        rows = [
            {headers[field]: value for field, value in row.items()}
            for row in rows
        ]

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


class TestJobVacancyCollector(unittest.TestCase):
    def test_accepts_api_headers_with_chinese_descriptions(self):
        records = job_vacancy.fetch_job_vacancies(
            "220",
            district="板橋區",
            open_url=lambda request, timeout: FakeResponse(
                csv_payload(
                    {
                        "OCCU_DESC": "測試工程師",
                        "JOB_PERSON": "2",
                        "CITYNAME": "新北市板橋區",
                        "URL_QUERY": "https://example.test/job/1",
                    },
                    descriptive_headers=True,
                )
            ),
        )

        self.assertEqual(records[0]["CITYNAME（工作地點）"], "新北市板橋區")
        self.assertEqual(job_vacancy.sum_job_person(records), 2)

    def test_fetches_csv_and_adds_query_metadata(self):
        requests = []

        def open_url(request, timeout):
            requests.append(request)
            return FakeResponse(
                csv_payload(
                    {
                        "OCCU_DESC": "測試工程師",
                        "JOB_PERSON": "2",
                        "CITYNAME": "新北市板橋區",
                        "URL_QUERY": "https://example.test/job/1",
                    }
                )
            )

        records = job_vacancy.fetch_job_vacancies(
            "220",
            district="板橋區",
            count=10,
            open_url=open_url,
        )

        self.assertEqual(records[0]["OCCU_DESC"], "測試工程師")
        self.assertEqual(records[0]["JOB_PERSON"], "2")
        self.assertEqual(records[0]["query_zipno"], "220")
        self.assertEqual(records[0]["district"], "板橋區")
        self.assertFalse(records[0]["query_truncated"])

        query = parse_qs(urlsplit(requests[0].full_url).query)
        self.assertEqual(query["city"], ["31"])
        self.assertEqual(query["zipno"], ["220"])
        self.assertEqual(query["count"], ["10"])
        self.assertEqual(query["T"], ["CSV"])

    def test_marks_response_at_count_limit_as_possible_truncation(self):
        records = job_vacancy.fetch_job_vacancies(
            "220",
            district="板橋區",
            count=2,
            open_url=lambda request, timeout: FakeResponse(
                csv_payload(
                    {
                        "OCCU_DESC": "測試工程師",
                        "JOB_PERSON": "1",
                        "CITYNAME": "新北市板橋區",
                        "URL_QUERY": "https://example.test/job/1",
                    },
                    {
                        "OCCU_DESC": "測試分析師",
                        "JOB_PERSON": "3",
                        "CITYNAME": "新北市板橋區",
                        "URL_QUERY": "https://example.test/job/2",
                    },
                )
            ),
        )

        self.assertTrue(all(record["query_truncated"] for record in records))

    def test_rejects_cityname_outside_requested_district(self):
        with self.assertRaisesRegex(
            job_vacancy.JobVacancyCollectorError,
            "CITYNAME.*板橋區",
        ):
            job_vacancy.fetch_job_vacancies(
                "220",
                district="板橋區",
                open_url=lambda request, timeout: FakeResponse(
                    csv_payload(
                        {
                            "OCCU_DESC": "測試工程師",
                            "JOB_PERSON": "1",
                            "CITYNAME": "新北市中和區",
                            "URL_QUERY": "https://example.test/job/1",
                        }
                    )
                ),
            )

    def test_fetches_multiple_districts_with_explicit_mapping(self):
        requests = []
        district_to_zip = {"板橋區": "220", "中和區": "235"}
        zip_to_city = {
            zipno: district
            for district, zipno in district_to_zip.items()
        }

        def open_url(request, timeout):
            requests.append(request)
            query = parse_qs(urlsplit(request.full_url).query)
            zipno = query["zipno"][0]
            return FakeResponse(
                csv_payload(
                    {
                        "OCCU_DESC": "測試職缺",
                        "JOB_PERSON": "1",
                        "CITYNAME": f"新北市{zip_to_city[zipno]}",
                        "URL_QUERY": f"https://example.test/job/{zipno}",
                    }
                )
            )

        records = job_vacancy.fetch_new_taipei_job_vacancies(
            zip_codes=district_to_zip,
            count=10,
            open_url=open_url,
        )

        self.assertEqual(
            [record["district"] for record in records],
            ["板橋區", "中和區"],
        )
        self.assertEqual(
            [
                parse_qs(urlsplit(request.full_url).query)["zipno"][0]
                for request in requests
            ],
            ["220", "235"],
        )

    def test_counts_rows_and_sums_job_people_by_district(self):
        records = [
            {"district": "板橋區", "JOB_PERSON": "2"},
            {"district": "板橋區", "JOB_PERSON": "3"},
            {"district": "中和區", "JOB_PERSON": "4"},
        ]

        self.assertEqual(job_vacancy.count_job_vacancies(records), 3)
        self.assertEqual(
            job_vacancy.count_job_vacancies_by_district(records),
            {"板橋區": 2, "中和區": 1},
        )
        self.assertEqual(job_vacancy.sum_job_person(records), 9)
        self.assertEqual(
            job_vacancy.sum_job_person_by_district(records),
            {"板橋區": 5, "中和區": 4},
        )

    def test_rejects_invalid_csv(self):
        with self.assertRaises(job_vacancy.JobVacancyCollectorError):
            job_vacancy.fetch_job_vacancies(
                "220",
                open_url=lambda request, timeout: FakeResponse(b"not,csv\n\x80"),
            )

    def test_rejects_invalid_job_person(self):
        with self.assertRaises(job_vacancy.JobVacancyCollectorError):
            job_vacancy.sum_job_person(
                [{"district": "板橋區", "JOB_PERSON": "unknown"}]
            )


if __name__ == "__main__":
    unittest.main()
