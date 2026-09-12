import csv
import io
import sys
import unittest
import zipfile
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.ntpc_address_points import match_ntpc_address_points  # noqa: E402


class _Response:
    def __init__(self, content):
        self.content = content

    def read(self, _limit):
        return self.content

    def close(self):
        pass


def _zip_csv(rows, *, fieldnames=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        output = io.StringIO()
        fieldnames = fieldnames or ["countycode", "street", "section", "lane", "alley", "number", "x_3826", "y_3826"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        archive.writestr("address.csv", output.getvalue().encode("utf-8"))
    return buffer.getvalue()


class TestNTPCAddressPoints(unittest.TestCase):
    def test_unique_normalized_address_match_and_ambiguous_exclusion(self):
        content = _zip_csv(
            [
                {"countycode": "65000", "street": "中央路", "section": "四段", "lane": "", "alley": "", "number": "1號", "x_3826": "300000", "y_3826": "2750000"},
                {"countycode": "65000", "street": "中央路", "section": "四段", "lane": "", "alley": "", "number": "2號", "x_3826": "300001", "y_3826": "2750001"},
                {"countycode": "65000", "street": "中央路", "section": "四段", "lane": "", "alley": "", "number": "1號", "x_3826": "300002", "y_3826": "2750002"},
            ]
        )
        result = match_ntpc_address_points(
            [
                {"point_id": "one", "address": "新北市土城區中央路四段1號"},
                {"point_id": "two", "address": "新北市土城區中央路四段2號"},
            ],
            open_url=lambda request, timeout: _Response(content),
        )

        self.assertEqual({row["point_id"] for row in result.matches}, {"two"})
        self.assertEqual(result.matches[0]["geocode_crs"], "EPSG:3826")
        self.assertEqual(result.metadata["source_rows_scanned"], 3)

    def test_matches_ntpc_combined_street_field_and_ignores_floor_suffix(self):
        fieldnames = ["countycode", "areacode", "street、road、section", "area", "lane", "alley", "number", "x_3826", "y_3826"]
        content = _zip_csv(
            [
                {
                    "countycode": "65000",
                    "areacode": "65000130",
                    "street、road、section": "莊園街",
                    "area": "",
                    "lane": "",
                    "alley": "",
                    "number": "１５１號",
                    "x_3826": "300000",
                    "y_3826": "2750000",
                }
            ],
            fieldnames=fieldnames,
        )

        result = match_ntpc_address_points(
            [{"point_id": "base", "address": "新北市土城區莊園街151號2樓"}],
            open_url=lambda request, timeout: _Response(content),
        )

        self.assertEqual([row["point_id"] for row in result.matches], ["base"])


if __name__ == "__main__":
    unittest.main()
