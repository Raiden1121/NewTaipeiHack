# ROC 103 Historical Population Denominator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion.

**Goal:** 將官方 ROC 10312 新北市單一年齡人口資料接入既有 `population` 管線，讓 ROC 103 青年參政的每十萬參選率與 YRR 取得精確 18–35 歲人口分母。

**Architecture:** 新增獨立 historical population collector 作為來源 adapter；輸出既有 `population` raw 欄位與 `CollectedPayload` artifact，沿用 `transform_population`、dataset index 與 youth participation analytics。retention 以 protected partition 保留 `population/10312`。

**Tech Stack:** Python standard library (`urllib`, `zipfile`, `csv`, `hashlib`)、既有 JSON pipeline、`unittest`。

**Spec:** [`docs/superpowers/specs/2026-09-12-historical-population-10312-design.md`](../specs/2026-09-12-historical-population-10312-design.md)

## Global Constraints

- 10312 使用官方單一年齡資料，不用五歲組估算。
- 不改變既有 `population` canonical output schema 與 analytics 公式。
- ODRP014 仍作 10701 以後人口來源；歷史 adapter 只註冊已確認的 10312。
- 保留完整下載 ZIP 的 SHA-256 artifact；raw records 只做必要欄位 normalization。
- 不把 10312 轉成 `population_villages` 服務涵蓋率資料。
- 不執行 `git add`、commit、merge 或 push。

## Task 1: Collector tests first

**Files:**

- Create: `data-pipeline/tests/test_historical_population_collector.py`

測試記憶體 ZIP、UTF-8 BOM、必要欄位、18–35 歲欄位轉換、來源 artifact metadata、錯誤 ZIP，以及 `fetch_population_for_period("10312")` 的 source routing。先執行並確認因 module/介面不存在而失敗。

## Task 2: Historical source adapter

**Files:**

- Create: `data-pipeline/src/collectors/historical_population.py`

實作官方 10312 resource URL、ZIP member discovery、CSV 解析、來源欄位驗證、canonical raw normalization、`CollectedPayload` metadata 與 SHA-256 `SourceArtifact`。未支援的歷史月份拋出 `CollectorNoDataError`，格式或內容錯誤拋出專用 collector error。

## Task 3: Register source routing and retention protection

**Files:**

- Modify: `data-pipeline/src/collectors/population_collector.py`
- Modify: `data-pipeline/src/run_pipeline.py`
- Modify: `data-pipeline/src/orchestration/retention.py`
- Modify: `data-pipeline/tests/test_orchestration_retention.py`

讓 `population` spec 對 `10312` 使用歷史 adapter，其餘月份維持 ODRP014。新增 election population anchor protected partition mapping（`10312`、`10712`、`11112`），測試 rolling retention 不刪除這三個年度分母的 raw/curated/index，同時仍刪除一般過期月份。

## Task 4: Materialize and regenerate analytics

使用官方 live ZIP 執行只含 `population` 的 `10312` range，確認 29 區、1,032 村里、總人口 `3,966,818`、18–35 歲總人口 `1,086,392`，並寫入 curated、quality、raw artifact 與 authoritative index。再執行 youth participation analytics，確認 ROC 103 V1 的 candidacy rate 與 YRR 不再因人口分母為 null。

## Task 5: Documentation and verification

更新 population data description、data gap registry 與 analytics gap 說明，明確區分「ODRP014 查無 103」與「已由歷史官方 archive 補足 10312」。執行 focused tests、完整 test discovery、JSON/schema/count checks，最後檢視 diff 與 git status。
