# Youth Budget Allocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將青年局 ROC 116 預算 PDF 的 01–04 工作計畫金額抽取、轉換並發布到既有 `youth_participation` analytics，讓下游未來可直接寫入 DynamoDB，而不修改前端或新增即時查詢計算。

**Architecture:** 延伸既有 `youth_budgets` collector 的 raw row contract，新增 `allocation` row type；transform 將 allocation rows 正規化為新臺幣元；analytics 以設定檔明確指定的 ROC 116 組合四筆 allocation、由 analytics 計算占比並產生品質狀態；published snapshot 只輸出結構化欄位，不帶 PDF 或 `raw_record`。

**Tech Stack:** Python 3、`pypdf`、既有 collector/transform/analytics pipeline、pytest、JSON published snapshots。

**Spec:** `docs/superpowers/specs/2026-09-12-youth-budget-allocation-design.md`

## Global Constraints

- 只修改 `/Users/ray/Desktop/NewTaipeiHack/data-pipeline` 的程式、設定、測試與必要的資料管線產物；不修改 `frontend/`、Backend、Terraform 或 DynamoDB writer。
- 保留既有年度預算趨勢 `budget` 的行為；新增資料放在 `youth_participation/all.json` 的 `budget_allocation`。
- ROC 116 allocation reference year 必須由 `config/homepage_analytics.json` 明確指定為 `116`，不可從 `annual_years_roc` 自動推導。
- 詳細 allocation 缺失時不能讓已有的年度摘要預算失敗；必須留下可檢查的品質狀態與 reason code。
- 不執行 `git add`、`git commit`、merge 或 push。

---

## Task 1: Add failing collector tests for PDF allocation rows

**Files:**

- Modify: `data-pipeline/tests/test_youth_budget.py`
- Reference: `data-pipeline/src/collectors/youth_budget.py`

- [x] Add four detailed-page fixtures representing the source PDF rows `01`–`04`, including the table title, section text, amount, and source sub-row text. Keep the fixture text close to the `pypdf`-extracted form, including `01綜合規劃業務`, `02職涯發展業務`, `03創業資源業務`, and `04青年業務設施`.
- [x] Add a test through `fetch_youth_budgets` that patches page extraction for the ROC 116 document and asserts the returned payload contains four `row_type == "allocation"` rows with codes, names, amounts in TWD, source page numbers, and a total of `159521000`.
- [x] Add an assertion that ordinary `2000`/`3000` sub-items are not emitted as allocation rows.
- [x] Run the focused collector tests and confirm the new assertions fail because the collector currently emits summary rows only.

## Task 2: Implement optional PDF allocation extraction

**Files:**

- Modify: `data-pipeline/src/collectors/youth_budget.py`
- Test: `data-pipeline/tests/test_youth_budget.py`

- [x] Add a dedicated allocation parser/finder, separate from `_find_budget_table`, that scans pages containing `歲出計畫說明提要與各項費用明細表` and `青年發展業務`.
- [x] Parse only top-level codes `01` through `04`; capture `allocation_code`, `allocation_name`, `budget_section`, optional `account_category`, and integer `budget_amount` in TWD. Set `unit_label` to `新臺幣元`, `row_type` to `allocation`, and `metric_id`-independent source fields (`table_title`, `source_page`, `source_row_text`).
- [x] Set `account_category` to the source-supported `設備及投資` for the capital allocation when present; leave it null when the top-level source row does not state a single account category.
- [x] Integrate allocation extraction only in the budget-document path. Preserve all summary rows. If a document has no matching detailed table, retain summary output and record allocation availability/failure metadata without failing the document.
- [x] Ensure document metadata reports the combined row count and allocation row count, while raw records retain document URL/hash linkage.
- [x] Run the focused collector tests and confirm they pass.

## Task 3: Add failing transform tests and support the allocation contract

**Files:**

- Modify: `data-pipeline/tests/test_transform_budget.py`
- Modify: `data-pipeline/src/transform/budget.py`

- [x] Add an allocation raw-row fixture with the four source fields and `unit_label == "新臺幣元"`.
- [x] Add a test asserting an allocation transforms into a curated row with `row_type == "allocation"`, `metric_id == "budget_allocation_amount"`, `unit == "TWD"`, an integer amount, and preserved allocation identity/source fields.
- [x] Run the focused transform test and confirm it fails before production changes.
- [x] Extend the accepted row types with `allocation` and branch allocation handling before the existing summary/settlement branches. Require the TWD unit, preserve `ratio_percent` as null, and keep existing `total`/`detail`/`final_settlement` behavior unchanged.
- [x] Run all budget collector/transform tests.

## Task 4: Add explicit reference configuration and allocation analytics

**Files:**

- Modify: `data-pipeline/src/analytics/config.py`
- Modify: `data-pipeline/config/homepage_analytics.json`
- Add: `data-pipeline/src/analytics/budget_allocation.py`
- Add: `data-pipeline/tests/test_budget_allocation.py`
- Modify: `data-pipeline/tests/test_analytics_input_resolver.py`

- [x] Add the failing config assertion that the loaded homepage config exposes `budget_allocation_reference_year_roc == 116`.
- [x] Add focused analytics tests for four complete allocation rows: the calculated total is `159521000`, each item has an analytics-calculated two-decimal share, and the expected shares are `24.42%`, `23.65%`, `44.50%`, and `7.43%`.
- [x] Add quality tests for incomplete rows and source-total mismatch; these cases must not be marked `observed` and must expose stable reason codes, including `budget_allocation_total_mismatch` for a mismatch.
- [x] Implement `calculate_budget_allocation(records, *, reference_year_roc)` as a pure function. Select allocation rows for the explicit year and document status, preserve allocation identity/section/category, calculate percentages with decimal half-up rounding, and expose status, source period, coverage, and blocking reasons.
- [x] Add `budget_allocation_reference_year_roc` to `HomepageAnalyticsConfig` validation and set it to `116` in the JSON config.
- [x] Run the new analytics/config tests and confirm they pass.

## Task 5: Publish allocation analytics without changing existing metrics

**Files:**

- Modify: `data-pipeline/src/analytics/youth_participation.py`
- Modify: `data-pipeline/tests/test_youth_participation.py` or `data-pipeline/tests/test_run_analytics.py` as needed for the existing fixture structure.
- Modify: `data-pipeline/tests/test_run_analytics.py` for every hand-built homepage config dictionary.

- [x] Load all `youth_budgets` records once and call `calculate_budget_allocation` with the new explicit config field.
- [x] Add the result under `budget_allocation` in the youth participation analytics object. Keep the existing `budget` series unchanged and add the allocation status/reasons/time policy to quality metadata without converting unrelated partial sources to observed.
- [x] Ensure the public allocation object contains no `raw_record`, `raw_records`, PDF bytes, or internal collector-only fields.
- [x] Update every test config fixture to include the new required reference year and add an integration assertion that the allocation object is embedded in the generated/published youth participation result.
- [x] Run focused youth participation and analytics runner tests.

## Task 6: Regenerate the youth budget data and published snapshot

**Files:**

- Generated/updated under `data-pipeline/data/raw/youth_budgets/`, `data-pipeline/data/curated/youth_budgets/`, `data-pipeline/data/analytics/`, and `data-pipeline/data/quality/` by the existing commands.

- [x] Refresh the existing `youth_budgets` source with the standard strict pipeline command so the local raw artifact and records include the ROC 116 allocation rows.
- [x] Run the existing all-metrics analytics publish command with a new snapshot ID; do not edit frontend files.
- [x] Verify the ROC 116 curated output contains exactly four allocation rows and the four amounts sum to `159521000`.
- [x] Verify `data/analytics/youth_participation/all.json` contains `budget_allocation` with the four calculated shares and that the existing annual `budget` series remains present.
- [x] Verify the published snapshot and `current.json` pointer include the new analytics object and contain no raw fields.

## Task 7: Full verification and handoff

**Files:**

- No additional source changes unless verification identifies a concrete failure.

- [x] Run the full data-pipeline pytest suite.
- [x] Run `git diff --check` and inspect the final diff/stat, preserving unrelated user changes and generated artifacts already in the working tree.
- [x] Re-run targeted JSON assertions against raw, curated, analytics, quality, and published outputs.
- [x] Report exact modified files, commands run, verified values, and the explicit boundary: this implementation is DynamoDB-ready in schema/output shape but does not write to AWS.
