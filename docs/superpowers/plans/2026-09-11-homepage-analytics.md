# Homepage Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 依照首頁設計規格，產生 110–114 年年度指標、最新快照 29 區 YOI、選舉事件指標，以及可驗證的青創基地服務涵蓋率資料。

**Architecture:** 保持 collector → transform → analytics 分層。Collector 只抓官方來源與保留原始欄位；transform 產生可被 analytics 直接讀取的 district、village、boundary 與 geocode 欄位；analytics 透過明確的年度／快照選擇器跨資料集計算，最後寫入 `analytics/homepage/all.json` 與品質報告。

**Tech Stack:** Python 3、既有 JSON pipeline、`shapely` 2.x、`pyproj` 3.x、`pyshp` 2.x、官方新北市門牌座標資料、國土測繪中心村里界 SHP、`unittest`／既有測試工具。

**Spec:** [`docs/superpowers/specs/2026-09-11-homepage-analytics-design.md`](../specs/2026-09-11-homepage-analytics-design.md)

## Global Constraints

- 年度輸出固定以 ROC 110–114 為主；ROC 109 只作 ROC 110 YoY 的比較基準。
- YOI 只計算最新可得快照，不把快照回填成歷史年度，也不產生 YOI YoY。
- 選舉只處理 2014／2018／2022 的 T1 與 V1；T1 保留選舉區，不硬套 29 區。
- 沒有可驗證座標的服務據點排除，不當作 0 覆蓋；輸出排除數量與 `partial` 狀態。
- `population` 現有 29 區輸出維持相容；里級人口新增為獨立 `population_villages` dataset。
- 里界保存 polygon geometry；不以 centroid 或單一經緯度取代里界面積。
- Collector／transform 不計算首頁指標；analytics 不讀 raw artifact 代替 curated dataset。
- 不自動 `git add`、commit、merge 或 push。

---

### Task 1: 建立年度與快照輸入選擇器

**Files:**

- Create: `data-pipeline/src/analytics/input_resolver.py`
- Modify: `data-pipeline/src/analytics/io.py`
- Modify: `data-pipeline/src/analytics/config.py`
- Create: `data-pipeline/config/homepage_analytics.json`
- Test: `data-pipeline/tests/test_analytics_input_resolver.py`

**Interfaces:**

- `HomepageAnalyticsConfig` dataclass fields: `version`, `annual_years_roc`, `population_reference_year_roc`, `election_years_roc`, `service_radius_m`, `normalization`, and `yoi_weights`.
- `CuratedSlice(dataset: str, period_type: str, source_periods: tuple[str, ...], records: tuple[dict[str, Any], ...], paths: tuple[str, ...])`
- `load_curated_period(dataset, period, *, output_dir) -> CuratedSlice`
- `load_curated_periods(dataset, periods, *, output_dir) -> CuratedSlice`
- `load_latest_snapshot(dataset, *, output_dir) -> CuratedSlice`
- `load_homepage_analytics_config(path) -> HomepageAnalyticsConfig`

- [x] **Step 1: 寫 period loader 的失敗測試**

  測試明確期間會讀取 `curated/{dataset}/{period}.json`，不存在時拋出包含 dataset／period／path 的 `ValueError`；禁止 `..` 或絕對路徑逃逸 output directory。

- [x] **Step 2: 寫 snapshot loader 與年度範圍測試**

  使用假的 `dataset_index.json` 測試 `load_latest_snapshot()` 只讀 index 指定的 curated path；測試 `load_curated_periods()` 保留來源期間順序與每個檔案的 row count。

- [x] **Step 3: 實作 resolver 與設定載入**

  `homepage_analytics.json` 固定放入：

  ```json
  {
    "version": "1",
    "annual_years_roc": [110, 111, 112, 113, 114],
    "population_reference_year_roc": 114,
    "election_years_roc": [103, 107, 111],
    "service_radius_m": 2500,
    "normalization": {"method": "p5_p95", "constant_value": 50},
    "yoi_weights": {
      "job": 0.25,
      "salary": 0.25,
      "talent": 0.05,
      "housing": 0.25,
      "transport": 0.20
    }
  }
  ```

  Resolver 只讀 curated JSON 與 dataset index，不掃 raw 目錄，也不進行網路抓取。

- [x] **Step 4: 執行 resolver 單元測試**

  Run:

  ```bash
  cd data-pipeline
  python -m unittest tests.test_analytics_input_resolver -v
  ```

  Expected: all tests pass。

---

### Task 2: 新增里級青年人口 curated dataset

**Files:**

- Create: `data-pipeline/src/transform/population_villages.py`
- Modify: `data-pipeline/src/transform/pipeline.py`
- Modify: `data-pipeline/src/run_pipeline.py`
- Modify: `data-pipeline/config/refresh_profiles.json`
- Create: `data-pipeline/tests/test_transform_population_villages.py`
- Test: `data-pipeline/tests/test_transform_pipeline.py`

**Interfaces:**

- `transform_population_villages(records, *, resolver, fetched_at=None) -> TransformResult`
- `CollectorSpec("population_villages", lambda period: fetch_population(period, county="新北市"), PeriodStrategy.MONTHLY)`

- [x] **Step 1: 寫里級彙總測試**

  使用兩個村里的 raw records，驗證輸出每里一筆，包含：

  ```text
  geo_level="village"
  village_code
  village_name
  district_id
  district_name
  period_start / period_end
  people_total
  youth_18_35_female
  youth_18_35_male
  youth_18_35_total
  ```

  驗證缺任一年齡欄位時，該里青年數為 `null` 並進入 quality warning，不把缺值當 0。

- [x] **Step 2: 實作獨立 transform**

  重用 `transform/population.py` 的 `parse_roc_month`、`parse_int` 與 `DistrictResolver`；不要改變既有 `population` 的 29 區輸出。

- [x] **Step 3: 註冊資料集**

  在 pipeline registry 與 refresh profile 加入 `population_villages`。它與 `population` 使用同一個 ODRP014 collector，但保存不同 curated path：

  ```text
  data/curated/population_villages/{yyyMM}.json
  data/quality/population_villages/{yyyMM}.json
  ```

- [x] **Step 4: 執行 transform 與 registry 測試**

  ```bash
  cd data-pipeline
  python -m unittest tests.test_transform_population_villages tests.test_transform_pipeline -v
  ```

  Expected: 原有 `population` 測試不變，新增 dataset 可被 `canonicalize_dataset()` 與 `run_transform()` 找到。

---

### Task 3: 新增官方村里界資料集

**Files:**

- Create: `data-pipeline/src/collectors/village_boundaries.py`
- Create: `data-pipeline/src/transform/village_boundaries.py`
- Modify: `data-pipeline/src/transform/pipeline.py`
- Modify: `data-pipeline/src/run_pipeline.py`
- Modify: `data-pipeline/config/refresh_profiles.json`
- Modify: `data-pipeline/requirements.txt`
- Create: `data-pipeline/tests/test_village_boundaries.py`

**Interfaces:**

- `fetch_village_boundaries(*, open_url=_open_url) -> CollectedPayload`
- `transform_village_boundaries(records, *, fetched_at=None) -> TransformResult`

- [x] **Step 1: 定義官方來源與 raw artifact**

  使用國土測繪中心的 `村(里)界(TWD97_121分帶).zip`，下載完整 SHP 壓縮檔，保存 SourceArtifact、SHA-256、來源 URL 與抓取時間；transform 只保留新北市代碼 `65`。

- [x] **Step 2: 寫 geometry 驗證測試**

  用測試用 Polygon／MultiPolygon fixture 驗證：

  - `village_code` 取自 `ADMIV_ID`；
  - `district_id` 取自 `ADMIT_ID`；
  - geometry 保留 polygon；
  - CRS 明確為 `EPSG:3826`；
  - 空 geometry、未知行政區、重複里代碼進 quarantine。

- [x] **Step 3: 加入最小空間依賴**

  在 `requirements.txt` 加入：

  ```text
  pyshp>=2.3,<3
  shapely>=2.0,<3
  pyproj>=3.6,<4
  ```

  不加入 `geopandas`，避免引入額外 GDAL／系統依賴。

- [x] **Step 4: 實作 collector、transform 與 pipeline registry**

  輸出：

  ```text
  data/curated/village_boundaries/latest.json
  data/quality/village_boundaries/latest.json
  data/raw/village_boundaries/artifacts/*.zip
  ```

- [x] **Step 5: 執行空間資料測試**

  ```bash
  cd data-pipeline
  python -m unittest tests.test_village_boundaries -v
  ```

---

### Task 4: 對有地址的青創基地補座標

**Files:**

- Create: `data-pipeline/src/collectors/ntpc_address_points.py`
- Modify: `data-pipeline/src/collectors/youth_service_points.py`
- Modify: `data-pipeline/src/transform/service_points.py`
- Create: `data-pipeline/tests/test_ntpc_address_points.py`
- Modify: `data-pipeline/tests/test_youth_service_points.py`

**Interfaces:**

- `AddressMatchResult` dataclass fields: `matches`, `metadata`, and `artifacts`.
- `match_ntpc_address_points(addresses, *, open_url=_open_url) -> AddressMatchResult`
- `AddressMatchResult.matches: list[dict[str, Any]]`
- `AddressMatchResult.metadata: dict[str, Any]`
- `AddressMatchResult.artifacts: tuple[SourceArtifact, ...]`

- [x] **Step 1: 寫地址標準化與唯一匹配測試**

  使用官方新北市門牌位置資料的欄位 `street`、`road`、`section`、`lane`、`alley`、`number`、`x_3826`、`y_3826` 建立比對鍵；測試全形空白、標點、`之` 號格式統一，以及 0 筆／多筆匹配都不能自動猜測。

- [x] **Step 2: 實作官方地址座標 lookup**

  使用新北市政府民政局「新北市門牌位置數值資料」作為來源。只接受唯一匹配，輸出：

  ```text
  geocode_status = "matched"
  geocode_provider = "ntpc_address_points"
  geocode_crs = "EPSG:3826"
  x_3826
  y_3826
  longitude
  latitude
  geocode_source_period
  ```

  `x_3826`／`y_3826` 直接作為 spatial analytics 的點；`longitude`／`latitude` 由 `pyproj` 轉成 WGS84，供地圖顯示。無地址或無唯一匹配的 6 筆保留原始資料，狀態設為 `excluded_no_verified_coordinate`。

- [x] **Step 3: 將 lookup 結果併回 service-point collector/transform**

  不刪除原始 9 筆；只新增 geocode 欄位與 source metadata。analytics 只選 `geocode_status="matched"` 的點。

- [x] **Step 4: 執行測試**

  ```bash
  cd data-pipeline
  python -m unittest tests.test_ntpc_address_points tests.test_youth_service_points -v
  ```

  Expected: 測試確認無座標據點不會被轉成座標 0，也不會被錯配到青年局辦公室地址。

---

### Task 5: 實作服務涵蓋率 spatial analytics

**Files:**

- Create: `data-pipeline/src/analytics/service_coverage.py`
- Create: `data-pipeline/tests/test_service_coverage.py`

**Interface:**

```python
def calculate_service_coverage(
    service_points: Iterable[Mapping[str, Any]],
    village_boundaries: Iterable[Mapping[str, Any]],
    village_population: Iterable[Mapping[str, Any]],
    *,
    radius_m: float = 2500,
) -> dict[str, Any]:
    ...
```

- [x] **Step 1: 寫幾何測試 fixture**

  建立兩個相鄰測試里 polygon、一個有效服務點與一個無座標服務點；驗證無座標點被排除，結果含 `excluded_point_count`。

- [x] **Step 2: 寫面積分攤預期值測試**

  在 EPSG:3826 幾何中建立已知交集比例，驗證：

  ```text
  covered_youth(village) = intersection_area_ratio * youth_18_35_total
  district_rate = sum(covered_youth) / sum(youth_18_35_total) * 100
  ```

  重疊 buffer 必須先 `unary_union`，避免同一里被多個據點重複計算。

- [x] **Step 3: 實作輸入驗證與狀態**

  - `matched` 點先轉成 EPSG:3826；
  - polygon 以 `village_code` join 人口；
  - 缺里界或缺里級人口時回傳 `value=null` 與 blocking reasons；
  - 有有效點但排除其他點時回傳 `status="partial"`；
  - 沒有有效點時回傳 `status="unavailable"`。

- [x] **Step 4: 執行測試**

  ```bash
  cd data-pipeline
  python -m unittest tests.test_service_coverage -v
  ```

---

### Task 6: 實作 YOI 基礎數學函式

**Files:**

- Create: `data-pipeline/src/analytics/homepage_math.py`
- Create: `data-pipeline/tests/test_homepage_math.py`

**Interfaces:**

- `normalize_p5_p95(values, *, inverse=False, constant_value=50) -> dict[str, float]`
- `shannon_entropy(category_counts) -> float`
- `calculate_quartile_risk(scores) -> dict[str, str]`
- `weighted_score(parts, weights) -> float`

- [x] **Step 1: 寫 P5/P95、反向與常數欄位測試**

  驗證極端值 clipping、`norm_inv=100-norm`、全部相同時為 50，以及 `None` 不會變成 NaN。

- [x] **Step 2: 寫 Shannon 與四分位測試**

  驗證單一職業 entropy 為 0、多職業依比例計算，以及 Q1/Q3 的 `high`／`medium`／`low` 邊界。

- [x] **Step 3: 實作純函式**

  這些函式不得讀檔、抓網路或依賴 dataset-specific 欄位，讓 YOI 與其他 analytics 可重用。

- [x] **Step 4: 執行測試**

  ```bash
  cd data-pipeline
  python -m unittest tests.test_homepage_math -v
  ```

---

### Task 7: 實作選舉與年度首頁指標

**Files:**

- Create: `data-pipeline/src/analytics/elections.py`
- Create: `data-pipeline/src/analytics/annual_metrics.py`
- Create: `data-pipeline/tests/test_homepage_elections.py`
- Create: `data-pipeline/tests/test_homepage_annual_metrics.py`

**Interfaces:**

- `calculate_youth_candidacy(records, population_records, *, election_years_roc) -> dict[str, Any]`
- `calculate_annual_population(population_by_period, *, annual_years_roc) -> dict[str, Any]`
- `calculate_annual_fertility(birth_records, population_by_month, *, annual_years_roc) -> dict[str, Any]`
- `calculate_budget_series(budget_records, settlement_records, *, annual_years_roc) -> dict[str, Any]`

- [x] **Step 1: 寫選舉 grain 測試**

  驗證 T1 輸出含 `election_district_code` 且 `district_id=null`；V1 可按 29 區彙總；候選人年齡依投票日與出生日期／年次判定；公式為每十萬青年人口。

- [x] **Step 2: 寫年度生育率與月份覆蓋測試**

  使用 12 個月與缺 1 個月 fixture，驗證分母為可用月份的女性 18–35 歲人口平均，並輸出 `available_months`／`coverage_ratio`。

- [x] **Step 3: 寫預算狀態測試**

  驗證只取 ROC 110–114 的 `row_type=total` 法定預算；預算案不與法定預算混算；決算缺解析資料時 `execution_rate=null`；可解析時使用 `realized_amount / legal_budget_amount`。

- [x] **Step 4: 實作年度與選舉 analytics**

  2014／2018／2022 作為 event periods；年度輸出固定 `[110, 111, 112, 113, 114]`，ROC 109 只作 ROC 110 YoY 基準。

- [x] **Step 5: 執行測試**

  ```bash
  cd data-pipeline
  python -m unittest tests.test_homepage_elections tests.test_homepage_annual_metrics -v
  ```

---

### Task 8: 整合 homepage analytics 與 CLI

**Files:**

- Create: `data-pipeline/src/analytics/homepage.py`
- Modify: `data-pipeline/src/analytics/io.py`
- Modify: `data-pipeline/src/run_analytics.py`
- Modify: `data-pipeline/data/data_description.md`
- Modify: `docs/homepage_analysis.md`
- Create: `data-pipeline/tests/test_homepage_analytics.py`
- Create: `data-pipeline/tests/test_run_analytics.py`

**Interfaces:**

- `generate_homepage_data(*, resolver, config) -> dict[str, Any]`
- `write_homepage_data(result, *, output_dir) -> tuple[Path, Path]`

- [x] **Step 1: 寫整合 fixture 測試**

  準備 29 區 fixture 與各資料集來源期間，驗證輸出包含：

  ```text
  current_yoi.districts: 29 rows
  annual.population: ROC 110–114
  annual.fertility: ROC 110–114
  annual.budget_trend: ROC 110–114 only
  elections.city_councilor_t1: election-district grain
  elections.borough_chief_v1: district grain
  service_coverage: value/status/blocking reasons
  ```

- [x] **Step 2: 實作 YOI 29 區計算**

  依 spec 加入工作、薪資、人才、居住、交通五個子指數；套用 salary、VT、租金、房價、大專與交通缺值規則；保留每個子指標的 source periods 與 quality metadata。

- [x] **Step 3: 實作輸出與品質檔**

  寫入：

  ```text
  data/analytics/homepage/all.json
  data/quality/analytics_homepage.json
  ```

  使用既有 `atomic_json_write()`，禁止輸出 NaN／Infinity。

- [x] **Step 4: 擴充 CLI**

  `run_analytics.py` 的 `--metric` 加入 `homepage`，並加入：

  ```text
  --annual-start-roc 110
  --annual-end-roc 114
  --population-reference-roc 114
  ```

  `homepage` 分支不得先載入 `join_proposals` 或 `youth_council_minutes`。

- [x] **Step 5: 更新文件**

  `homepage_analysis.md` 補上 current snapshot YOI／annual 110–114 的區分、服務據點排除規則、里級資料集與座標流程；`data_description.md` 加入 `population_villages`、`village_boundaries` 與 geocode 欄位範例。

- [x] **Step 6: 執行整合測試**

  ```bash
  cd data-pipeline
  python -m unittest tests.test_homepage_analytics tests.test_run_analytics -v
  ```

---

### Task 9: 真實資料刷新與驗證

**Files:**

- Modify only generated outputs under `data-pipeline/data/` during the run。
- Review: `data-pipeline/data/quality/analytics_homepage.json`
- Review: `data-pipeline/data/quality/dataset_index.json`

- [x] **Step 1: 先抓 110–114 的人口／里級人口與年度來源**

  ```bash
  data-pipeline/.venv/bin/python data-pipeline/src/run_pipeline.py \
    --start-period 11001 --end-period 11412 \
    --datasets population,population_villages,births,wages,college_majors \
    --output-dir data-pipeline/data \
    --config-dir data-pipeline/config \
    --force
  ```

  檢查 110–114 的來源檔、11308 缺月狀態、里級筆數與 quality quarantine。

- [x] **Step 2: 抓快照與空間資料**

  ```bash
  data-pipeline/.venv/bin/python data-pipeline/src/run_pipeline.py \
    --start-period 11509 --end-period 11509 \
    --datasets youth_service_points,village_boundaries,job_vacancies,job_vacancy_salaries,house_prices,rentals,bus_stops,railway_stops,bike_stops,vt_courses,training_numbers \
    --output-dir data-pipeline/data \
    --config-dir data-pipeline/config \
    --force
  ```

  檢查 geocode 成功數、排除數、里界 geometry 筆數與 EPSG metadata。

- [x] **Step 3: 補抓 110–114 預算並保留決算 failure**

  執行 `youth_budgets` refresh，確認 110–114 法定預算資料是否存在；111／112 影像決算若仍無法解析，保留 artifact 與 failure，不填入執行率。

- [x] **Step 4: 執行首頁 analytics**

  ```bash
  PYTHONPATH=data-pipeline/src \
    data-pipeline/.venv/bin/python data-pipeline/src/run_analytics.py \
    --metric homepage \
    --annual-start-roc 110 \
    --annual-end-roc 114 \
    --population-reference-roc 114 \
    --output-dir data-pipeline/data \
    --config-dir data-pipeline/config
  ```

- [x] **Step 5: 驗收實際輸出**

  檢查：

  - `current_yoi.districts` 正好 29 筆；
  - annual years 正好 110–114；
  - budget trend 沒有 115／116；
  - 服務涵蓋率記錄有效點、排除點、里界與里級人口覆蓋率；
  - T1 沒有被賦予單一 `district_id`；
  - 沒有 NaN／Infinity；
  - `analytics_homepage.json` 能追溯所有 source periods、proxy 與 failure。

- [x] **Step 6: 執行完整回歸測試**

  ```bash
  cd data-pipeline
  python -m unittest discover -s tests -p 'test_*.py' -v
  ```

  Expected: 全部既有測試與新增首頁 analytics 測試通過；若 live source 的資料筆數或 geocode 結果變動，只更新 quality report，不修改公式讓測試迎合資料。

---

## 完成後的交付物

1. `data/analytics/homepage/all.json`：首頁可讀的年度、快照、選舉與服務涵蓋結果。
2. `data/quality/analytics_homepage.json`：輸入期間、筆數、proxy、排除與 failure。
3. `population_villages` curated dataset：里級青年人口。
4. `village_boundaries` curated dataset：新北市里界 polygon。
5. 更新後的 `data_description.md` 與 `homepage_analysis.md`。
6. 可重跑、可測試、可用實際資料驗證的 `run_analytics.py --metric homepage`。

## 執行順序

先完成 Task 1–4 的資料契約與來源，再完成 Task 5–8 的 analytics，最後執行 Task 9 真實資料刷新。沒有完成里級人口、里界或有效服務點時，首頁其他指標仍可先產出，只有 `service_coverage` 保持 `null`／`unavailable` 或 `partial`。
