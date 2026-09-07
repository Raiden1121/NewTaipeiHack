# Data Pipeline Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 timeout、no-data、birth schema、TaiwanJobs geography 與 wage-year 錯誤，並建立 source-aware scheduling 與只重跑失敗資料的 resume 流程。

**Architecture:** `run_pipeline.py` 保持 CLI／orchestration entrypoint，但 period planning、retry 與 resume state 拆到 `orchestration/`。Collectors 以共用 exception taxonomy 表達 no-data；每個 dataset 由 `CollectorSpec.period_strategy` 決定 monthly、annual、snapshot 或 all-available 執行單位。既有 raw 優先重用，新下載只發生在 raw 缺失或明確要求 `--force` 時。

**Tech Stack:** Python 3 standard library、`unittest`、local JSON、existing urllib collectors

**Spec:** `docs/superpowers/specs/2026-09-02-data-pipeline-recovery-design.md`

## Global Constraints

- 青年核心資料維持 18–35 歲且包含 18、35。
- 缺失值維持 JSON `null`，不得改成 0。
- `新北市不限` 維持 county-level，不得猜測行政區。
- Retry 僅限 transient timeout，最多 3 attempts，backoff 1 秒、2 秒。
- No-data 不計入 errors，不觸發 `--strict` failure。
- Snapshot 與 all-available sources 不得複製成每月歷史資料。
- 不自動刪除既有 raw、curated 或 quality files。
- 測試不得呼叫 live API。

---

## File Structure

### New files

- `data-pipeline/src/collectors/errors.py`: shared collector no-data exception.
- `data-pipeline/src/orchestration/__init__.py`: orchestration public exports.
- `data-pipeline/src/orchestration/contracts.py`: period strategy, collector spec, execution unit, retry result.
- `data-pipeline/src/orchestration/retry.py`: timeout detection and bounded retry.
- `data-pipeline/src/orchestration/schedule.py`: source-aware execution-unit planning.
- `data-pipeline/src/orchestration/state.py`: report lookup, raw reuse decisions, authoritative dataset index.
- `data-pipeline/tests/test_orchestration_retry.py`: retry behavior.
- `data-pipeline/tests/test_orchestration_schedule.py`: execution frequencies.
- `data-pipeline/tests/test_orchestration_state.py`: resume and index behavior.

### Modified files

- `data-pipeline/src/run_pipeline.py`: registry metadata, CLI flags, execution/recovery flow, terminal progress.
- `data-pipeline/src/collectors/population_collector.py`: no-data taxonomy.
- `data-pipeline/src/collectors/moving_in.py`: no-data taxonomy.
- `data-pipeline/src/collectors/birth_nums.py`: no-data taxonomy and Chinese field aliases.
- `data-pipeline/src/collectors/marriage_nums.py`: no-data taxonomy.
- `data-pipeline/src/collectors/job_vacancy.py`: county-wide rows and deduplication metadata.
- `data-pipeline/src/collectors/wage.py`: unavailable-year taxonomy and fail-fast behavior.
- `data-pipeline/src/transform/labor.py`: county-level vacancy transform.
- `data-pipeline/src/transform/io.py`: authoritative index writer.
- Relevant existing collector and transform tests.
- `data-pipeline/data-pipeline.md` and `data-pipeline/src/transform/transform.md`: corrected commands and output contract.

---

### Task 1: Collector No-Data Taxonomy

**Files:**
- Create: `data-pipeline/src/collectors/errors.py`
- Modify: `data-pipeline/src/collectors/population_collector.py`
- Modify: `data-pipeline/src/collectors/moving_in.py`
- Modify: `data-pipeline/src/collectors/birth_nums.py`
- Modify: `data-pipeline/src/collectors/marriage_nums.py`
- Modify: `data-pipeline/src/collectors/wage.py`
- Test: `data-pipeline/tests/test_population_collector.py`
- Test: `data-pipeline/tests/test_moving_in.py`
- Test: `data-pipeline/tests/test_birth_nums.py`
- Test: `data-pipeline/tests/test_marriage_nums.py`
- Test: `data-pipeline/tests/test_wage.py`

**Interfaces:**
- Produces: `class CollectorNoDataError(RuntimeError)`.
- Consumes later: `run_pipeline.py` catches `CollectorNoDataError` and emits `skipped/no_data`.

- [ ] **Step 1: Add failing household no-data tests**

Change the existing `OD-0102-S` tests to assert the shared type while preserving collector-specific context:

```python
from collectors.errors import CollectorNoDataError

def test_reports_no_data_separately(self):
    responses = {1: {"responseCode": "OD-0102-S", "responseMessage": "查無資料"}}
    with self.assertRaises(CollectorNoDataError):
        fetch_population("11507", open_url=fake_open_url(responses))
```

Add equivalent tests for movement, births and marriages. For marriages, assert that one unavailable required month raises `CollectorNoDataError`, not an incomplete annual record.

- [ ] **Step 2: Add failing wage unavailable-year test**

```python
from collectors.errors import CollectorNoDataError

def test_missing_requested_year_stops_without_trying_fallback_format(self):
    calls = []
    with self.assertRaises(CollectorNoDataError):
        wage.fetch_wage(year="115", cache_dir=None, open_url=fake_table6_source(calls))
    self.assertEqual(calls.count("spreadsheet"), 1)
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
python3 -m unittest \
  data-pipeline/tests/test_population_collector.py \
  data-pipeline/tests/test_moving_in.py \
  data-pipeline/tests/test_birth_nums.py \
  data-pipeline/tests/test_marriage_nums.py \
  data-pipeline/tests/test_wage.py
```

Expected: import or assertion failures because `CollectorNoDataError` does not exist.

- [ ] **Step 4: Implement the shared error and exact no-data branches**

```python
# collectors/errors.py
class CollectorNoDataError(RuntimeError):
    """The source responded successfully but has no data for the requested period."""
```

In each household `_parse_page()`:

```python
if response_code == "OD-0102-S":
    raise CollectorNoDataError(
        f"{dataset_code} has no data for {period} page {page}: {message}"
    )
```

In wage sheet selection:

```python
raise CollectorNoDataError(
    f"Table 6 does not contain year {requested_year}; available years: {available}"
)
```

In `fetch_wage()`, re-raise `CollectorNoDataError` before the generic `WageCollectorError` fallback handler.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the command from Step 3. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data-pipeline/src/collectors/errors.py \
  data-pipeline/src/collectors/population_collector.py \
  data-pipeline/src/collectors/moving_in.py \
  data-pipeline/src/collectors/birth_nums.py \
  data-pipeline/src/collectors/marriage_nums.py \
  data-pipeline/src/collectors/wage.py \
  data-pipeline/tests/test_population_collector.py \
  data-pipeline/tests/test_moving_in.py \
  data-pipeline/tests/test_birth_nums.py \
  data-pipeline/tests/test_marriage_nums.py \
  data-pipeline/tests/test_wage.py
git commit -m "fix(pipeline): classify unavailable source periods"
```

---

### Task 2: Timeout Retry

**Files:**
- Create: `data-pipeline/src/orchestration/__init__.py`
- Create: `data-pipeline/src/orchestration/contracts.py`
- Create: `data-pipeline/src/orchestration/retry.py`
- Create: `data-pipeline/tests/test_orchestration_retry.py`

**Interfaces:**
- Produces: `RetryResult(value: Any, attempts: int)`.
- Produces: `collect_with_retry(operation: Callable[[], Any], *, max_attempts: int = 3, sleep: Callable[[float], None] = time.sleep, on_retry: Callable[[int, BaseException], None] | None = None) -> RetryResult`.
- Produces: `is_timeout_error(exc: BaseException) -> bool`.

- [ ] **Step 1: Write failing retry-success test**

```python
def test_retries_two_timeouts_then_returns_success(self):
    attempts = 0
    delays = []

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            try:
                raise TimeoutError("read timed out")
            except TimeoutError as exc:
                raise RuntimeError("collector request failed") from exc
        return ["record"]

    result = collect_with_retry(operation, sleep=delays.append)
    self.assertEqual(result.value, ["record"])
    self.assertEqual(result.attempts, 3)
    self.assertEqual(delays, [1.0, 2.0])
```

- [ ] **Step 2: Write failing non-timeout test**

```python
def test_does_not_retry_validation_error(self):
    attempts = 0
    def operation():
        nonlocal attempts
        attempts += 1
        raise ValueError("schema mismatch")
    with self.assertRaises(ValueError):
        collect_with_retry(operation, sleep=lambda _: None)
    self.assertEqual(attempts, 1)
```

- [ ] **Step 3: Write failing exhausted-timeout test**

Assert three calls, delays `[1.0, 2.0]`, and the final wrapped collector exception is re-raised.

- [ ] **Step 4: Run test and verify RED**

```bash
python3 -m unittest data-pipeline/tests/test_orchestration_retry.py
```

Expected: import failure because `orchestration.retry` does not exist.

- [ ] **Step 5: Implement minimal retry code**

```python
@dataclass(frozen=True)
class RetryResult:
    value: Any
    attempts: int

def collect_with_retry(operation, *, max_attempts=3, sleep=time.sleep, on_retry=None):
    for attempt in range(1, max_attempts + 1):
        try:
            return RetryResult(operation(), attempt)
        except Exception as exc:
            if not is_timeout_error(exc) or attempt == max_attempts:
                raise
            if on_retry is not None:
                on_retry(attempt + 1, exc)
            sleep(float(2 ** (attempt - 1)))
    raise AssertionError("unreachable")
```

`is_timeout_error()` must walk `exc`, `exc.__cause__`, and `exc.__context__`; accept `TimeoutError`, `socket.timeout`, and `URLError` whose reason is timeout. Message matching is allowed only as a final compatibility fallback for existing wrapped collectors.

- [ ] **Step 6: Run focused tests and verify GREEN**

```bash
python3 -m unittest data-pipeline/tests/test_orchestration_retry.py
```

- [ ] **Step 7: Commit**

```bash
git add data-pipeline/src/orchestration data-pipeline/tests/test_orchestration_retry.py
git commit -m "feat(pipeline): retry transient collection timeouts"
```

---

### Task 3: Birth Field Aliases

**Files:**
- Modify: `data-pipeline/src/collectors/birth_nums.py`
- Test: `data-pipeline/tests/test_birth_nums.py`

**Interfaces:**
- Produces unchanged `fetch_birth_numbers(...) -> list[dict[str, str]]`.
- Returned rows preserve Chinese source keys and add canonical keys required by transform.

- [ ] **Step 1: Add failing Chinese-field response test**

```python
def test_accepts_113_chinese_source_fields_and_adds_canonical_aliases(self):
    source = {
        "統計年度": "113", "按照別": "按發生日期分", "區域別": "新北市板橋區",
        "生母年齡": "18歲", "出生者性別": "男", "嬰兒出生數": "2",
    }
    records = birth_nums.fetch_birth_numbers(
        "113", open_url=fake_open_url({1: success_page(source)})
    )
    self.assertEqual(records[0]["mother_age"], "18歲")
    self.assertEqual(records[0]["birth_count"], "2")
    self.assertEqual(records[0]["區域別"], "新北市板橋區")
```

- [ ] **Step 2: Run test and verify RED**

```bash
python3 -m unittest data-pipeline/tests/test_birth_nums.py
```

Expected: missing canonical fields.

- [ ] **Step 3: Implement canonical alias enrichment**

Define an exact mapping and copy each source record before adding aliases:

```python
FIELD_ALIASES = {
    "statistic_yyy": "統計年度",
    "according": "按照別",
    "site_id": "區域別",
    "mother_age": "生母年齡",
    "birth_sex": "出生者性別",
    "birth_count": "嬰兒出生數",
}
```

Canonical keys already present take precedence. Validate after enrichment.

- [ ] **Step 4: Run birth collector and transform tests**

```bash
python3 -m unittest \
  data-pipeline/tests/test_birth_nums.py \
  data-pipeline/tests/test_transform_life_events.py
```

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/src/collectors/birth_nums.py \
  data-pipeline/tests/test_birth_nums.py
git commit -m "fix(pipeline): support localized birth fields"
```

---

### Task 4: County-Level TaiwanJobs Rows

**Files:**
- Modify: `data-pipeline/src/collectors/job_vacancy.py`
- Modify: `data-pipeline/src/transform/labor.py`
- Test: `data-pipeline/tests/test_job_vacancy.py`
- Test: `data-pipeline/tests/test_job_vacancy_salary.py`
- Test: `data-pipeline/tests/test_transform_labor.py`

**Interfaces:**
- Collector adds `geo_scope: "district" | "county"`.
- County rows use `district: ""` and keep `query_zipno` only as query provenance.
- Transform emits `geo_level="county"`, `district_id=None`, `district_name=None`, `county_name="新北市"`.

- [ ] **Step 1: Add failing county-wide collector test**

Return identical `CITYNAME="新北市不限"` rows from zip 220 and 235. Assert the combined collector returns one county row, not an exception and not two district rows.

```python
self.assertEqual(len(records), 1)
self.assertEqual(records[0]["geo_scope"], "county")
self.assertEqual(records[0]["district"], "")
```

- [ ] **Step 2: Preserve existing mismatch rejection test**

Keep `新北市中和區` rejected when querying `板橋區`; this guards against weakening district validation.

- [ ] **Step 3: Add failing county-level transform test**

```python
result = transform_job_vacancies([county_row], resolver=self.resolver)
self.assertEqual(result.records[0]["geo_level"], "county")
self.assertIsNone(result.records[0]["district_id"])
self.assertEqual(result.records[0]["county_name"], "新北市")
```

- [ ] **Step 4: Run tests and verify RED**

```bash
python3 -m unittest \
  data-pipeline/tests/test_job_vacancy.py \
  data-pipeline/tests/test_job_vacancy_salary.py \
  data-pipeline/tests/test_transform_labor.py
```

- [ ] **Step 5: Implement scope classification and county deduplication**

`_validate_cityname()` becomes a classifier returning `"district"` or `"county"`. It accepts only exact New Taipei county-wide markers (`新北市不限`, `新北市`) or the expected district. Other districts remain errors.

After all zip queries, deduplicate only `geo_scope="county"` records using a deterministic hash of source fields excluding `query_zipno`, `district`, `query_truncated`, and `geo_scope`.

- [ ] **Step 6: Update labor transform**

Branch on `geo_scope` before zip resolution. County rows never call `resolve_zip()` and never inherit the query district.

- [ ] **Step 7: Run tests and verify GREEN**

Run the command from Step 4. Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add data-pipeline/src/collectors/job_vacancy.py \
  data-pipeline/src/transform/labor.py \
  data-pipeline/tests/test_job_vacancy.py \
  data-pipeline/tests/test_job_vacancy_salary.py \
  data-pipeline/tests/test_transform_labor.py
git commit -m "fix(pipeline): preserve county-wide vacancies"
```

---

### Task 5: Source-Aware Execution Schedule

**Files:**
- Modify: `data-pipeline/src/orchestration/contracts.py`
- Create: `data-pipeline/src/orchestration/schedule.py`
- Modify: `data-pipeline/src/run_pipeline.py`
- Create: `data-pipeline/tests/test_orchestration_schedule.py`
- Modify: `data-pipeline/tests/test_transform_pipeline.py`

**Interfaces:**
- Produces: `PeriodStrategy(str, Enum)` with `MONTHLY`, `ANNUAL`, `SNAPSHOT`, `ALL_AVAILABLE`.
- Produces: `CollectorSpec(dataset: str, collect: Callable[[str], Any], period_strategy: PeriodStrategy)`.
- Produces: `ExecutionUnit(spec: CollectorSpec, source_period: str, output_key: str)`.
- Produces: `build_execution_units(specs, start_period, end_period) -> list[ExecutionUnit]`.

- [ ] **Step 1: Write failing strategy-count test**

For range `11411–11502`, assert:

```python
self.assertEqual(monthly_keys, ["11411", "11412", "11501", "11502"])
self.assertEqual(annual_keys, ["114", "115"])
self.assertEqual(snapshot_keys, ["latest"])
self.assertEqual(all_available_keys, ["all"])
```

- [ ] **Step 2: Write failing default registry test**

Assert every default dataset has the exact strategy from the design table and TDX datasets are snapshot.

- [ ] **Step 3: Run tests and verify RED**

```bash
python3 -m unittest data-pipeline/tests/test_orchestration_schedule.py
```

- [ ] **Step 4: Implement contracts and schedule**

Annual units pass `source_period=f"{year}01"` to existing collectors so wrappers using `period[:3]` remain compatible, while `output_key=year`. Snapshot and all-available units pass `source_period=end_period` only as fetch provenance; records retain source dates.

- [ ] **Step 5: Refactor range runner to consume execution units**

Extract the body that runs one `CollectorSpec` into:

```python
def run_execution_unit(
    unit: ExecutionUnit,
    *,
    output_dir: str | Path,
    config_dir: str | Path,
    strict: bool,
    resume: bool,
    force: bool,
) -> dict[str, Any]:
```

Keep `run_full_pipeline()` as a compatibility wrapper for a single month.

- [ ] **Step 6: Run schedule and existing integration tests**

```bash
python3 -m unittest \
  data-pipeline/tests/test_orchestration_schedule.py \
  data-pipeline/tests/test_transform_pipeline.py
```

- [ ] **Step 7: Commit**

```bash
git add data-pipeline/src/orchestration/contracts.py \
  data-pipeline/src/orchestration/schedule.py \
  data-pipeline/src/run_pipeline.py \
  data-pipeline/tests/test_orchestration_schedule.py \
  data-pipeline/tests/test_transform_pipeline.py
git commit -m "refactor(pipeline): schedule sources by period strategy"
```

---

### Task 6: Resume, Raw Reuse, and Authoritative Index

**Files:**
- Create: `data-pipeline/src/orchestration/state.py`
- Modify: `data-pipeline/src/transform/io.py`
- Modify: `data-pipeline/src/run_pipeline.py`
- Create: `data-pipeline/tests/test_orchestration_state.py`
- Modify: `data-pipeline/tests/test_transform_pipeline.py`

**Interfaces:**
- Produces: `ResumeAction(str, Enum)` with `REUSE_OUTPUT`, `REUSE_RAW`, `DOWNLOAD`, `KEEP_NO_DATA`.
- Produces: `choose_resume_action(...) -> ResumeAction`.
- Produces: `find_latest_raw(output_dir, dataset, unit) -> Path | None`.
- Produces: `write_dataset_index(entries, *, output_dir) -> Path`.
- CLI adds `--resume` and `--force`; they are mutually exclusive.

- [ ] **Step 1: Write failing resume-decision tests**

Cover exact cases:

```python
self.assertEqual(action_for_current_ok_output, ResumeAction.REUSE_OUTPUT)
self.assertEqual(action_for_legacy_report_with_raw, ResumeAction.REUSE_RAW)
self.assertEqual(action_for_error_without_raw, ResumeAction.DOWNLOAD)
self.assertEqual(action_for_no_data, ResumeAction.KEEP_NO_DATA)
self.assertEqual(action_with_force, ResumeAction.DOWNLOAD)
```

- [ ] **Step 2: Write failing raw-selection tests**

Create multiple temp raw filenames. Assert monthly selects matching `yyyMM`, annual selects the newest raw matching `yyy??`, and snapshot selects the newest raw file regardless of requested historical month.

- [ ] **Step 3: Write failing index test**

Assert the index contains only current execution-unit outputs:

```json
{
  "schema_version": 2,
  "datasets": {
    "population": [{"output_key": "11507", "path": "curated/population/11507.json"}],
    "house_prices": [{"output_key": "latest", "path": "curated/house_prices/latest.json"}]
  }
}
```

Legacy `curated/house_prices/11001.json` must not appear.

- [ ] **Step 4: Run tests and verify RED**

```bash
python3 -m unittest data-pipeline/tests/test_orchestration_state.py
```

- [ ] **Step 5: Implement state decisions and atomic index output**

Use `SCHEMA_VERSION = 2` and `TRANSFORM_VERSION = "2026-09-02"`. Reuse `_atomic_json_write()` through a public `write_dataset_index()` in `transform/io.py`; do not duplicate non-atomic JSON writes.

- [ ] **Step 6: Integrate retry, no-data, resume and raw replay**

`run_execution_unit()` performs:

```text
choose action
  REUSE_OUTPUT -> report and index existing output
  KEEP_NO_DATA -> report skipped
  REUSE_RAW -> load raw envelope -> run_transform -> write output
  DOWNLOAD -> collect_with_retry -> write raw -> run_transform -> write output
```

Catch `CollectorNoDataError` before generic exceptions. Store attempts, downloaded, reused_raw and reused_output in reports. Terminal prints every decision.

- [ ] **Step 7: Add CLI integration tests**

Run range once with fake collectors, then run with `--resume`. Assert collector call counts do not increase for successful units, failed units are called again, raw-backed legacy units transform without collector calls, and `--force` calls everything again.

- [ ] **Step 8: Run focused tests and verify GREEN**

```bash
python3 -m unittest \
  data-pipeline/tests/test_orchestration_state.py \
  data-pipeline/tests/test_transform_pipeline.py \
  data-pipeline/tests/test_orchestration_retry.py \
  data-pipeline/tests/test_orchestration_schedule.py
```

- [ ] **Step 9: Commit**

```bash
git add data-pipeline/src/orchestration/state.py \
  data-pipeline/src/transform/io.py \
  data-pipeline/src/run_pipeline.py \
  data-pipeline/tests/test_orchestration_state.py \
  data-pipeline/tests/test_transform_pipeline.py
git commit -m "feat(pipeline): resume failed data collection"
```

---

### Task 7: Documentation and Full Verification

**Files:**
- Modify: `data-pipeline/data-pipeline.md`
- Modify: `data-pipeline/src/transform/transform.md`

**Interfaces:**
- Documents authoritative commands and output paths from Tasks 5–6.

- [ ] **Step 1: Update commands and status semantics**

Document:

```bash
python src/run_pipeline.py \
  --start-period 10501 \
  --end-period 11507 \
  --output-dir data \
  --resume \
  --strict
```

Explain `downloaded`, `retried`, `reused_raw`, `reused_output`, `skipped/no_data`, `latest`, `all`, and `dataset_index.json`. State that `--force` re-downloads all scheduled units.

- [ ] **Step 2: Run the complete test suite**

```bash
python3 -m unittest discover -s data-pipeline/tests -p 'test_*.py'
```

Expected: all collector, transform, orchestration and integration tests pass.

- [ ] **Step 3: Run compilation and whitespace verification**

```bash
python3 -m py_compile \
  data-pipeline/src/run_pipeline.py \
  data-pipeline/src/collectors/*.py \
  data-pipeline/src/orchestration/*.py \
  data-pipeline/src/transform/*.py
git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 4: Run safe local recovery smoke test**

Use a temporary output directory and test fixtures/fake collectors. Confirm the second `--resume` execution performs zero calls for successful units and retries only the seeded failed unit. Do not call live APIs in this step.

- [ ] **Step 5: Review existing data without deleting it**

Confirm `data/quality/dataset_index.json` excludes legacy repeated snapshot paths. Report the legacy files to the user; do not remove them.

- [ ] **Step 6: Commit**

```bash
git add data-pipeline/data-pipeline.md data-pipeline/src/transform/transform.md
git commit -m "docs(pipeline): document recovery workflow"
```

---

### Task 8: Controlled Live Recovery

**Files:**
- Output only: `data-pipeline/data/raw/`
- Output only: `data-pipeline/data/curated/`
- Output only: `data-pipeline/data/quality/`
- Output only: `data-pipeline/data/quarantine/`

**Interfaces:**
- Consumes the verified CLI from Tasks 1–7.
- Produces updated reports and authoritative index; does not delete legacy files.

- [ ] **Step 1: Execute resume mode**

```bash
cd data-pipeline
python src/run_pipeline.py \
  --start-period 10501 \
  --end-period 11507 \
  --output-dir data \
  --resume \
  --strict
```

Expected: terminal displays reuse for valid raw/output, retries only missing/error units, and runs snapshot/all-available once.

- [ ] **Step 2: Inspect recovery summary**

Read `data/quality/collection_range.json` and calculate status/action counts. Confirm timeout count, errors, skipped periods, downloads and raw reuse separately.

- [ ] **Step 3: Inspect authoritative index**

Confirm every indexed path exists, annual datasets have one file per year, monthly datasets one per available month, and snapshot datasets only `latest.json`.

- [ ] **Step 4: Report remaining external-source limitations**

List any source that remains unavailable after 3 timeout attempts, any no-data periods, and any upstream schema not covered by the validated aliases. Do not label no-data as failure.

