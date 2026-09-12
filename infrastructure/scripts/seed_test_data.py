"""Push a complete set of deterministic test data into the analytics
DynamoDB table, so infrastructure/modules/api/lambda/handler.py has
something to read before data-pipeline's real loader exists.

Single file, run locally:

    python infrastructure/scripts/seed_test_data.py --table-name newtaipei-youth-analytics
    python infrastructure/scripts/seed_test_data.py --self-check   # no AWS calls

Every value here is synthetic (deterministic formulas, not real analytics)
and is clearly labelled as such in the data itself (`calculation_version`,
`quality.status` are both "test") so nobody downstream mistakes it for a
real snapshot. Item shapes follow infrastructure/dynamodb_schema.md exactly.
"""

from __future__ import annotations

import argparse
import os
from decimal import Decimal
from typing import Any

SNAPSHOT_ID = "local-test-data"
GENERATED_AT = "2026-09-12T00:00:00Z"

DISTRICTS = [
    ("65000010", "板橋區"), ("65000020", "三重區"), ("65000030", "中和區"),
    ("65000040", "永和區"), ("65000050", "新莊區"), ("65000060", "新店區"),
    ("65000070", "樹林區"), ("65000080", "鶯歌區"), ("65000090", "三峽區"),
    ("65000100", "淡水區"), ("65000110", "汐止區"), ("65000120", "瑞芳區"),
    ("65000130", "土城區"), ("65000140", "蘆洲區"), ("65000150", "五股區"),
    ("65000160", "泰山區"), ("65000170", "林口區"), ("65000180", "深坑區"),
    ("65000190", "石碇區"), ("65000200", "坪林區"), ("65000210", "三芝區"),
    ("65000220", "石門區"), ("65000230", "八里區"), ("65000240", "平溪區"),
    ("65000250", "雙溪區"), ("65000260", "貢寮區"), ("65000270", "金山區"),
    ("65000280", "萬里區"), ("65000290", "烏來區"),
]

# Real values from api_contract.md §6.2 for the 5 districts that actually have
# service_coverage data; every other district is genuinely 0 (median is 0).
SERVICE_COVERAGE_OVERRIDES = {
    "65000010": 90.79, "65000020": 86.08, "65000030": 90.80,
    "65000040": 55.13, "65000050": 41.55,
}


def _frac(i):
    return i / (len(DISTRICTS) - 1)


def _retention_risk(i):
    if i < 8:
        return "low"
    if i < 21:
        return "medium"
    return "high"


def _build_borough_chief_rows():
    """3 屆（103/107/111）× 29 區里長選舉明細。僅民國 111 年屆的比例會被拿去併入
    districts[].youthBoroughChiefRatioPercent，其餘兩屆只保留在 elections.borough_chief_v1
    供未來歷年趨勢使用，不進 KPI 卡，見 api_contract.md §6.2。"""
    rows = []
    for i, (did, name) in enumerate(DISTRICTS):
        frac = _frac(i)
        elected_count = 20 + (i * 7) % 100
        for yr in (103, 107, 111):
            youth_elected = max(0, round(elected_count * (0.02 + 0.1 * frac)))
            rows.append({
                "district_id": did, "district_name": name, "year_roc": yr,
                "elected_count": elected_count, "youth_elected_count": youth_elected,
            })
    return rows


BOROUGH_CHIEF_ROWS = _build_borough_chief_rows()
BOROUGH_CHIEF_LATEST_BY_DISTRICT = {
    row["district_id"]: row for row in BOROUGH_CHIEF_ROWS if row["year_roc"] == 111
}


def _build_district(i, district_id, district_name):
    frac = _frac(i)
    job = round(10 + frac * 76.29, 2)
    salary = round(0.22 + frac * 91.39, 2)
    talent = 35.0 if i % 2 == 0 else 65.0
    housing = round(2.05 + frac * 97.95, 2)
    transport = round(1.76 + frac * 63.24, 2)
    opportunity_index = round(
        0.25 * job + 0.25 * salary + 0.05 * talent + 0.25 * housing + 0.20 * transport, 2
    )
    candidacy_rate = round((frac ** 2) * 64.68, 2)
    borough_latest = BOROUGH_CHIEF_LATEST_BY_DISTRICT[district_id]
    borough_chief_ratio = (
        round(borough_latest["youth_elected_count"] / borough_latest["elected_count"] * 100, 2)
        if borough_latest["elected_count"] else None
    )
    return {
        "district_id": district_id,
        "district_name": district_name,
        "youth_18_35_total": int(30000 + frac * 80000),
        "vacancies_per_10k_youth": round(50 + frac * 150, 2),
        "occupation_shannon_index": round(2.5 + frac * 1.5, 2),
        "talent_demand_yoy": round(-10 + frac * 20, 2),
        "salary_median": int(28000 + frac * 12000),
        "high_salary_ratio": round(0.02 + frac * 0.08, 4),
        "adjusted_youth_wage": round(50 + frac * 40, 2),
        "college_student_density": round(frac * 5000, 2),
        "vt_course_count": int(frac * 40),
        "training_people_per_10k_youth": round(frac * 40, 2),
        "rent_median": int(12000 + frac * 15000),
        "house_price_median": round(300000 + frac * 400000, 2),
        "rent_wage_ratio": round(0.3 + frac * 0.4, 4),
        "bus_stops_per_10k_youth": round(50 + frac * 150, 2),
        "railway_stop_density": round(frac * 1.0, 4),
        "bike_stop_density": round(frac * 15, 2),
        "opportunityIndex": opportunity_index,
        "yoiComponents": {
            "job": job, "salary": salary, "talent": talent,
            "housing": housing, "transport": transport,
        },
        "retentionRiskLevel": _retention_risk(i),
        "fertilityRate": round(12.67 + frac * (74.92 - 12.67), 2),
        "fertilityVsCityAvg": round(49.63 + frac * (293.51 - 49.63), 2),
        "serviceCoverageRate": SERVICE_COVERAGE_OVERRIDES.get(district_id, 0.0),
        "serviceCoverageStatus": "partial",
        "youthCandidacyRatePer100k": candidacy_rate,
        "youthParticipationIndex": candidacy_rate,
        "youthBoroughChiefRatioPercent": borough_chief_ratio,
        "qualityStatus": "observed",
        "sourcePeriods": {},
    }


TEST_DISTRICTS = [_build_district(i, did, name) for i, (did, name) in enumerate(DISTRICTS)]
TOTAL_YOUTH_18_35 = sum(d["youth_18_35_total"] for d in TEST_DISTRICTS)


def _build_kpis():
    return {
        "nationalYouthPopulation": 4820000,
        "nationalYouthPopulationQuality": "proxy",
        "cityYouthPopulationShare": 20.914,
        "cityYouthPopulation": 845938,
        "cityYouthPopulationYoY": -1.969,
        "referenceYearRoc": 114,
    }


def _build_population_years():
    years = [110, 111, 112, 113, 114]
    city_start, city_end = 913345, 845938
    share_start, share_end = 22.79, 20.91
    out = []
    for idx, yr in enumerate(years):
        t = idx / (len(years) - 1)
        city_pop = round(city_start + (city_end - city_start) * t)
        share = round(share_start + (share_end - share_start) * t, 2)
        districts = []
        for d in TEST_DISTRICTS:
            scaled = round(d["youth_18_35_total"] * (city_pop / TOTAL_YOUTH_18_35))
            districts.append({
                "district_id": d["district_id"],
                "district_name": d["district_name"],
                "youth_population": scaled,
                "youth_share_percent": share,
            })
        out.append({
            "year_roc": yr,
            "city": {"youth_population": city_pop, "youth_share_percent": share},
            "districts": districts,
        })
    return out


def _build_fertility_years():
    years = [110, 111, 112, 113, 114]
    births_start, births_end = 17645, 10489
    rate_start, rate_end = 39.39, 25.53
    quality_by_year = {110: "observed", 111: "observed", 112: "observed", 113: "partial", 114: "observed"}
    out = []
    for idx, yr in enumerate(years):
        t = idx / (len(years) - 1)
        city_births = round(births_start + (births_end - births_start) * t)
        city_rate = round(rate_start + (rate_end - rate_start) * t, 2)
        districts = []
        for d in TEST_DISTRICTS:
            d_rate = round(d["fertilityRate"] * (city_rate / rate_end), 2)
            d_births = round(city_births * (d["youth_18_35_total"] / TOTAL_YOUTH_18_35))
            districts.append({
                "district_id": d["district_id"],
                "district_name": d["district_name"],
                "births_mother_age_18_35": d_births,
                "fertility_rate": d_rate,
                "quality_status": quality_by_year[yr],
            })
        out.append({
            "year_roc": yr,
            "city": {
                "births_mother_age_18_35": city_births,
                "fertility_rate": city_rate,
                "quality_status": quality_by_year[yr],
            },
            "districts": districts,
        })
    return out


def _build_borough_chief_citywide():
    latest = [row for row in BOROUGH_CHIEF_ROWS if row["year_roc"] == 111]
    elected_count = sum(row["elected_count"] for row in latest)
    youth_elected_count = sum(row["youth_elected_count"] for row in latest)
    return {
        "year_roc": 111,
        "elected_count": elected_count,
        "youth_elected_count": youth_elected_count,
        "ratio_percent": round(youth_elected_count / elected_count * 100, 2) if elected_count else None,
    }


def _build_elections():
    citywide = [
        {"year_roc": 103, "youth_candidacy_rate": None, "quality_status": "unavailable"},
        {"year_roc": 107, "youth_candidacy_rate": None, "quality_status": "unavailable"},
        {"year_roc": 111, "youth_candidacy_rate": 1.674, "quality_status": "observed"},
    ]
    return {
        "city_councilor_t1_citywide": citywide,
        "borough_chief_v1": BOROUGH_CHIEF_ROWS,
        "borough_chief_v1_citywide": _build_borough_chief_citywide(),
    }


def _build_service_coverage():
    return {
        "value": 49.23, "status": "partial", "radius_m": 2500,
        "verified_point_count": 9, "excluded_point_count": 0,
        "population_coverage_ratio": 0.9933,
        "boundary_village_count": 1039, "joined_village_count": 1032,
        "blocking_reasons": [],
    }


def _build_policy():
    return {
        "currentBudget": 196153,
        "budgetUnit": "TWD_thousand",
        "budgetYoY": 23.639,
        "executionRate": None,
        "executionFailure": "final_settlement_unavailable",
        "budgetTrend": [
            {"year_roc": 110, "value_thousand": None},
            {"year_roc": 111, "value_thousand": None},
            {"year_roc": 112, "value_thousand": 149029},
            {"year_roc": 113, "value_thousand": 158650},
            {"year_roc": 114, "value_thousand": 196153},
        ],
    }


AVAILABILITY = {
    "opportunityIndex": "available",
    "fertility": "available",
    "youthParticipationIndex": "available",
    "serviceCoverage": "partial",
    "budget": "partial",
}


def _analysis_employment_scatter():
    knowledge_points, wage_housing_points = [], []
    for d in TEST_DISTRICTS:
        knowledge_ratio = round(min(100.0, d["vacancies_per_10k_youth"] / 2), 2)
        est_wage_annual = d["adjusted_youth_wage"]
        est_wage_monthly = round(est_wage_annual / 12, 2)
        house_wan = round(d["house_price_median"] / 10000, 2)
        knowledge_points.append({
            "district_id": d["district_id"], "district_name": d["district_name"],
            "x": knowledge_ratio, "y": est_wage_annual,
        })
        wage_housing_points.append({
            "district_id": d["district_id"], "district_name": d["district_name"],
            "x": est_wage_monthly, "y": house_wan,
        })
    return {
        "analysis_id": "employment-scatter",
        "geo_level": "district",
        "plots": [
            {
                "id": "knowledge-wage",
                "title": "起薪與知識型職缺密度相關性（各行政區）",
                "x_label": "知識型職缺比例（%）",
                "y_label": "估算起薪（萬元／年）",
                "points": knowledge_points,
                "regression": {"slope": 0.0, "intercept": 0.0, "r_squared": 0.0},
                "note": "test data，X 軸為職缺要求大專以上學歷的比例，非居住人口教育程度",
            },
            {
                "id": "wage-housing",
                "title": "房價與平均薪資關聯（各行政區）",
                "x_label": "青年平均月薪（萬元）",
                "y_label": "每坪平均房價（萬元）",
                "points": wage_housing_points,
                "regression": {"slope": 0.0, "intercept": 0.0, "r_squared": 0.0},
                "note": "test data，薪資為房價代理估算值",
            },
        ],
        "limitations": ["test data - job_vacancies 僅示意"],
    }


# 青年局各科別預算比例：organization/county 層級的決算科別拆分，不可分攤到 29 區，
# 見 api_contract.md §6.3。科別名稱與比例待青年局提供真實決算後取代。
DEPARTMENT_BUDGET = [
    {"label": "綜合規劃", "amount_thousand": 68654, "share_percent": 35.0},
    {"label": "職涯發展", "amount_thousand": 58846, "share_percent": 30.0},
    {"label": "創業資源", "amount_thousand": 39231, "share_percent": 20.0},
    {"label": "資本門設備與投資", "amount_thousand": 29423, "share_percent": 15.0},
]

TOPIC_LABELS = ["社會住宅", "青年就業", "青年創業", "托育資源", "交通建設"]
LATEST_TOPIC_YEAR_ROC = 114


def _analysis_youth_topic_weight():
    topics = []
    for idx, label in enumerate(TOPIC_LABELS):
        weight = 1 + (idx + LATEST_TOPIC_YEAR_ROC) % 5
        topics.append({
            "label": label, "weight": weight, "signal": "minutes",
            "join_mentions": 0, "minutes_mentions": weight,
            "resolved": weight >= 3, "escalated": False,
            "join_support_score": 0.0, "raw_score": float(weight),
        })
    return {"analysis_id": "youth-topic-weight", "year_roc": LATEST_TOPIC_YEAR_ROC, "topics": topics}


def _analysis_fertility_overlay():
    points = [
        {
            "district_id": d["district_id"], "district_name": d["district_name"],
            "x": d["opportunityIndex"], "y": d["fertilityRate"],
        }
        for d in TEST_DISTRICTS
    ]
    return {
        "analysis_id": "fertility-overlay", "geo_level": "district",
        "points": points, "regression": {"slope": 0.0, "intercept": 0.0, "r_squared": 0.0},
    }


def _analysis_fertility_family_friendliness():
    items = []
    for d in TEST_DISTRICTS:
        score = round((d["yoiComponents"]["housing"] + min(100.0, d["adjusted_youth_wage"])) / 2, 2)
        level = "high" if score >= 70 else "medium" if score >= 50 else "low"
        items.append({
            "district_id": d["district_id"], "district_name": d["district_name"],
            "fafi_score": score, "fafi_level": level,
        })
    return {"analysis_id": "fertility-family-friendliness", "geo_level": "district", "districts": items}


def _analysis_policy_outcomes():
    wage_trend = [
        {"year_roc": yr, "wage": None, "yoy": None, "quality_status": "observed"}
        for yr in (110, 111, 112, 113)
    ]
    return {
        "analysis_id": "policy-outcomes",
        "geo_level": "county",
        "wageTrend": wage_trend,
        "currentWageGrowth": 2.8,
        "currentPopGrowth": -1.969,
        # 語意固定、非資料：薪資成長「越高越好」、青年人口成長「下滑才是警訊」，
        # 兩者期望方向皆為 up。見 api_contract.md §8.1。
        "desiredDirection": {"wageGrowth": "up", "populationChange": "up"},
    }


def _to_decimal(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_decimal(v) for v in value]
    return value


def build_items() -> list[dict]:
    """One dict per DynamoDB item, `pk`/`sk` included. See dynamodb_schema.md."""
    manifest = {
        "pk": "META",
        "sk": "MANIFEST",
        "snapshot_id": SNAPSHOT_ID,
        "generated_at": GENERATED_AT,
        "calculation_version": "test",
        "districts_count": len(DISTRICTS),
        "time_policy": {
            "annual_years_roc": [110, 111, 112, 113, 114],
            "election_years_roc": [103, 107, 111],
        },
        "quality": {"status": "test"},
        "warnings": [],
    }

    dashboard_items = [
        {"pk": "DASHBOARD", "sk": "KPIS", "kpis": _build_kpis(), "availability": AVAILABILITY},
        {"pk": "DASHBOARD", "sk": "POLICY", **_build_policy()},
        {"pk": "DASHBOARD", "sk": "SERVICE_COVERAGE", **_build_service_coverage()},
        {"pk": "DASHBOARD", "sk": "ELECTIONS", **_build_elections()},
        {"pk": "DASHBOARD", "sk": "POPULATION_TREND", "years": _build_population_years()},
        {"pk": "DASHBOARD", "sk": "FERTILITY_TREND", "years": _build_fertility_years()},
        {"pk": "DASHBOARD", "sk": "DISTRICTS", "districts": TEST_DISTRICTS},
    ]

    district_items = [
        {"pk": f"DISTRICT#{d['district_id']}", "sk": "SUMMARY", **d} for d in TEST_DISTRICTS
    ]

    # politics-resource-io and policy-outcomes deliberately drop the fields
    # dynamodb_schema.md says are reused from DASHBOARD/POLICY and
    # DASHBOARD/POPULATION_TREND at read time instead of duplicated here.
    analysis_items = [
        {"pk": "ANALYSIS#employment-scatter", "sk": "DATA", **_analysis_employment_scatter()},
        {"pk": "ANALYSIS#politics-resource-io", "sk": "DATA", "budget_by_department": DEPARTMENT_BUDGET},
        {"pk": "ANALYSIS#youth-topic-weight", "sk": "DATA", **_analysis_youth_topic_weight()},
        {"pk": "ANALYSIS#fertility-overlay", "sk": "DATA", **_analysis_fertility_overlay()},
        {"pk": "ANALYSIS#fertility-family-friendliness", "sk": "DATA", **_analysis_fertility_family_friendliness()},
        {"pk": "ANALYSIS#policy-outcomes", "sk": "DATA", **_analysis_policy_outcomes()},
    ]

    return [manifest, *dashboard_items, *district_items, *analysis_items]


def seed(table_name: str, region: str) -> int:
    import boto3

    table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    items = build_items()
    manifest = next(i for i in items if i["pk"] == "META")
    rest = [i for i in items if i["pk"] != "META"]

    with table.batch_writer() as batch:
        for item in rest:
            batch.put_item(Item=_to_decimal(item))

    # META/MANIFEST last, per dynamodb_schema.md's write contract -- readers
    # use it to judge freshness, so it shouldn't point at a half-written table.
    table.put_item(Item=_to_decimal(manifest))

    return len(items)


def _demo() -> None:
    items = build_items()
    assert len(items) == 1 + 7 + 29 + 6, len(items)

    keys = {(i["pk"], i["sk"]) for i in items}
    for expected in [
        ("META", "MANIFEST"),
        ("DASHBOARD", "DISTRICTS"),
        ("DISTRICT#65000010", "SUMMARY"),
        ("ANALYSIS#policy-outcomes", "DATA"),
    ]:
        assert expected in keys, expected

    def _has_float(value: Any) -> bool:
        if isinstance(value, float):
            return True
        if isinstance(value, dict):
            return any(_has_float(v) for v in value.values())
        if isinstance(value, list):
            return any(_has_float(v) for v in value)
        return False

    for item in items:
        assert not _has_float(_to_decimal(item)), item["pk"]

    print(f"ok — {len(items)} items")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-name", default=os.environ.get("ANALYTICS_TABLE_NAME"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--self-check", action="store_true", help="validate build_items() locally, no AWS calls")
    args = parser.parse_args()

    if args.self_check:
        _demo()
        return

    if not args.table_name:
        parser.error("--table-name is required (or set ANALYTICS_TABLE_NAME)")

    count = seed(args.table_name, args.region)
    print(f"wrote {count} items to {args.table_name}")


if __name__ == "__main__":
    main()
