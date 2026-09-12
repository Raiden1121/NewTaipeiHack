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
        # The two 1號 rows sit kilometres apart, so they are genuinely different
        # addresses rather than two door plates on one building.
        content = _zip_csv(
            [
                {"countycode": "65000", "street": "中央路", "section": "四段", "lane": "", "alley": "", "number": "1號", "x_3826": "300000", "y_3826": "2750000"},
                {"countycode": "65000", "street": "中央路", "section": "四段", "lane": "", "alley": "", "number": "2號", "x_3826": "300001", "y_3826": "2750001"},
                {"countycode": "65000", "street": "中央路", "section": "四段", "lane": "", "alley": "", "number": "1號", "x_3826": "305000", "y_3826": "2755000"},
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


    def test_district_code_separates_identical_street_numbers(self):
        fieldnames = ["countycode", "areacode", "street、road、section", "area", "lane", "alley", "number", "x_3826", "y_3826"]
        rows = [
            {"countycode": "65000", "areacode": areacode, "street、road、section": "中山路", "area": "", "lane": "", "alley": "", "number": "100號", "x_3826": x, "y_3826": y}
            for areacode, x, y in (
                ("65000010", "300000", "2750000"),
                ("65000020", "310000", "2760000"),
                ("65000030", "320000", "2770000"),
            )
        ]
        content = _zip_csv(rows, fieldnames=fieldnames)

        result = match_ntpc_address_points(
            [{"point_id": "banqiao", "address": "新北市板橋區中山路100號2樓", "areacode": "65000010"}],
            open_url=lambda request, timeout: _Response(content),
        )

        self.assertEqual([row["point_id"] for row in result.matches], ["banqiao"])
        self.assertEqual(result.matches[0]["x_3826"], 300000.0)

    def test_arabic_and_cjk_section_digits_are_interchangeable(self):
        fieldnames = ["countycode", "areacode", "street、road、section", "area", "lane", "alley", "number", "x_3826", "y_3826"]
        content = _zip_csv(
            [{"countycode": "65000", "areacode": "65000010", "street、road、section": "四川路一段", "area": "", "lane": "", "alley": "", "number": "151號", "x_3826": "300000", "y_3826": "2750000"}],
            fieldnames=fieldnames,
        )

        result = match_ntpc_address_points(
            [{"point_id": "arabic", "address": "新北市板橋區四川路1段151號", "areacode": "65000010"}],
            open_url=lambda request, timeout: _Response(content),
        )

        self.assertEqual([row["point_id"] for row in result.matches], ["arabic"])

    def test_listed_plates_and_hyphen_plates_are_normalized(self):
        fieldnames = ["countycode", "areacode", "street、road、section", "area", "lane", "alley", "number", "x_3826", "y_3826"]
        content = _zip_csv(
            [
                {"countycode": "65000", "areacode": "65000010", "street、road、section": "三民路二段", "area": "", "lane": "21巷", "alley": "", "number": "8號", "x_3826": "300000", "y_3826": "2750000"},
                {"countycode": "65000", "areacode": "65000010", "street、road、section": "國慶路", "area": "", "lane": "", "alley": "", "number": "165之1號二樓", "x_3826": "301000", "y_3826": "2751000"},
            ],
            fieldnames=fieldnames,
        )

        result = match_ntpc_address_points(
            [
                {"point_id": "listed", "address": "新北市板橋區三民路二段21巷8、10、12、16號1樓", "areacode": "65000010"},
                {"point_id": "hyphen", "address": "新北市板橋區國慶路165-1號2樓", "areacode": "65000010"},
            ],
            open_url=lambda request, timeout: _Response(content),
        )

        self.assertEqual({row["point_id"] for row in result.matches}, {"listed", "hyphen"})

    def test_same_building_plates_collapse_and_sub_plates_are_a_fallback(self):
        fieldnames = ["countycode", "areacode", "street、road、section", "area", "lane", "alley", "number", "x_3826", "y_3826"]
        content = _zip_csv(
            [
                {"countycode": "65000", "areacode": "65000010", "street、road、section": "大觀路二段", "area": "", "lane": "265巷", "alley": "3弄", "number": "53號之3", "x_3826": "294700", "y_3826": "2765440"},
                {"countycode": "65000", "areacode": "65000010", "street、road、section": "大觀路二段", "area": "", "lane": "265巷", "alley": "3弄", "number": "53號之8", "x_3826": "294740", "y_3826": "2765430"},
            ],
            fieldnames=fieldnames,
        )

        result = match_ntpc_address_points(
            [{"point_id": "gongba", "address": "新北市板橋區大觀路二段265巷3弄53號1樓", "areacode": "65000010"}],
            open_url=lambda request, timeout: _Response(content),
        )

        self.assertEqual([row["point_id"] for row in result.matches], ["gongba"])
        self.assertAlmostEqual(result.matches[0]["x_3826"], 294720.0, places=3)


if __name__ == "__main__":
    unittest.main()
