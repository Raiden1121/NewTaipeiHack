from __future__ import annotations

import csv
import io
import json
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors import house_price  # noqa: E402


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._payload


def house_record(**overrides):
    record = {
        "district": "板橋區",
        "rps01": "房地(土地+建物)",
        "rps02": "新北市板橋區測試路 1 號二樓",
        "rps03_area": "40.32",
        "rps04": "住宅區",
        "rps05": "",
        "rps06": "",
        "rps07_yyymmddroc": "1140521",
        "rps08": "土地3建物1車位0",
        "rps09": "二層",
        "rps10": "四層",
        "rps11": "公寓(5樓含以下無電梯)",
        "rps12": "住家用",
        "rps13": "鋼筋混凝土造",
        "rps14_yyymmddroc": "0780529",
        "rps15_area": "104.73",
        "rps16_quantity": "3",
        "rps17_quantity": "2",
        "rps18_quantity": "2",
        "rps19": "有",
        "rps20": "無",
        "rps21_amountsunitdollars": "4200000",
        "rps22_amountsunitdollars": "40103",
        "rps23": "",
        "rps24_area": "0",
        "rps25_amountsunitdollars": "0",
        "rps26": "",
        "rps27": "sale-1",
        "rps28_area": "94.21",
        "rps29_area": "0",
        "rps30_area": "10.52",
        "rps31": "無",
        "rps32": "",
    }
    record.update(overrides)
    return record


def csv_payload(*rows):
    fieldnames = list(house_record())
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


class TestHousePriceCollector(unittest.TestCase):
    def test_normalizes_residential_record_without_aggregating(self):
        records = house_price.normalize_house_records(
            [house_record()],
            fetched_at="2026-09-01T00:00:00+00:00",
        )

        self.assertEqual(len(records), 1)
        normalized = records[0]
        self.assertEqual(normalized["rps21_amountsunitdollars"], "4200000")
        self.assertEqual(normalized["rps22_amountsunitdollars"], "40103")
        self.assertEqual(normalized["transaction_date"], "1140521")
        self.assertEqual(normalized["transaction_period"], "11405")
        self.assertEqual(normalized["total_price"], 4200000)
        self.assertEqual(normalized["building_area_sqm"], 104.73)
        self.assertEqual(normalized["price_per_sqm"], 40103)
        self.assertAlmostEqual(
            normalized["price_per_ping"],
            132571.895855,
            places=6,
        )
        self.assertEqual(normalized["transaction_type"], "房地(土地+建物)")
        self.assertEqual(
            normalized["snapshot_fetched_at"],
            "2026-09-01T00:00:00+00:00",
        )
        self.assertNotIn("price_median", normalized)
        self.assertNotIn("growth_rate", normalized)

    def test_returns_all_rows_by_default_and_can_filter_to_residential(self):
        rows = [
            house_record(rps27="residential"),
            house_record(
                rps01="土地",
                rps12="",
                rps27="land",
            ),
            house_record(
                rps01="房地(土地+建物)",
                rps12="商業用",
                rps27="commercial",
            ),
            house_record(
                rps01="車位",
                rps12="",
                rps27="parking",
            ),
        ]

        all_rows = house_price.normalize_house_records(rows)
        residential = house_price.normalize_house_records(
            rows,
            residential_only=True,
        )

        self.assertEqual(
            [row["rps27"] for row in residential],
            ["residential"],
        )
        self.assertEqual(
            [row["rps27"] for row in all_rows],
            ["residential", "land", "commercial", "parking"],
        )

    def test_fetches_csv_and_filters_to_requested_district(self):
        requests = []

        def open_url(request, timeout):
            requests.append((request, timeout))
            return FakeResponse(
                csv_payload(
                    house_record(rps27="banqiao"),
                    house_record(district="中和區", rps27="zhonghe"),
                )
            )

        records = house_price.fetch_house_prices(
            district="板橋區",
            open_url=open_url,
        )

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0].full_url, house_price.HOUSE_CSV_URL)
        self.assertEqual(requests[0][0].get_header("Accept"), "text/csv")
        self.assertEqual([record["district"] for record in records], ["板橋區"])

    def test_rejects_invalid_json(self):
        with self.assertRaises(house_price.HousePriceCollectorError):
            house_price.fetch_house_prices(
                source_format="json",
                open_url=lambda request, timeout: FakeResponse(b"not-json"),
            )

    def test_rejects_invalid_api_shape(self):
        with self.assertRaises(house_price.HousePriceCollectorError):
            house_price.fetch_house_prices(
                source_format="json",
                open_url=lambda request, timeout: FakeResponse(
                    json.dumps({"data": []}).encode("utf-8")
                ),
            )


if __name__ == "__main__":
    unittest.main()
