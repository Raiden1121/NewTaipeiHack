# 18–35 歲新北市資料清理與標準化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可測試的 Python transform layer，將現有 collectors 的原始資料清理、標準化、對齊新北市 29 區與資料期間，並正確標示 18–35 歲資料口徑。

**Architecture:** 保留 `collectors` 的來源請求與原始欄位，在 `data-pipeline/src/transform/` 建立共用解析工具、行政區 resolver、資料集專屬 transform、品質報告與本地 JSON 輸出。先完成「人口 + 遷徙」vertical slice，再依同一 contract 擴充出生、婚姻、房價、租金、職缺、薪資、教育、訓練與 TDX；正式統計指標留在 `analytics/`。

**Tech Stack:** Python 3.11+、standard library、JSON、現有 `unittest`；空間 point-in-polygon 以 boundary adapter 封裝，只有實作 TDX 空間 task 時加入必要幾何套件。

**Spec:** `data-pipeline/data-pipeline.md` and the approved requirements in the implementation request

## Global Constraints

- 年齡範圍固定為 18–35 歲，包含 18 與 35。
- 可精確判斷年齡的資料才可標記 `exact_18_35` 或 `derived_18_35`。
- 沒有年齡欄位的資料保留為 `not_age_specific` 或 `all_ages`，只能作背景指標。
- 官方年齡組不得自行拼成 18–35 歲；只能標記 `official_age_group_proxy`。
- 核心青年指標只接受 `youth_eligibility=eligible`；`proxy_only` 與 `context_only` 不得當作青年樣本。
- 缺失值輸出為 JSON `null`，不得以 0 代替。
- Collector 原始欄位保留；canonical 欄位另行新增，不覆寫原始值。
- 行政區 join key 為 `district_id`，時間 join key 為 `period`；兩者在可比較資料上共同形成 `district_id + period`。
- 無法可靠對應行政區或期間時保留 `null`，並記錄 quality warning 或 quarantine。
- Transform 不呼叫外部 API、不計算跨主題指標、不修改現有 collector 的 public API。
- 每個新增 transform 行為先建立 failing test，再實作最小程式使測試通過。

## Canonical Record Contract

每筆 curated record 必須保留下列 common metadata；彙總資料另外使用 `metric_id`、`value`、`unit`，交易、事件與站點資料則保留各自的 canonical domain fields：

```text
dataset
source
source_record_id
geo_level                 # district | county | national
district_id               # string or null
district_name             # string or null
period_start              # ISO date or null
period_end                # ISO date or null
period_type               # day | month | year | snapshot or null
metric_id                 # string or null for observation records
value                     # number or null for metric records
unit                      # explicit canonical unit or null
age_scope                # exact_18_35 | derived_18_35 | official_age_group_proxy | all_ages | not_age_specific
age_min                  # integer or null
age_max                  # integer or null
youth_eligibility        # eligible | proxy_only | context_only
fetched_at               # ISO timestamp or null
quality_flags            # list[str]
```

Aggregated population output must use separate records for `people_total` and `youth_18_35_total`, because one record-level `age_scope` cannot describe both all-ages and 18–35 values.

---

### Task 1: 建立共用 transform contract、解析工具與品質報告

**Files:**
- Create: `data-pipeline/src/transform/__init__.py`
- Create: `data-pipeline/src/transform/contracts.py`
- Create: `data-pipeline/src/transform/common.py`
- Create: `data-pipeline/src/transform/quality.py`
- Create: `data-pipeline/tests/test_transform_common.py`
- Create: `data-pipeline/tests/test_transform_quality.py`

**Interfaces:**
- `TransformResult(records: list[dict[str, Any]], quality: dict[str, Any], quarantine: list[dict[str, Any]])`
- `clean_text(value: Any) -> str | None`
- `parse_int(value: Any, *, field: str, allow_none: bool = True) -> int | None`
- `parse_decimal(value: Any, *, field: str, allow_none: bool = True) -> float | None`
- `parse_roc_year(value: Any, *, field: str) -> str`
- `parse_roc_month(value: Any, *, field: str) -> str`
- `parse_roc_date(value: Any, *, field: str) -> str | None`
- `build_common_metadata(*, dataset: str, source: str, source_record_id: str | None, geo_level: str, district_id: str | None, district_name: str | None, period_start: str | None, period_end: str | None, period_type: str | None, metric_id: str | None, value: int | float | None, unit: str | None, age_scope: str, age_min: int | None, age_max: int | None, youth_eligibility: str, fetched_at: str | None, quality_flags: list[str] | None = None) -> dict[str, Any]`
- `QualityCollector.finish() -> dict[str, Any]`

- [ ] **Step 1: Write failing parser tests.**

```python
def test_clean_text_normalizes_full_width_whitespace(self):
    self.assertEqual(clean_text("　板橋區  "), "板橋區")

def test_parse_int_handles_commas_and_missing_tokens(self):
    self.assertEqual(parse_int("1,234", field="people"), 1234)
    self.assertIsNone(parse_int("面議", field="salary"))

def test_parse_roc_date_returns_iso_date(self):
    self.assertEqual(parse_roc_date("1140521", field="date"), "2025-05-21")
```

- [ ] **Step 2: Run the parser tests and verify they fail because transform modules do not exist.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_common -v`

Expected: collection fails with an import error for the missing transform module.

- [ ] **Step 3: Implement the minimal parser and metadata contract.**

  Normalize text with Unicode NFKC and whitespace stripping. Treat `""`, `"-"`, `"—"`, `"－"`, `"NA"`, `"N/A"`, `"無"`, and `"面議"` as missing. Keep identifiers as strings, reject booleans for numeric fields, and reject negative values for counts and monetary amounts.

- [ ] **Step 4: Add quality and quarantine tests, then implement them.**

  `QualityCollector` must track `rows_in`, `rows_out`, `rows_rejected`, `duplicate_count`, `unmapped_district_count`, `numeric_parse_errors`, `missing_value_count`, `warnings`, and `reject_reasons`. Every quarantine item contains `input_index`, `raw_record`, and `reason`.

- [ ] **Step 5: Run focused tests and commit.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_common tests.test_transform_quality -v`

Expected: all focused tests pass with no live API calls.

Commit: `git add data-pipeline/src/transform/__init__.py data-pipeline/src/transform/contracts.py data-pipeline/src/transform/common.py data-pipeline/src/transform/quality.py data-pipeline/tests/test_transform_common.py data-pipeline/tests/test_transform_quality.py && git commit -m "feat(pipeline): add transform contracts and quality reporting"`

### Task 2: 建立新北市 29 區 canonical resolver

**Files:**
- Create: `data-pipeline/config/districts.json`
- Create: `data-pipeline/src/transform/geography.py`
- Create: `data-pipeline/tests/test_transform_geography.py`
- Reference: `frontend/public/Map_NewTaipei.json`

**Interfaces:**
- `DistrictResolver.from_json(path: str | Path) -> DistrictResolver`
- `DistrictResolver.districts -> list[dict[str, Any]]`
- `DistrictResolver.resolve_name(value: Any) -> tuple[str, str] | None`
- `DistrictResolver.resolve_code(value: Any) -> tuple[str, str] | None`
- `DistrictResolver.resolve_zip(value: Any) -> tuple[str, str] | None`
- `DistrictResolver.resolve_point(latitude: float, longitude: float) -> tuple[str, str] | None`

- [ ] **Step 1: Write tests for the 29 canonical districts.**

  Build the mapping from the 29 `id`/`name` pairs in `Map_NewTaipei.json`. Assert `len(resolver.districts) == 29`, `新北市板橋區` and `板橋區` both resolve to `("65000010", "板橋區")`, and an unknown name returns `None`.

- [ ] **Step 2: Run the geography tests and verify they fail before the resolver exists.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_geography -v`

Expected: import or attribute failure caused by the missing resolver implementation.

- [ ] **Step 3: Implement name, official-code and postal-code lookup.**

  Store postal codes as strings. Use explicit aliases from `districts.json`; do not blindly slice an official code unless the resulting prefix is verified against the canonical mapping.

- [ ] **Step 4: Add the spatial boundary adapter.**

  Use the existing `frontend/public/Map_NewTaipei.json` `objects.map` geometry as the initial boundary source, convert its 29 TopoJSON features through a dedicated adapter, and keep the resolver independent from React. `resolve_point` returns a district only when exactly one boundary contains the WGS84 point. Outside or ambiguous points return `None` and are counted as unmapped; no nearest-district fallback is allowed.

- [ ] **Step 5: Run tests and commit.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_geography -v`

Expected: 29 district IDs, known aliases, postal codes, and unknown values behave deterministically.

Commit: `git add data-pipeline/config/districts.json data-pipeline/src/transform/geography.py data-pipeline/tests/test_transform_geography.py && git commit -m "feat(pipeline): add New Taipei district resolver"`

### Task 3: 完成人口與遷徙第一個 vertical slice

**Files:**
- Create: `data-pipeline/src/transform/population.py`
- Create: `data-pipeline/src/transform/mobility.py`
- Create: `data-pipeline/tests/test_transform_population.py`
- Create: `data-pipeline/tests/test_transform_mobility.py`
- Reference: `data-pipeline/src/collectors/population_collector.py`
- Reference: `data-pipeline/src/collectors/moving_in.py`

**Interfaces:**
- `transform_population(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`
- `transform_movement(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`

- [ ] **Step 1: Write failing tests for inclusive 18–35 population aggregation.**

  Use raw rows containing age 17, 18, 35, and 36. Assert that only 18 and 35 enter `youth_18_35_total`. Output `people_total` and `youth_18_35_total` as separate metric records so each has its own age scope.

```python
def test_population_includes_18_and_35_but_excludes_17_and_36(self):
    result = transform_population(self.raw_rows, resolver=self.resolver)
    youth = next(row for row in result.records if row["metric_id"] == "youth_18_35_total")
    total = next(row for row in result.records if row["metric_id"] == "people_total")
    self.assertEqual(youth["value"], 5)
    self.assertEqual(youth["age_scope"], "derived_18_35")
    self.assertEqual(total["age_scope"], "all_ages")
```

- [ ] **Step 2: Run the population tests and verify the expected missing-module failure.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_population -v`

Expected: failure because `transform_population` has not been implemented.

- [ ] **Step 3: Implement population transformation.**

  Convert source numeric strings, resolve `site_id`, group by `district_id + statistic_yyymm`, and produce metric records for `people_total`, `youth_18_35_male`, `youth_18_35_female`, and `youth_18_35_total`. Set `geo_level="district"`, `period_type="month"`, and preserve source village IDs in `source_record_ids`.

- [ ] **Step 4: Write and run movement tests before implementing movement.**

  Assert that movement records use `age_scope="all_ages"`, `youth_eligibility="context_only"`, and never expose a youth movement metric. Verify that missing `in_total` or `out_total` produces `net_movement_total=null` plus a quality warning.

- [ ] **Step 5: Implement movement transformation.**

  Convert `in_*`, `out_*`, and source/destination fields to numeric metrics, aggregate village rows by district and month, and calculate net movement only when both operands are present.

- [ ] **Step 6: Run the vertical-slice tests and commit.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_population tests.test_transform_mobility -v`

Expected: 18 and 35 are included, 17 and 36 are excluded, movement is explicitly all-ages context, and missing values remain `None`.

Commit: `git add data-pipeline/src/transform/population.py data-pipeline/src/transform/mobility.py data-pipeline/tests/test_transform_population.py data-pipeline/tests/test_transform_mobility.py && git commit -m "feat(pipeline): transform youth population and mobility data"`

### Task 4: 加入出生與婚姻的年齡及期間標準化

**Files:**
- Create: `data-pipeline/src/transform/life_events.py`
- Create: `data-pipeline/tests/test_transform_life_events.py`
- Reference: `data-pipeline/src/collectors/birth_nums.py`
- Reference: `data-pipeline/src/collectors/marriage_nums.py`

**Interfaces:**
- `transform_births(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`
- `transform_marriages(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`

- [ ] **Step 1: Test birth age parsing and total-sex precedence.**

  Include `18歲`, `35歲`, `36歲`, male/female rows, and a `總計` row. Assert that only mother ages 18–35 are included and a total-sex row prevents double counting.

- [ ] **Step 2: Implement birth transformation.**

  Set `age_scope="exact_18_35"`, `age_min=18`, `age_max=35`, `youth_eligibility="eligible"`, aggregate by district and ROC year, and preserve `according` as provenance.

- [ ] **Step 3: Test and implement marriage transformation.**

  Convert village monthly values to annual district metrics, reject duplicate `(statistic_yyymm, site_id, village)` rows, and set `age_scope="all_ages"`, `youth_eligibility="context_only"`. Do not call the output youth marriage counts.

- [ ] **Step 4: Run tests and commit.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_life_events -v`

Expected: birth output is exact 18–35, marriage output is all-ages context, and duplicate rows are quarantined or reported.

Commit: `git add data-pipeline/src/transform/life_events.py data-pipeline/tests/test_transform_life_events.py && git commit -m "feat(pipeline): standardize youth life-event data"`

### Task 5: 標準化房價、租金、職缺與薪資

**Files:**
- Create: `data-pipeline/src/transform/housing.py`
- Create: `data-pipeline/src/transform/labor.py`
- Create: `data-pipeline/tests/test_transform_housing.py`
- Create: `data-pipeline/tests/test_transform_labor.py`
- Reference: `data-pipeline/src/collectors/house_price.py`
- Reference: `data-pipeline/src/collectors/rental_price.py`
- Reference: `data-pipeline/src/collectors/job_vacancy.py`
- Reference: `data-pipeline/src/collectors/job_vacancy_salary.py`
- Reference: `data-pipeline/src/collectors/wage.py`

**Interfaces:**
- `transform_house_prices(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`
- `transform_rentals(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`
- `transform_job_vacancies(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`
- `transform_wages(records: Iterable[Mapping[str, Any]], *, fetched_at: str | None = None) -> TransformResult`

- [ ] **Step 1: Test shared null, unit and ROC-date rules.**

  Assert that `面議` becomes `None`, original source values remain unchanged, ping/square-metre fields retain explicit units, and ROC transaction dates become ISO dates.

- [ ] **Step 2: Implement house-price and rental transforms.**

  Consume the canonical fields already produced by the existing collectors, resolve district and period, preserve transaction-level rows, and set `age_scope="not_age_specific"`, `youth_eligibility="context_only"`. Do not calculate medians or YoY here.

- [ ] **Step 3: Test and implement job vacancy snapshot semantics.**

  Preserve `snapshot_fetched_at`; turn `query_truncated=true` into a quality warning; name `JOB_PERSON` as a position count; and convert non-date closing values such as `額滿為止` to `null`.

- [ ] **Step 4: Implement posted-salary and official-wage transforms.**

  Keep salary bounds, midpoint and estimate type. Preserve official wage age groups and units. Mark posted vacancies as `not_age_specific/context_only` and official grouped wages as `official_age_group_proxy/proxy_only`; never fabricate a 18–35 wage value.

- [ ] **Step 5: Run tests and commit.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_housing tests.test_transform_labor -v`

Expected: housing and labor records retain raw values, nulls, units, snapshot warnings and non-exact age labels.

Commit: `git add data-pipeline/src/transform/housing.py data-pipeline/src/transform/labor.py data-pipeline/tests/test_transform_housing.py data-pipeline/tests/test_transform_labor.py && git commit -m "feat(pipeline): standardize housing and labor data"`

### Task 6: 標準化教育、訓練與人才需求

**Files:**
- Create: `data-pipeline/src/transform/education.py`
- Create: `data-pipeline/src/transform/training.py`
- Create: `data-pipeline/tests/test_transform_education.py`
- Create: `data-pipeline/tests/test_transform_training.py`
- Reference: `data-pipeline/src/collectors/college_major.py`
- Reference: `data-pipeline/src/collectors/graduate_major.py`
- Reference: `data-pipeline/src/collectors/vt_course.py`
- Reference: `data-pipeline/src/collectors/training_nums.py`
- Reference: `data-pipeline/src/collectors/talent_demand.py`

**Interfaces:**
- `transform_college_majors(overview_records: Iterable[Mapping[str, Any]], detail_records: Iterable[Mapping[str, Any]] | None = None, *, fetched_at: str | None = None) -> TransformResult`
- `transform_graduate_majors(records: Iterable[Mapping[str, Any]], *, fetched_at: str | None = None) -> TransformResult`
- `transform_vt_courses(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`
- `transform_training_numbers(records: Iterable[Mapping[str, Any]], *, fetched_at: str | None = None) -> TransformResult`
- `transform_talent_demand(records: Iterable[Mapping[str, Any]], *, fetched_at: str | None = None) -> TransformResult`

- [ ] **Step 1: Test the 9621/9622 join contract.**

  Join by academic year, school code, department code, day/evening, level, county and system. Normalize codes only for the join key, retain source codes, and keep unmatched 9622 rows with a warning instead of filling zero.

- [ ] **Step 2: Implement education transforms.**

  Convert student and graduate counts to numeric values, preserve classification codes/names, and keep 9620 records at `geo_level="national"` because that source has no reliable county or school location. Mark these records `proxy_only` or `context_only`, not exact youth observations.

- [ ] **Step 3: Test and implement training/course semantics.**

  Count distinct `課程編號`, never sum `數量` as course count. Preserve county-only training as `geo_level="county"`; use district only when `訓練區域` or a verified address provides it. Normalize dates, hours, fees and people counts.

- [ ] **Step 4: Implement national talent-demand transformation.**

  Normalize `統計期`, occupation labels and numeric demand/hire fields. Keep the source at `geo_level="national"`; do not assign it to New Taipei districts.

- [ ] **Step 5: Run tests and commit.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_education tests.test_transform_training -v`

Expected: joins, unmatched rows, source geography levels and distinct-course behavior pass.

Commit: `git add data-pipeline/src/transform/education.py data-pipeline/src/transform/training.py data-pipeline/tests/test_transform_education.py data-pipeline/tests/test_transform_training.py && git commit -m "feat(pipeline): standardize education and training data"`

### Task 7: 加入 TDX 站點與行政區空間標準化

**Files:**
- Create: `data-pipeline/src/transform/transport.py`
- Create: `data-pipeline/tests/test_transform_transport.py`
- Modify: `data-pipeline/requirements.txt` only when the spatial adapter requires a new dependency
- Reference: `data-pipeline/src/collectors/bus_stop.py`
- Reference: `data-pipeline/src/collectors/railway_stop.py`
- Reference: `data-pipeline/src/collectors/bike_stop.py`

**Interfaces:**
- `transform_bus_stops(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`
- `transform_railway_stops(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`
- `transform_bike_stops(records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver, fetched_at: str | None = None) -> TransformResult`

- [ ] **Step 1: Write tests for nested TDX fields and coordinates.**

  Assert that `StopPosition.PositionLat` and `PositionLon` become numeric `latitude` and `longitude`, invalid coordinates are quarantined, and `Operators`, `Availability`, `line_ids`, and `line_nos` remain arrays or null.

- [ ] **Step 2: Implement station normalization.**

  Use `StopUID` or `StationUID` as string IDs, normalize Chinese/English names, preserve static and live fields separately, and set `age_scope="not_age_specific"`, `youth_eligibility="context_only"`.

- [ ] **Step 3: Implement verified point-in-polygon assignment.**

  Assign a district only for exactly one containing boundary. Outside or ambiguous coordinates keep `district_id=null` and increment the unmapped quality count; never use nearest-district fallback.

- [ ] **Step 4: Run tests and commit.**

Run: `cd data-pipeline && python -m unittest tests.test_transform_transport -v`

Expected: coordinate validation, nested fields, static/live separation and district assignment are deterministic.

Commit: `git add data-pipeline/src/transform/transport.py data-pipeline/tests/test_transform_transport.py data-pipeline/requirements.txt && git commit -m "feat(pipeline): standardize TDX transport data"`

### Task 8: 建立 raw／curated／quality／quarantine 的本地 pipeline

**Files:**
- Create: `data-pipeline/src/transform/pipeline.py`
- Create: `data-pipeline/src/transform/io.py`
- Create: `data-pipeline/tests/test_transform_pipeline.py`
- Modify: `data-pipeline/src/run_pipeline.py`
- Modify: `data-pipeline/data-pipeline.md`
- Create: `data-pipeline/src/transform/transform.md`

**Interfaces:**
- `run_transform(dataset: str, records: Iterable[Mapping[str, Any]], *, resolver: DistrictResolver | None = None, fetched_at: str | None = None) -> TransformResult`
- `write_raw(payload: Mapping[str, Any], *, dataset: str, snapshot: str, output_dir: str | Path) -> Path`
- `write_curated(result: TransformResult, *, dataset: str, output_dir: str | Path) -> tuple[Path, Path, Path]`
- `main(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Write failing dispatch and output tests.**

  Assert that `run_transform("population", records, resolver=resolver)` dispatches to population, an unknown dataset returns a clear error, and `write_curated` writes curated, quality and quarantine JSON files.

- [ ] **Step 2: Implement explicit dataset dispatch.**

  Use a static dictionary of supported dataset names to transform callables. Load the default resolver from `config/districts.json` when a dataset needs geography; do not dynamically import arbitrary user input.

- [ ] **Step 3: Implement local file outputs.**

  Write `data/raw/{dataset}/{snapshot}.json`, `data/curated/{dataset}.json`, `data/quality/{dataset}.json`, and `data/quarantine/{dataset}.json`. Curated output contains `dataset`, `generated_at`, and `records`; quality output contains the complete quality report; quarantine contains input index, raw record and rejection reason. Use atomic temporary-file replacement.

- [ ] **Step 4: Add the CLI without moving transformation logic into it.**

  `run_pipeline.py` accepts `--dataset`, `--input`, `--output-dir`, and `--config-dir`. It reads a previously saved raw JSON envelope and calls `run_transform`; it must not silently fetch live data when `--input` is absent.

- [ ] **Step 5: Document the contract and age/geography rules.**

  Update `data-pipeline.md` and add `transform.md` covering common metadata, exact inclusive 18–35 behavior, proxy/context labels, `district/county/national` levels, null semantics, output paths and local commands.

- [ ] **Step 6: Run full verification and commit.**

Run:

```bash
cd data-pipeline
python -m unittest discover -s tests -v
python -m py_compile src/transform/*.py src/run_pipeline.py
```

Expected: all existing collector tests and transform tests pass, compilation exits 0, and a deterministic population raw fixture produces curated, quality and quarantine output.

Commit: `git add data-pipeline/src/transform/pipeline.py data-pipeline/src/transform/io.py data-pipeline/src/run_pipeline.py data-pipeline/data-pipeline.md data-pipeline/src/transform/transform.md data-pipeline/tests/test_transform_pipeline.py && git commit -m "feat(pipeline): orchestrate curated youth data transforms"`

## Acceptance Criteria

- Population output contains separate `people_total` and `youth_18_35_total` metric records; 18 and 35 are included, 17 and 36 are excluded.
- Birth output is based on mother age 18–35 and avoids double counting total-sex rows.
- Movement and marriage are clearly labelled all-ages context data.
- Official wage age groups remain proxies; no fabricated exact 18–35 wage exists.
- Housing, transport and current vacancies are not labelled as exact youth samples.
- Reliable sources resolve to canonical New Taipei district IDs; unresolved locations remain null and visible in quality reports.
- County and national sources retain their original `geo_level` instead of being artificially split into 29 districts.
- Raw source values remain available, standardized values are typed, and missing values serialize as `null`.
- Transform does not contain YoY, median, correlation, Opportunity Index or Retention Risk calculations.
