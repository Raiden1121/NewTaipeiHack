# Population Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個使用戶政司 ODRP014 API、可抓取指定民國年月新北市村里原始人口資料的 Python collector，並完成資料格式文件。

**Architecture:** `population_collector.py` 只負責來源請求、年月與回應驗證、API 分頁及原始資料合併；不做 18–35 歲統計、不寫入檔案。後續 pipeline 可直接使用 `fetch_population()` 的村里記錄，再由 transform／analytics layer 轉換。

**Tech Stack:** Python 3.10+、Python standard library `urllib.request`／`urllib.parse`／`json`、`unittest`。

**Spec:** `docs/superpowers/specs/2026-08-30-population-collector-design.md`

## Global Constraints

- API endpoint 固定使用 `https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP014/{yyyymm}`。
- `yyyymm` 為必填的 5 位數民國年月字串，例如 `11507`；月份必須為 `01` 至 `12`。
- 預設查詢 `COUNTY=新北市`，可選擇 `TOWN`。
- 回傳 ODRP014 `responseData` 的原始村里資料與字串值。
- 以 `totalPage` 控制分頁，不以篩選後可能不準確的 `totalDataSize` 推算頁數。
- 不新增第三方套件，不修改 `run_pipeline.py`，不在 collector 內寫檔或計算指標。

---

### Task 1: Define failing collector behavior tests

**Files:**
- Create: `data-pipeline/tests/test_population_collector.py`

**Interfaces:**
- Consumes: planned `collectors.population_collector.fetch_population` and `PopulationCollectorError`.
- Produces: executable regression cases for validation, pagination, query parameters, and API error handling.

- [ ] **Step 1: Write the failing tests**

Create a standard-library test module that places `data-pipeline/src` on `sys.path`, supplies a fake `urlopen` context manager, and verifies behavior rather than implementation details:

```python
class TestFetchPopulation(unittest.TestCase):
    def test_merges_all_pages_for_new_taipei(self):
        responses = {
            1: {
                "responseCode": "OD-0101-S",
                "totalPage": "2",
                "responseData": [{"site_id": "新北市板橋區", "village": "留侯里"}],
            },
            2: {
                "responseCode": "OD-0101-S",
                "totalPage": "2",
                "responseData": [{"site_id": "新北市板橋區", "village": "流芳里"}],
            },
        }
        records = fetch_population("11507", open_url=fake_open_url(responses))
        self.assertEqual(records, [
            {"site_id": "新北市板橋區", "village": "留侯里"},
            {"site_id": "新北市板橋區", "village": "流芳里"},
        ])

    def test_sends_county_and_optional_town_query_parameters(self):
        requests = []
        responses = {1: success_page(total_page=1, records=[])}
        records = fetch_population(
            "11507",
            county="新北市",
            town="板橋區",
            open_url=fake_open_url(responses, requests),
        )
        self.assertEqual(records, [])
        self.assertIn("COUNTY=%E6%96%B0%E5%8C%97%E5%B8%82", requests[0].full_url)
        self.assertIn("TOWN=%E6%9D%BF%E6%A9%8B%E5%8D%80", requests[0].full_url)

    def test_rejects_invalid_roc_month(self):
        with self.assertRaises(PopulationCollectorError):
            fetch_population("202607", open_url=fake_open_url({}))

    def test_raises_for_unsuccessful_api_response(self):
        responses = {1: {"responseCode": "OD-0102-S", "responseMessage": "查無資料"}}
        with self.assertRaises(PopulationCollectorError):
            fetch_population("11507", open_url=fake_open_url(responses))
```

The test helper must return a response object whose `read()` returns JSON bytes and whose `Request.full_url` can be inspected. It must also model the `urlopen` context-manager protocol.

- [ ] **Step 2: Run tests to verify they fail for the missing implementation**

Run:

```bash
PYTHONPATH=data-pipeline/src python3 -m unittest discover -s data-pipeline/tests -v
```

Expected: collection fails because `collectors.population_collector` and its public interface do not exist yet.

### Task 2: Implement the ODRP014 collector

**Files:**
- Create: `data-pipeline/src/collectors/population_collector.py`

**Interfaces:**
- Consumes: ODRP014 JSON pages and optional `county`／`town` values.
- Produces: `fetch_population(yyyymm, county="新北市", town=None, *, open_url=urlopen) -> list[dict[str, str]]` and `PopulationCollectorError`.

- [ ] **Step 1: Implement input validation and URL construction**

Use a five-digit ROC date check with a numeric month range. Build URLs through `urllib.parse.urlencode`, starting with `PAGE=1` and `COUNTY`, and add `TOWN` only when a non-empty town is provided.

- [ ] **Step 2: Implement one-page request and response validation**

Use `urllib.request.Request` with an `Accept: application/json` header and a fixed 30-second timeout. Convert `HTTPError`, `URLError`, `TimeoutError`, and JSON decode failures into `PopulationCollectorError`. Require `responseCode == "OD-0101-S"`, a positive integer `totalPage`, and a list-valued `responseData` whose record keys and values are strings.

- [ ] **Step 3: Implement sequential pagination and raw record merge**

Fetch pages `2..totalPage` using the same filters, append each page's `responseData` in order, and return the merged list. Do not cast values, deduplicate rows, write files, or calculate age metrics in this layer.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
PYTHONPATH=data-pipeline/src python3 -m unittest discover -s data-pipeline/tests -v
```

Expected: all collector tests pass with no network access.

### Task 3: Document the source and returned data

**Files:**
- Modify: `data-pipeline/src/collectors/data.md`

**Interfaces:**
- Consumes: the public `fetch_population()` contract and an actual `ODRP014/11507?PAGE=1&COUNTY=新北市` response.
- Produces: Chinese-first documentation that allows another developer to reproduce the request and understand the raw record shape.

- [ ] **Step 1: Document request examples and response envelope**

Document the endpoint, ROC month format, default New Taipei filter, optional town filter, pagination fields, success code, and the returned `responseData` list.

- [ ] **Step 2: Add five actual 11507 sample rows**

Include a compact table with `statistic_yyymm`, `district_code`, `site_id`, `village`, household count, total population, male/female total, and selected age fields from five actual rows. Explain that the complete record also contains every single-age male/female field.

- [ ] **Step 3: Document downstream calculation boundaries and caveats**

Explain that 18–35 calculations sum `people_age_018_m` through `people_age_035_m` and the corresponding `_f` fields after numeric conversion in a later transform layer. Record that API values are strings, one month is one endpoint call, pages are sequential, and filtered responses may retain the unfiltered `totalDataSize` metadata.

### Task 4: Verify against the live official API and review the diff

**Files:**
- Verify: `data-pipeline/src/collectors/population_collector.py`
- Verify: `data-pipeline/src/collectors/data.md`
- Verify: `data-pipeline/tests/test_population_collector.py`

**Interfaces:**
- Consumes: the implemented collector and official ODRP014 endpoint.
- Produces: evidence that the collector handles the current 11507 New Taipei response and preserves the existing untracked scaffold files.

- [ ] **Step 1: Run the complete local test command**

Run:

```bash
PYTHONPATH=data-pipeline/src python3 -m unittest discover -s data-pipeline/tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Run a live collector smoke check for 11507**

Run a read-only command that calls `fetch_population("11507")` and prints the record count, distinct `site_id` count, and first record's core fields. Expected output is 1,039 records and 29 distinct New Taipei districts for the current source snapshot.

- [ ] **Step 3: Check syntax and repository scope**

Run:

```bash
python3 -m py_compile data-pipeline/src/collectors/population_collector.py
git status --short
git diff -- data-pipeline/src/collectors/population_collector.py data-pipeline/src/collectors/data.md data-pipeline/tests/test_population_collector.py
```

Confirm that `run_pipeline.py` and unrelated existing files are unchanged, and report any pre-existing untracked files separately.
