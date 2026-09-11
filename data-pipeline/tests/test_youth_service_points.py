import io
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors import youth_service_points  # noqa: E402
from transform.service_points import transform_youth_service_points  # noqa: E402
from transform.geography import DistrictResolver  # noqa: E402


LIST_URL = youth_service_points.SERVICE_POINTS_LIST_URL
DETAIL_URL = "https://example.test/youth/ch/app/data/view?module=youth0001&id=145&serno=green"
LISTING_HTML = f'''
<a href="{DETAIL_URL.replace('&', '&amp;')}"
   title="新北青創綠創基地">新北青創綠創基地</a>
<a href="/other">不是青創基地</a>
'''
DETAIL_HTML = '''
<h2 class="title"><p>找基地</p></h2>
<ul><li class="note_box"> 發佈日期：<span>112-12-21</span></li>
<li class="note_box"> 更新日期：<span>114-12-18</span></li></ul>
<div class="d_title">新北青創綠創基地</div>
<div class="ed_txt">說明文字<br />地址：新北市土城區莊園街151號2樓<br />Email：<a href="mailto:green@example.test">green@example.test</a><br />服務電話：02-22600350</div>
'''


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False


def _fake_open_url(request, *, timeout):
    del timeout
    if request.full_url == LIST_URL:
        return _FakeResponse(LISTING_HTML.encode("utf-8"))
    if request.full_url == DETAIL_URL:
        return _FakeResponse(DETAIL_HTML.encode("utf-8"))
    raise AssertionError(f"unexpected URL: {request.full_url}")


class TestYouthServicePointCollector(unittest.TestCase):
    def test_discovers_detail_links_and_extracts_source_fields(self):
        payload = youth_service_points.fetch_youth_service_points(
            listing_url=LIST_URL,
            open_url=_fake_open_url,
        )

        self.assertEqual(len(payload.records), 1)
        row = payload.records[0]
        self.assertEqual(row["point_type"], "startup_base")
        self.assertEqual(row["name"], "新北青創綠創基地")
        self.assertEqual(row["address"], "新北市土城區莊園街151號2樓")
        self.assertEqual(row["source_district_name"], "土城區")
        self.assertEqual(row["email"], "green@example.test")
        self.assertEqual(row["published_date_roc"], "1121221")
        self.assertEqual(row["updated_date_roc"], "1141218")
        self.assertEqual(len(payload.artifacts), 2)

    def test_address_stops_before_adjacent_directions(self):
        html = DETAIL_HTML.replace(
            "</div>",
            " 交通：鄰近捷運站 【聯絡方式】<br />服務電話：02-22600350</div>",
        )

        def open_url(request, *, timeout):
            del timeout
            if request.full_url == LIST_URL:
                return _FakeResponse(LISTING_HTML.encode("utf-8"))
            if request.full_url == DETAIL_URL:
                return _FakeResponse(html.encode("utf-8"))
            raise AssertionError(f"unexpected URL: {request.full_url}")

        payload = youth_service_points.fetch_youth_service_points(
            listing_url=LIST_URL,
            open_url=open_url,
        )

        self.assertEqual(
            payload.records[0]["address"], "新北市土城區莊園街151號2樓"
        )


class TestYouthServicePointTransform(unittest.TestCase):
    def test_applies_static_location_reference_without_mutating_raw_record(self):
        resolver = DistrictResolver(
            [{"district_id": "65000020", "district_name": "三重區", "aliases": []}]
        )
        raw = {
            "point_id": "innovation",
            "point_type": "startup_base",
            "name": "新北創力坊",
            "address": None,
            "source_district_name": None,
            "latitude": None,
            "longitude": None,
            "geocode_status": "not_attempted",
        }

        result = transform_youth_service_points(
            [raw],
            resolver=resolver,
            location_reference={
                "innovation": {
                    "address": "新北市三重區重新路一段108號3樓",
                    "source_district_name": "三重區",
                    "x_3826": 300530.403775,
                    "y_3826": 2772867.4135083,
                    "source_url": "https://example.test/address",
                    "source_type": "official_manual_reference",
                    "verified_at": "2026-09-11",
                }
            },
        )

        row = result.records[0]
        self.assertEqual(row["address"], "新北市三重區重新路一段108號3樓")
        self.assertEqual(row["district_id"], "65000020")
        self.assertEqual(row["geocode_status"], "matched")
        self.assertAlmostEqual(row["x_3826"], 300530.403775)
        self.assertAlmostEqual(row["y_3826"], 2772867.4135083)
        self.assertEqual(row["location_source_type"], "official_manual_reference")
        self.assertIsNone(raw["address"])
        self.assertIsNone(row["raw_record"]["address"])

    def test_keeps_address_without_fabricating_coordinates(self):
        resolver = DistrictResolver(
            [{"district_id": "65000030", "district_name": "土城區", "aliases": []}]
        )
        result = transform_youth_service_points(
            [
                {
                    "point_id": "green",
                    "point_type": "startup_base",
                    "name": "新北青創綠創基地",
                    "address": "新北市土城區莊園街151號2樓",
                    "source_district_name": "土城區",
                    "phone": "02-22600350",
                    "email": "green@example.test",
                    "detail_url": DETAIL_URL,
                    "published_date_roc": "1121221",
                    "updated_date_roc": "1141218",
                    "latitude": None,
                    "longitude": None,
                }
            ],
            resolver=resolver,
        )

        row = result.records[0]
        self.assertEqual(row["district_id"], "65000030")
        self.assertEqual(row["point_type"], "startup_base")
        self.assertIsNone(row["latitude"])
        self.assertIsNone(row["longitude"])
        self.assertEqual(row["geocode_status"], "excluded_no_verified_coordinate")


if __name__ == "__main__":
    unittest.main()
