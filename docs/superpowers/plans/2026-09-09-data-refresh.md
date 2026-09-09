# Data Pipeline Source-Aware Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 data pipeline 依 daily、weekly、monthly profile 只更新已到期的資料，保留既有 raw/curated 輸出，並能安全重試 transient failure 與重新檢查 annual no-data。

**Architecture:** `PeriodStrategy` 繼續描述來源資料的 period 分區；新增 refresh profile 描述 wall-clock 更新頻率。`orchestration.refresh` 讀取設定、檢查 refresh state 並選出到期的 `ExecutionUnit`，`run_pipeline.py` 執行這些 units、更新 state 與 refresh report；外部 cron、GitHub Actions 或 AWS Scheduler 只負責定時呼叫 CLI。

**Tech Stack:** Python 3 standard library、既有 urllib collectors、local JSON、`unittest`、既有 `pypdf` dependency。

**Spec:** `docs/superpowers/specs/2026-09-09-data-refresh-design.md`

## Global Constraints

- `PeriodStrategy` 與 wall-clock refresh cadence 必須分離，不得用 `PeriodStrategy` 代替排程頻率。
- daily profile 只包含 `job_vacancies`、`job_vacancy_salaries`。
- weekly profile 只包含 `house_prices`、`rentals`、`vt_courses`、`training_numbers`。
- monthly profile 包含人口、年度檢查、人才需求、青年預算與 TDX 資料集。
- annual data 使用 monthly profile 檢查新完整年度；查無資料不得永久 suppress，下一個日曆月份 window 必須能重新檢查。
- refresh mode 只處理到期 units；未到期 unit 不呼叫 collector。
- `--datasets` 只能縮小 profile 範圍；未知 dataset 必須在執行前報錯。
- `--failed-only` 只選上一次 status 為 `error` 的 unit，不把 `no_data` 當成永久失敗。
- transient retry 最多 3 次，backoff 為 1 秒、2 秒；不得 retry schema、validation、unsupported-year 或 `CollectorNoDataError`。
- 既有 `--period`、`--start-period/--end-period`、`--resume`、`--force` 與 `--input` replay contract 必須維持相容。
- 預設保留前五個完整年度與目前年度；collection 成功後才清除早於保留起點的 local JSON 與 dataset index entries。
- 清理規則必須依 PeriodStrategy 處理 monthly、annual、snapshot、all_available，不能只依檔名猜測。
- local retention policy 與 storage 操作分離，未來改用 S3 時沿用同一保留規則。
- 測試使用 fake responses，不呼叫 live source；live refresh 只作手動 smoke check。
- `data-pipeline/data/data_description.md` 不在本次修改範圍。
- AWS infrastructure 不在本次實作範圍；外部 scheduler 必須能呼叫同一個 refresh CLI。

## File Map

### Create

- `data-pipeline/config/refresh_profiles.json`: daily、weekly、monthly 的 dataset 清單。
- `data-pipeline/src/orchestration/refresh.py`: refresh profile 載入、dataset 選擇、cadence 判斷與 current execution units。
- `data-pipeline/tests/test_orchestration_refresh.py`: profile validation、due/not-due、annual no-data recheck 與 failed-only 測試。
- `data-pipeline/tests/test_run_pipeline_refresh.py`: refresh runner、CLI 範圍與 state/report integration tests。

### Modify

- `data-pipeline/src/orchestration/schedule.py`: 新增由現在時間建立 current ROC period 的 source-aware units，保留歷史 range planner。
- `data-pipeline/src/orchestration/state.py`: 新增 refresh state 讀寫、unit key、due 判斷與 state 更新。
- `data-pipeline/src/orchestration/retry.py`: 將 `IncompleteRead` 與 `ConnectionResetError` 納入 transient retry taxonomy。
- `data-pipeline/src/run_pipeline.py`: 新增 `run_refresh()`、`--refresh-profile`、`--datasets`、`--failed-only` 與 refresh report/state 更新。
- `data-pipeline/src/transform/io.py`: 新增 refresh report 的原子 JSON writer。
- `data-pipeline/tests/test_orchestration_schedule.py`: 驗證 current ROC period 對應 monthly、annual、snapshot、all_available。
- `data-pipeline/tests/test_orchestration_state.py`: 驗證 refresh state 與 no-data recheck。
- `data-pipeline/tests/test_orchestration_retry.py`: 驗證 `IncompleteRead` retry 與 exhausted error。
- `data-pipeline/data-pipeline.md`: 新增 refresh profiles、命令、state、failed-only 與外部 scheduler 說明。

### Generated at runtime, not committed as source configuration

- `data-pipeline/data/quality/refresh_state.json`
- `data-pipeline/data/quality/refresh_daily.json`
- `data-pipeline/data/quality/refresh_weekly.json`
- `data-pipeline/data/quality/refresh_monthly.json`
- `data-pipeline/data/quality/retention_report.json`

## Task 1: 建立 refresh profile 設定與驗證

**Files:**

- Create: `data-pipeline/config/refresh_profiles.json`
- Create: `data-pipeline/src/orchestration/refresh.py`
- Create: `data-pipeline/tests/test_orchestration_refresh.py`

**Interfaces:**

- Produces `PROFILE_NAMES: tuple[str, ...] = ("daily", "weekly", "monthly")`.
- Produces `load_refresh_profiles(path: str | Path) -> dict[str, tuple[str, ...]]`.
- Produces `validate_refresh_profiles(profiles: Mapping[str, Sequence[str]], known_datasets: Iterable[str]) -> None`.
- Produces `datasets_for_profile(profiles: Mapping[str, Sequence[str]], profile: str, selected: Sequence[str] | None = None) -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing profile tests**

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from orchestration.refresh import (
    datasets_for_profile,
    load_refresh_profiles,
    validate_refresh_profiles,
)


class RefreshProfileTests(unittest.TestCase):
    def test_loads_profiles_and_filters_selected_datasets(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "refresh_profiles.json"
            path.write_text(json.dumps({
                "version": 1,
                "profiles": {
                    "daily": ["job_vacancies", "job_vacancy_salaries"],
                    "weekly": ["house_prices"],
                    "monthly": ["population"],
                },
            }), encoding="utf-8")
            profiles = load_refresh_profiles(path)

        self.assertEqual(
            datasets_for_profile(
                profiles,
                "daily",
                selected=("job_vacancies",),
            ),
            ("job_vacancies",),
        )

    def test_rejects_unknown_or_duplicate_dataset(self):
        profiles = {
            "daily": ("job_vacancies", "population"),
            "weekly": ("population",),
            "monthly": (),
        }
        with self.assertRaises(ValueError):
            validate_refresh_profiles(profiles, {"job_vacancies", "population"})

    def test_rejects_unknown_profile(self):
        with self.assertRaises(ValueError):
            datasets_for_profile(
                {"daily": ("job_vacancies",), "weekly": (), "monthly": ()},
                "annual",
            )
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest tests.test_orchestration_refresh -v
```

Expected: `ImportError` because `orchestration.refresh` does not exist.

- [ ] **Step 3: Add the exact profile configuration**

Create `data-pipeline/config/refresh_profiles.json`:

```json
{
  "version": 1,
  "profiles": {
    "daily": [
      "job_vacancies",
      "job_vacancy_salaries"
    ],
    "weekly": [
      "house_prices",
      "rentals",
      "vt_courses",
      "training_numbers"
    ],
    "monthly": [
      "population",
      "movement",
      "births",
      "marriages",
      "wages",
      "college_majors",
      "graduate_majors",
      "talent_demand",
      "youth_budgets",
      "bus_stops",
      "railway_stops",
      "bike_stops"
    ]
  }
}
```

- [ ] **Step 4: Implement profile loading and validation**

Implement `load_refresh_profiles()` to reject invalid JSON, a missing `version`, non-list profile values, and profile names outside `PROFILE_NAMES`. Implement `validate_refresh_profiles()` against the complete supported registry (the 15 default datasets plus 3 optional TDX datasets), so TDX names remain valid when TDX execution is disabled. Reject duplicates across profiles. Implement `datasets_for_profile()` to preserve configuration order and ensure `selected` is a subset of the requested profile.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run:

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest tests.test_orchestration_refresh -v
```

Expected: all profile tests pass.

- [ ] **Step 6: Commit**

```bash
git add data-pipeline/config/refresh_profiles.json data-pipeline/src/orchestration/refresh.py data-pipeline/tests/test_orchestration_refresh.py
git commit -m "feat(pipeline): add refresh profiles"
```

## Task 2: 建立 current execution units 與 refresh state

**Files:**

- Modify: `data-pipeline/src/orchestration/schedule.py`
- Modify: `data-pipeline/src/orchestration/state.py`
- Modify: `data-pipeline/src/orchestration/refresh.py`
- Modify: `data-pipeline/tests/test_orchestration_schedule.py`
- Modify: `data-pipeline/tests/test_orchestration_state.py`
- Modify: `data-pipeline/tests/test_orchestration_refresh.py`

**Interfaces:**

- Produces `current_roc_period(now: datetime) -> str`.
- Produces `build_current_execution_units(specs: Iterable[CollectorSpec], now: datetime) -> list[ExecutionUnit]`.
- Produces `load_refresh_state(output_dir: str | Path) -> dict[str, Any]`.
- Produces `write_refresh_state(state: Mapping[str, Any], output_dir: str | Path) -> Path`.
- Produces `refresh_state_key(unit: ExecutionUnit) -> str`.
- Produces `is_refresh_due(entry: Mapping[str, Any] | None, *, now: datetime, profile: str, failed_only: bool = False) -> bool`.
- Extends `build_refresh_units(...) -> list[ExecutionUnit]` with profile, state, selected datasets and failed-only filtering.

- [ ] **Step 1: Write the failing current-period and state tests**

```python
import unittest
from datetime import datetime, timezone

from orchestration.schedule import build_current_execution_units, current_roc_period
from orchestration.state import is_refresh_due
from run_pipeline import DEFAULT_COLLECTOR_SPECS


class RefreshSchedulingTests(unittest.TestCase):
    def test_current_period_converts_gregorian_to_roc_month(self):
        now = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(current_roc_period(now), "11509")

    def test_current_units_keep_source_aware_output_keys(self):
        now = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
        units = build_current_execution_units(DEFAULT_COLLECTOR_SPECS, now=now)
        by_dataset = {unit.spec.dataset: unit for unit in units}
        self.assertEqual(by_dataset["population"].output_key, "11509")
        self.assertEqual(by_dataset["births"].output_key, "115")
        self.assertEqual(by_dataset["house_prices"].output_key, "latest")
        self.assertEqual(by_dataset["youth_budgets"].output_key, "all")

    def test_no_data_entry_is_due_again_after_monthly_window(self):
        old = {
            "status": "skipped",
            "reason": "no_data",
            "last_checked_at": "2026-08-01T00:00:00+00:00",
        }
        now = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(is_refresh_due(old, now=now, profile="monthly"))

    def test_failed_only_excludes_successful_entry(self):
        old = {
            "status": "ok",
            "last_success_at": "2026-09-08T00:00:00+00:00",
        }
        now = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(is_refresh_due(old, now=now, profile="daily", failed_only=True))
```

- [ ] **Step 2: Run focused tests and verify they fail**

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_orchestration_schedule \
  tests.test_orchestration_state \
  tests.test_orchestration_refresh -v
```

Expected: missing current-period/state functions or assertion failures.

- [ ] **Step 3: Implement current period planning**

`current_roc_period()` must use `now.year - 1911` and two-digit month formatting. `build_current_execution_units()` must call the existing source-aware planner with the same current period as start and end, so monthly, annual, snapshot and all_available units continue to use the existing `output_key` rules. `is_refresh_due()` uses 24 hours for daily, 7 days for weekly, and a calendar-month change for monthly.

- [ ] **Step 4: Implement refresh state persistence**

Store JSON under `output_dir / "quality" / "refresh_state.json"` with this shape:

```json
{
  "schema_version": 1,
  "units": {
    "job_vacancies:latest": {
      "dataset": "job_vacancies",
      "source_period": "11509",
      "output_key": "latest",
      "status": "ok",
      "last_started_at": "2026-09-09T00:00:00+00:00",
      "last_checked_at": "2026-09-09T00:00:03+00:00",
      "last_success_at": "2026-09-09T00:00:03+00:00",
      "attempts": 1
    }
  }
}
```

Use the unit key `{dataset}:{output_key}`. A missing entry is due. A successful entry is due when its profile interval has elapsed. An error entry is due for `failed_only`; a no-data entry is due again after the same profile interval. State writes must use the existing atomic JSON-writing pattern.

- [ ] **Step 5: Implement profile-based unit filtering**

`build_refresh_units()` must:

1. Build current source-aware units for all registered specs.
2. Validate the profile against the complete supported dataset registry, including optional TDX specs.
3. Keep only active specs whose datasets are in the selected profile.
4. Apply `selected` dataset filtering.
5. Apply `is_refresh_due()` using the state entry.
6. Apply `failed_only` after status filtering.

It must return an empty list when no unit is due; this is a successful no-op, not an error.

- [ ] **Step 6: Run focused tests and verify they pass**

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_orchestration_schedule \
  tests.test_orchestration_state \
  tests.test_orchestration_refresh -v
```

- [ ] **Step 7: Commit**

```bash
git add data-pipeline/src/orchestration/schedule.py data-pipeline/src/orchestration/state.py data-pipeline/src/orchestration/refresh.py data-pipeline/tests/test_orchestration_schedule.py data-pipeline/tests/test_orchestration_state.py data-pipeline/tests/test_orchestration_refresh.py
git commit -m "feat(pipeline): plan due refresh units"
```

## Task 3: 補強 transient retry

**Files:**

- Modify: `data-pipeline/src/orchestration/retry.py`
- Modify: `data-pipeline/tests/test_orchestration_retry.py`

**Interfaces:**

- Preserve `is_timeout_error(exc: BaseException) -> bool`.
- Preserve `collect_with_retry(...) -> RetryResult`.
- Add recognition for `http.client.IncompleteRead` and `ConnectionResetError`, including wrapped causes and contexts.

- [ ] **Step 1: Write failing retry tests**

```python
import unittest
from http.client import IncompleteRead

from orchestration.retry import collect_with_retry


class RetryTests(unittest.TestCase):
    def test_retries_incomplete_read_then_succeeds(self):
        calls = 0

        def operation():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise IncompleteRead(b"partial")
            return ["record"]

        result = collect_with_retry(operation, sleep=lambda _: None)
        self.assertEqual(result.value, ["record"])
        self.assertEqual(result.attempts, 3)

    def test_does_not_retry_collector_validation_error(self):
        calls = 0

        def operation():
            nonlocal calls
            calls += 1
            raise ValueError("invalid source schema")

        with self.assertRaises(ValueError):
            collect_with_retry(operation, sleep=lambda _: None)
        self.assertEqual(calls, 1)
```

- [ ] **Step 2: Run retry tests and verify the new test fails**

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest tests.test_orchestration_retry -v
```

Expected: `IncompleteRead` is raised without retry.

- [ ] **Step 3: Implement the expanded transient taxonomy**

Import `IncompleteRead` and `ConnectionResetError` support in `is_timeout_error()`. Continue walking `__cause__` and `__context__`; do not classify generic `RuntimeError` or collector validation exceptions as transient only because their message contains “error”.

- [ ] **Step 4: Run retry tests and verify they pass**

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest tests.test_orchestration_retry -v
```

- [ ] **Step 5: Commit**

```bash
git add data-pipeline/src/orchestration/retry.py data-pipeline/tests/test_orchestration_retry.py
git commit -m "fix(pipeline): retry interrupted HTTP reads"
```

## Task 4: 新增 refresh runner、report 與 CLI

**Files:**

- Modify: `data-pipeline/src/run_pipeline.py`
- Modify: `data-pipeline/src/transform/io.py`
- Create: `data-pipeline/tests/test_run_pipeline_refresh.py`

**Interfaces:**

- Produces `run_refresh(profile: str, *, output_dir: str | Path, config_dir: str | Path, include_tdx: bool = False, strict: bool = False, datasets: Sequence[str] | None = None, failed_only: bool = False, now: datetime | None = None, refresh_profiles_path: str | Path | None = None, collector_specs: Sequence[CollectorSpec] | None = None, refresh_profiles: Mapping[str, Sequence[str]] | None = None) -> dict[str, Any]`.
- Produces `write_refresh_report(report: Mapping[str, Any], *, profile: str, output_dir: str | Path) -> Path`.
- CLI accepts `--refresh-profile daily|weekly|monthly`.
- CLI accepts comma-separated `--datasets` only with refresh mode.
- CLI accepts `--failed-only` only with refresh mode.

- [ ] **Step 1: Write failing runner tests with fake collectors**

```python
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from orchestration.contracts import CollectorSpec, PeriodStrategy
from run_pipeline import run_refresh


class RefreshRunnerTests(unittest.TestCase):
    def test_refresh_runs_only_due_selected_dataset(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            specs = (
                CollectorSpec(
                    "job_vacancies",
                    lambda period: [],
                    PeriodStrategy.SNAPSHOT,
                ),
            )
            profiles = {
                "daily": ("job_vacancies",),
                "weekly": (),
                "monthly": (),
            }
            status = {
                "status": "ok",
                "source_period": "11509",
                "output_key": "latest",
                "attempts": 1,
            }
            with patch("run_pipeline._run_execution_unit", return_value=status) as execute:
                report = run_refresh(
                    "daily",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    now=datetime(2026, 9, 9, tzinfo=timezone.utc),
                )

            self.assertEqual(report["status"], "ok")
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(execute.call_args.args[0].source_period, "11509")
            self.assertTrue((output_dir / "quality" / "refresh_state.json").is_file())
            self.assertTrue((output_dir / "quality" / "refresh_daily.json").is_file())

    def test_failed_only_does_not_run_successful_unit(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            state_dir = output_dir / "quality"
            state_dir.mkdir(parents=True)
            (state_dir / "refresh_state.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "units": {
                        "job_vacancies:latest": {
                            "dataset": "job_vacancies",
                            "output_key": "latest",
                            "status": "ok",
                            "last_success_at": "2026-09-09T00:00:00+00:00",
                        }
                    },
                }),
                encoding="utf-8",
            )
            specs = (
                CollectorSpec(
                    "job_vacancies",
                    lambda period: [],
                    PeriodStrategy.SNAPSHOT,
                ),
            )
            profiles = {
                "daily": ("job_vacancies",),
                "weekly": (),
                "monthly": (),
            }
            with patch("run_pipeline._run_execution_unit") as execute:
                report = run_refresh(
                    "daily",
                    output_dir=output_dir,
                    config_dir=output_dir,
                    collector_specs=specs,
                    refresh_profiles=profiles,
                    failed_only=True,
                    now=datetime(2026, 9, 9, 1, tzinfo=timezone.utc),
                )

            self.assertEqual(report["status"], "ok")
            execute.assert_not_called()
```

- [ ] **Step 2: Run the new runner tests and verify they fail**

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest tests.test_run_pipeline_refresh -v
```

Expected: `run_refresh` does not exist or the new CLI/report files are missing.

- [ ] **Step 3: Implement refresh report writing**

Add `write_refresh_report()` to `transform/io.py`. Write to `quality/refresh_{profile}.json` using the existing atomic replacement pattern. Report fields must include `schema_version`, `profile`, `fetched_at`, `selected_datasets`, `execution_units`, `status`, `errors`, and `state_path`.

- [ ] **Step 4: Implement `run_refresh()`**

The function must:

1. Load the configured profiles or use the injected `refresh_profiles` mapping in tests.
2. Build the default specs and optional TDX specs, unless tests inject `collector_specs`.
3. Load `refresh_state.json`.
4. Call `build_refresh_units()`.
5. Mark each selected unit as started.
6. Call the existing `_run_execution_unit()` with `resume=False` and `force=True`, because a due refresh explicitly requests a new source fetch.
7. Copy status fields into the state entry, including `status`, `attempts`, `source_period`, `output_key`, `error`, `source_message`, and timestamps.
8. Persist state after each unit so an interrupted run can resume from completed units.
9. Write `refresh_{profile}.json`.
10. Return `status="error"` only when a unit is error and `strict=True`; `no_data` remains skipped.

The existing historical `run_period_range()` and `_run_execution_unit()` contracts must remain unchanged.

- [ ] **Step 5: Add CLI argument validation and dispatch**

Add:

```python
parser.add_argument(
    "--refresh-profile",
    choices=("daily", "weekly", "monthly"),
    help="Run only datasets due in the selected refresh profile",
)
parser.add_argument(
    "--datasets",
    help="Comma-separated dataset names; only valid with --refresh-profile",
)
parser.add_argument(
    "--failed-only",
    action="store_true",
    help="With refresh mode, retry only units whose previous status was error",
)
```

Reject refresh arguments combined with `--input`, `--period`, `--start-period`, or `--end-period`. Parse `--datasets` into a trimmed tuple and reject an empty name before any collector runs.

- [ ] **Step 6: Run focused runner and existing pipeline tests**

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_run_pipeline_refresh \
  tests.test_orchestration_schedule \
  tests.test_orchestration_state \
  tests.test_transform_pipeline -v
```

- [ ] **Step 7: Commit**

```bash
git add data-pipeline/src/run_pipeline.py data-pipeline/src/transform/io.py data-pipeline/tests/test_run_pipeline_refresh.py
git commit -m "feat(pipeline): add scheduled refresh runner"
```

## Task 5: 補充操作文件與本機驗證命令

**Files:**

- Modify: `data-pipeline/data-pipeline.md`

**Interfaces:**

- Documentation must expose the exact refresh commands and distinguish refresh mode from historical range mode.
- Documentation must state that `data/data_description.md` is not the scheduling source of truth.

- [ ] **Step 1: Add refresh operation documentation**

Add these commands to `data-pipeline/data-pipeline.md`:

```bash
# 每日職缺更新
cd data-pipeline
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile daily \
  --output-dir data \
  --strict

# 每週房價、租金與職訓更新
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile weekly \
  --output-dir data \
  --strict

# 每月人口、年度資料檢查、青年預算與 TDX 更新
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile monthly \
  --include-tdx \
  --output-dir data \
  --strict

# 只重跑 daily profile 中上次失敗的指定資料
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile daily \
  --datasets job_vacancies,job_vacancy_salaries \
  --failed-only \
  --output-dir data \
  --strict
```

- [ ] **Step 2: Document external scheduler boundary**

Explain that cron, GitHub Actions or AWS EventBridge invokes the same command. Do not add AWS credentials, infrastructure code, or deployment resources in this task.

- [ ] **Step 3: Run documentation and repository checks**

```bash
git diff --check
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m py_compile \
  src/run_pipeline.py \
  src/orchestration/contracts.py \
  src/orchestration/retry.py \
  src/orchestration/schedule.py \
  src/orchestration/state.py \
  src/orchestration/refresh.py
```

- [ ] **Step 4: Run the complete test suite**

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Expected: all existing and new tests pass, with no live network calls.

- [ ] **Step 5: Commit documentation**

```bash
git add data-pipeline/data-pipeline.md
git commit -m "docs(pipeline): document refresh operations"
```

## Task 6: 建立本地 JSON 五年保留與未來 S3 邊界

**Files:**

- Create: `data-pipeline/src/orchestration/retention.py`
- Create: `data-pipeline/tests/test_orchestration_retention.py`
- Modify: `data-pipeline/src/run_pipeline.py`
- Modify: `data-pipeline/src/transform/io.py`
- Modify: `data-pipeline/tests/test_run_pipeline_refresh.py`
- Modify: `data-pipeline/data-pipeline.md`

**Interfaces:**

- `build_retention_window(current_period: str, years: int = 5) -> RetentionWindow`
- `period_is_retained(period: str, strategy: PeriodStrategy, window: RetentionWindow) -> bool`
- `prune_local_data(output_dir, *, current_period, period_strategies, retention_years=5) -> dict`

保留窗以目前 ROC 年為基準，5 年代表前五個完整年度加上目前年度；例如 `11509` 的月資料起點為 `11001`，年度資料保留 `110` 至 `115`。`SNAPSHOT` 保留最新 curated output，`ALL_AVAILABLE` 依資料內的年度或日期欄位過濾 records，但未來年度資料不因為晚於目前年度而刪除。無法辨識期間的資料必須保留，不得猜測刪除。

- [ ] **Step 1: Write failing retention tests**

測試月資料的 60 個月邊界、年資料的 5 年邊界、curated/raw/quality/quarantine 與 dataset index 的同步清除，以及 youth budget/all-available records 的年度過濾。

- [ ] **Step 2: Run focused retention tests and verify they fail**

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest tests.test_orchestration_retention -v
```

Expected: `ImportError` because `orchestration.retention` does not exist.

- [ ] **Step 3: Implement retention policy and local storage operation**

`retention.py` 只包含保留窗計算、期間判斷與 local JSON 清理；不得把 S3 SDK 或 AWS 設定放進來。刪除前只處理 pipeline 自己產生且可判斷期間的檔案，並回傳 `deleted_paths`、`rewritten_paths`、`monthly_cutoff`、`annual_cutoff` 與計數。

- [ ] **Step 4: Integrate successful-run cleanup**

`run_refresh()`、`run_period_range()` 與 `run_full_pipeline()` 在 collection 沒有任何 error 時執行清理，並把結果放入 report；只要有 error 就保留現有資料。使用 `quality/retention_report.json` 記錄清理結果，並在清理後重寫 authoritative `dataset_index.json`。

- [ ] **Step 5: Document bootstrap and retention behavior**

文件說明首次使用 historical range 先抓最近 5 年；之後 refresh 只抓到期資料，成功後自動刪除超過保留窗的 local JSON。說明未來 S3 只替換 storage operation，保留規則不變。

- [ ] **Step 6: Run focused verification**

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_orchestration_retention \
  tests.test_run_pipeline_refresh -v
```

- [ ] **Step 7: Commit**

```bash
git add data-pipeline/src/orchestration/retention.py \
  data-pipeline/src/run_pipeline.py \
  data-pipeline/src/transform/io.py \
  data-pipeline/tests/test_orchestration_retention.py \
  data-pipeline/tests/test_run_pipeline_refresh.py \
  data-pipeline/data-pipeline.md
git commit -m "feat(pipeline): enforce rolling data retention"
```

## Verification Checklist

- [ ] `refresh_profiles.json` covers every registered dataset exactly once when TDX is enabled.
- [ ] A second daily invocation within the same interval executes zero collectors.
- [ ] A monthly invocation rechecks an old annual `no_data` entry.
- [ ] `--failed-only` executes only previous `error` units.
- [ ] `IncompleteRead` succeeds on the third attempt and records `attempts=3` when exhausted.
- [ ] Existing historical range and replay behavior still passes all tests.
- [ ] Existing untracked files outside this plan remain untouched.
- [ ] No AWS infrastructure is committed as part of this local refresh implementation.
- [ ] Local JSON retention keeps exactly the configured rolling five-year window.
- [ ] Collection errors never trigger retention deletion.
- [ ] Retention logic does not depend on a future S3 SDK.
