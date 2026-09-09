# Task 2 Report: Current Execution Units and Refresh State

## Status

Implemented on the `datapipeline` branch. Task 2 adds current ROC execution-unit planning, refresh cadence decisions, persistent refresh state, and due-unit filtering while preserving the historical range planner and existing resume/raw-selection behavior.

## Files changed

- `data-pipeline/src/orchestration/schedule.py`
  - Added `current_roc_period()`.
  - Added `build_current_execution_units()` which delegates to the existing source-aware `build_execution_units()` planner.
- `data-pipeline/src/orchestration/state.py`
  - Added versioned refresh-state load/write helpers under `quality/refresh_state.json`.
  - Added `refresh_state_key()`.
  - Added daily, weekly, monthly and failed-only due decisions.
  - Kept the existing resume action, raw selection and collection schema constants unchanged.
- `data-pipeline/src/orchestration/refresh.py`
  - Added `build_refresh_units()`.
  - Validates custom profiles against the complete supported registry, including optional TDX datasets.
  - Filters active specs by profile, selected datasets, state and due status.
- `data-pipeline/tests/test_orchestration_schedule.py`
  - Added current ROC period and source-aware current-unit tests.
- `data-pipeline/tests/test_orchestration_state.py`
  - Added state round-trip, state-key, cadence and failed-only tests.
- `data-pipeline/tests/test_orchestration_refresh.py`
  - Added profile/state filtering and no-op refresh tests.
- `.superpowers/sdd/2026-09-09-data-refresh/task-2-report.md`
  - Added this implementation report as requested.

The existing untracked files `docs/homepage_analysis.md`, `docs/superpowers/plans/2026-09-09-data-refresh.md`, and `docs/superpowers/specs/2026-09-09-data-refresh-design.md` were not modified or staged.

## TDD evidence

### RED

Command:

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_orchestration_schedule \
  tests.test_orchestration_state \
  tests.test_orchestration_refresh -v
```

Output before implementation:

```text
ImportError: cannot import name 'build_current_execution_units' from 'orchestration.schedule'
ImportError: cannot import name 'is_refresh_due' from 'orchestration.state'
ImportError: cannot import name 'build_refresh_units' from 'orchestration.refresh'
Ran 3 tests in 0.000s
FAILED (errors=3)
```

The failures were missing-function failures from the newly added tests, not source/network failures.

### GREEN

Focused command:

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_orchestration_schedule \
  tests.test_orchestration_state \
  tests.test_orchestration_refresh -v
```

Result:

```text
Ran 27 tests in 0.040s
OK
```

Full regression command:

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Result:

```text
Ran 255 tests in 0.224s
OK
```

Additional verification:

```bash
git diff --check
```

Result: no whitespace errors.

## State and cadence decisions

- Current ROC period uses `now.year - 1911` and a two-digit month, for example Gregorian `2026-09` becomes ROC `11509`.
- Current units reuse the existing period strategy rules:
  - monthly: `source_period=11509`, `output_key=11509`
  - annual: `source_period=11501`, `output_key=115`
  - snapshot: `source_period=11509`, `output_key=latest`
  - all-available: `source_period=11509`, `output_key=all`
- Refresh state is stored at `output_dir/quality/refresh_state.json` with `schema_version: 1` and a `units` object keyed by `{dataset}:{output_key}`.
- Missing state entries are due.
- Successful and no-data entries use `last_checked_at` for cadence decisions.
- Daily is due after 24 hours; weekly is due after 7 days; monthly is due when the calendar month changes.
- `failed_only=True` selects only entries with `status: error`; successful and `no_data` entries are excluded.
- Invalid or missing timestamps are treated as due so stale state cannot silently suppress collection.
- `build_refresh_units()` loads the repository profile by default, but accepts validated profile mappings for deterministic tests and future callers.
- Optional TDX names remain valid in the supported registry; they produce units only when the caller passes active TDX specs.
- An empty due-unit result is returned as `[]`, allowing Task 4 to treat it as a successful no-op.

## Self-review

- Historical `build_execution_units()` behavior is unchanged.
- Existing `choose_resume_action()` and `find_latest_raw()` behavior is unchanged.
- No collector, runner, retry taxonomy, CLI, AWS scheduler, data description, plan or design file was changed.
- State writes use a temporary file in the destination directory and an atomic replacement, matching the existing JSON output pattern.
- Tests use local temporary directories and fake collector specs; no live source was called.
- The implementation is limited to Task 2 interfaces and supporting tests.

## Concerns

- `run_pipeline.py` does not yet call `build_refresh_units()` or persist state after a live run; that integration belongs to Task 4.
- Retry support for `IncompleteRead` and `ConnectionResetError` belongs to Task 3.
- Wall-clock execution still requires an external scheduler; this task only plans due units and persists state.
