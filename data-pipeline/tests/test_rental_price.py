from __future__ import annotations

import csv
import io
import json
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import rental_price  # noqa: E402


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._payload


def rental_record(**overrides):
    record = {
        "district": "板橋區",
        "rps01": "租賃房屋",
        "rps02": "測試路 1 號",
        "rps03_area": "12.3",
        "rps07_yyymmddroc": "1140219",
        "rps08": "整層住家",
        "rps09": "5",
        "rps10_quantity": "12",
        "rps11": "住宅大樓(11層含以上有電梯)",
        "rps12": "住家用",
        "rps15_area": "85.8",
        "rps16_quantity": "3",
        "rps17_quantity": "2",
        "rps18_quantity": "2",
        "rps22_amountsunitdollars": "23000",
        "rps23_amountsunitdollars": "268",
        "rps24": "無",
        "rps25_area": "0",
        "rps26_amountsunitdollars": "0",
        "rps27": "",
        "rps28": "rental-1",
        "rps29": "整棟(戶)出租",
        "rps30": "無",
        "rps31": "一年",
        "rps32": "有",
        "rps33": "",
        "rps34": "",
    }
    record.update(overrides)
    return record


def csv_payload(*rows):
    fieldnames = list(rental_record())
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


class TestRentalPriceCollector(unittest.TestCase):
    def test_normalizes_residential_record_without_aggregating(self):
        records = rental_price.normalize_rental_records(
            [rental_record()],
            fetched_at="2026-09-01T00:00:00+00:00",
        )

        self.assertEqual(len(records), 1)
        normalized = records[0]
        self.assertEqual(normalized["rps22_amountsunitdollars"], "23000")
        self.assertEqual(normalized["rental_date"], "1140219")
        self.assertEqual(normalized["rental_period"], "11402")
        self.assertEqual(normalized["rent_total"], 23000)
        self.assertEqual(normalized["building_area_sqm"], 85.8)
        self.assertEqual(normalized["rent_per_sqm"], 268)
        self.assertAlmostEqual(normalized["rent_per_ping"], 885.95038, places=5)
        self.assertEqual(normalized["rental_type"], "整戶")
        self.assertEqual(
            normalized["snapshot_fetched_at"],
            "2026-09-01T00:00:00+00:00",
        )
        self.assertNotIn("rent_median", normalized)
        self.assertNotIn("rent_yoy", normalized)

    def test_filters_non_residential_rows_and_can_return_them_on_request(self):
        rows = [
            rental_record(rps28="residential"),
            rental_record(
                rps01="租賃房屋",
                rps12="店舖、集合住宅",
                rps28="store",
            ),
            rental_record(
                rps01="車位",
                rps12="",
                rps28="parking",
            ),
        ]

        residential = rental_price.normalize_rental_records(rows)
        all_rows = rental_price.normalize_rental_records(
            rows,
            residential_only=False,
        )

        self.assertEqual([row["rps28"] for row in residential], ["residential"])
        self.assertEqual(
            [row["rps28"] for row in all_rows],
            ["residential", "store", "parking"],
        )

    def test_fetches_csv_and_filters_to_requested_district(self):
        requests = []

        def open_url(request, timeout):
            requests.append((request, timeout))
            return FakeResponse(
                csv_payload(
                    rental_record(rps28="banqiao"),
                    rental_record(district="中和區", rps28="zhonghe"),
                )
            )

        records = rental_price.fetch_rental_prices(
            district="板橋區",
            open_url=open_url,
        )

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0].full_url, rental_price.RENTAL_CSV_URL)
        self.assertEqual(requests[0][0].get_header("Accept"), "text/csv")
        self.assertEqual([record["district"] for record in records], ["板橋區"])

    def test_rejects_invalid_json(self):
        with self.assertRaises(rental_price.RentalPriceCollectorError):
            rental_price.fetch_rental_prices(
                source_format="json",
                open_url=lambda request, timeout: FakeResponse(b"not-json"),
            )

    def test_rejects_invalid_api_shape(self):
        with self.assertRaises(rental_price.RentalPriceCollectorError):
            rental_price.fetch_rental_prices(
                source_format="json",
                open_url=lambda request, timeout: FakeResponse(
                    json.dumps({"data": []}).encode("utf-8")
                ),
            )


if __name__ == "__main__":
    unittest.main()
