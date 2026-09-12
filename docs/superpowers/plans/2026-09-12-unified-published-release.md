# Unified Published Analytics Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one analytics orchestration mode that writes homepage and every supported analysis into one versioned published snapshot, then updates `current.json` once.

**Architecture:** Keep the existing analytics generators and published snapshot writer as separate responsibilities. Add an `all` orchestration path in `run_analytics.py` that computes each metric once, writes the normal per-metric analytics artifacts, and passes all public analysis payloads plus quality payloads to the existing atomic publisher. Individual metric publishing remains available for historical/debug snapshots but does not become the complete release path.

**Tech Stack:** Python 3, existing `data-pipeline/src/analytics` modules, `unittest`, JSON published artifacts.

**Spec:** `docs/superpowers/specs/2026-09-10-backend-read-api-design.md` plus the approved chat design for a unified `dev-full` release.

## Global Constraints

- The complete release contains homepage, employment, fertility, participation, policy support, keyword frequency, and topic weight outputs.
- `current.json` is updated only after every requested output and manifest has been written successfully.
- Existing per-metric snapshot directories are retained and are not merged at read time.
- Public payloads exclude `_quality`, `raw_record`, `raw_records`, PDF contents, and local filesystem paths.
- Missing values remain `null`; this change does not convert quality warnings into numeric values.
- Existing collector, transform, curated, quality, and quarantine behavior is unchanged.
- Do not run `git add`, `git commit`, merge, or push; leave changes in the working tree for review.

## File and Responsibility Map

- Modify `data-pipeline/src/run_analytics.py`: add the `all` orchestration path and make it the only path that activates a complete current release.
- Modify `data-pipeline/src/analytics/published_snapshot.py`: preserve the existing atomic writer and add any manifest validation needed for multiple named analyses.
- Modify `data-pipeline/tests/test_run_analytics.py`: test that all seven outputs are generated once and passed to one publish call.
- Modify `data-pipeline/tests/test_published_snapshot.py`: test a complete manifest with all analysis artifact paths and quality entries.
- Create `data-pipeline/tests/fixtures/` data only if a small fixture is needed; do not copy the large live analytics files.
- Modify `data-pipeline/data/analytics/published/current.json` and create the complete `dev-full-*` snapshot only after the code and focused tests pass.

### Task 1: Add the full-release orchestration command

**Files:**

- Modify: `data-pipeline/src/run_analytics.py`
- Test: `data-pipeline/tests/test_run_analytics.py`

**Interfaces:**

- CLI: `python src/run_analytics.py --metric all --publish --snapshot-id dev-full-YYYYMMDD --output-dir data`
- Internal: `_run_all_analytics(args, *, output_dir: Path, config_dir: Path) -> int`
- Internal: `_public_payload(result: Mapping[str, Any]) -> dict[str, Any]`

- [x] Write a failing test that mocks all seven generators and writers, invokes `--metric all --publish`, and asserts one `publish_homepage_snapshot` call containing `employment`, `fertility`, `participation`, `policy_support`, `keyword_frequency`, and `topic_weight`.
- [x] Run `python -m unittest data-pipeline/tests/test_run_analytics.py -v` and verify the new test fails because `all` is not a supported metric.
- [x] Add `all` to the CLI choices and implement `_run_all_analytics` using one resolver/configuration, one homepage result, and the existing writer functions.
- [x] Keep the existing `_load_indexed_dataset` path for `join_proposals` and `youth_council_minutes`; the full run must use the authoritative dataset index.
- [x] Strip `_quality` from every public analysis payload and pass each corresponding quality mapping to `analysis_quality`.
- [x] Pass the user-provided snapshot id to the publisher; when omitted, derive a safe `dev-full-<UTC timestamp>` id from the homepage `generated_at`.
- [x] Make individual metric `--publish` calls write candidate snapshots without replacing the complete release pointer; only `--metric all --publish` updates `current.json`.
- [x] Run the focused test file and verify all existing single-metric tests still pass.

### Task 2: Validate and publish multiple analyses atomically

**Files:**

- Modify: `data-pipeline/src/analytics/published_snapshot.py`
- Test: `data-pipeline/tests/test_published_snapshot.py`

**Interfaces:**

- Extend `publish_homepage_snapshot(..., update_current: bool = True)` without changing the existing default behavior for direct callers.
- The complete release passes all named public analyses through `analyses` and their quality reports through `analysis_quality`.

- [x] Add a failing test with two or more analyses and assert that every named analysis appears in `manifest.artifacts.analyses` and `manifest.datasets`.
- [x] Run the focused publisher tests and verify the new assertions fail before implementation.
- [x] Add the optional pointer-update flag; always write snapshot artifacts and manifest first, and write `current.json` only when `update_current=True`.
- [x] Validate analysis names, mappings, public payload restrictions, and quality mappings before any pointer update.
- [x] Preserve the existing `dashboard_overview.json` and `district_details.json` output exactly for the homepage base payload.
- [x] Run `python -m unittest data-pipeline/tests/test_published_snapshot.py -v` and verify all tests pass.

### Task 3: Generate and verify the complete development snapshot

**Files:**

- Modify: `data-pipeline/data/analytics/published/current.json`
- Create: `data-pipeline/data/analytics/published/dev-full-<timestamp>/...`
- Test: `data-pipeline/tests/test_run_analytics.py`

- [x] Run the full-release command against the existing authoritative curated data:

  ```bash
  cd data-pipeline
  PYTHONPATH=src python3 src/run_analytics.py \
    --metric all \
    --publish \
    --snapshot-id dev-full-20260912 \
    --output-dir data
  ```

- [x] Verify the new directory contains `manifest.json`, `dashboard_overview.json`, `district_details.json`, and all six analysis files.
- [x] Verify the manifest lists seven datasets and no `_quality` key is present in public artifacts.
- [x] Verify `current.json` points only to `dev-full-20260912`.
- [x] Verify old `dev-employment-*`, `dev-fertility-*`, `dev-policy-support-*`, and other historical snapshots remain unchanged.
- [x] Run the complete data-pipeline analytics test suite and report any existing data-quality warnings separately from code failures.

## Acceptance Criteria

- `--metric all --publish` produces one complete release and updates the pointer once.
- A reader following `current.json` can discover homepage plus all six analyses from one manifest.
- Running an individual metric publish cannot replace the complete current release.
- Existing metric calculations and output paths remain compatible.
- The generated complete release is suitable as the single input for the later DynamoDB loader.
