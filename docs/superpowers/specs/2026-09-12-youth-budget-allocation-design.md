# 青年局 116 年預算分配 PDF → Data Pipeline 設計

**Date:** 2026-09-12  
**Status:** Design confirmed in chat; implementation follows the written-spec review checkpoint

## Goal

延伸既有 `youth_budgets` 資料流，從青年局 116 年度預算 PDF 抽取「青年發展業務」的 01～04 一級分配明細，產生可供後續 Frontend／Backend／DynamoDB loader 使用的 curated 與 analytics JSON。

本次只修改 data pipeline。Frontend、Backend、DynamoDB table、DynamoDB writer 與 Terraform 不在本次實作範圍。

## Source and target values

來源 artifact：

```text
data/raw/youth_budgets/artifacts/116_proposed_budget_881ef74b2f54.pdf
```

PDF 的「歲出計畫說明提要與各項費用明細表」位於第 41～45 頁，需抽取以下一級明細：

| 編號 | 來源名稱 | 預算金額（TWD） | 來源區段 |
|---|---|---:|---|
| 01 | 綜合規劃業務 | 38,960,000 | 經常門 |
| 02 | 職涯發展業務 | 37,730,000 | 經常門 |
| 03 | 創業資源業務 | 70,979,000 | 經常門 |
| 04 | 青年業務設施 | 11,852,000 | 資本門 |

四筆金額合計為 `159,521,000`。比例由 analytics 依金額計算並四捨五入至小數點 2 位：`24.42%`、`23.65%`、`44.50%`、`7.43%`。

## Data flow

```text
official budget listing/detail/PDF
        ↓
youth_budget collector
        ↓
raw/youth_budgets/{snapshot}.json + artifacts/*.pdf
        ↓
budget transform
        ↓
curated/youth_budgets/all.json
        ↓
analytics/youth_participation/all.json
        ↓
future DynamoDB loader
```

既有摘要預算列維持原狀；新明細與摘要共用 `youth_budgets`，不新增第二次 PDF 下載或另一個資料集。

## Collector design

在既有 `youth_budget.py` 新增詳細表抽取邏輯，與目前摘要表抽取分開：

- 摘要表仍抽取 `total`／`detail` rows，單位維持來源的 `新臺幣千元`。
- 詳細表只抽取編號 01～04 的一級列，不抽取 `2000`、`3000`、`2036` 等用途別科目或其下的細項。
- 每筆詳細 raw row 使用 `row_type: "allocation"`，保留 `allocation_code`、`allocation_name`、`budget_section`、`account_category`、`source_page_number`、`source_row_text`、`source_pdf_sha256` 與來源 URL。
- 04 項保留 PDF 的來源名稱「青年業務設施」，並記錄 `account_category: "設備及投資"`，不在 raw 層改寫成展示文字。
- 詳細表抽取是可選擴充：若歷史文件沒有相同表格，既有摘要預算仍可成功產出；allocation 解析失敗需留下 quality／document failure，不可靜默產生錯誤明細。

## Curated contract

`transform_youth_budgets` 擴充既有 row type 與單位驗證：

```json
{
  "row_type": "allocation",
  "allocation_code": "01",
  "allocation_name": "綜合規劃業務",
  "business_plan": "青年發展業務",
  "work_plan": "綜合規劃業務",
  "budget_section": "經常門",
  "budget_amount": 38960000,
  "metric_id": "budget_allocation_amount",
  "value": 38960000,
  "unit": "TWD",
  "budget_year_roc": "116",
  "document_status": "proposed_budget"
}
```

摘要預算仍使用 `metric_id: "budget_amount"` 與 `unit: "TWD_thousand"`；決算資料的既有 `TWD` contract 不變。

## Analytics contract

在既有 `youth_participation/all.json` 新增 `budget_allocation`，不改變既有 `budget.trend` 與 `budget.execution`：

```json
{
  "metric_id": "youthBudgetAllocation",
  "budget_year_roc": 116,
  "document_status": "proposed_budget",
  "total_amount": 159521000,
  "unit": "TWD",
  "items": [
    {
      "code": "01",
      "name": "綜合規劃業務",
      "amount": 38960000,
      "share_percent": 24.42,
      "budget_section": "經常門"
    }
  ],
  "status": "observed",
  "source_datasets": ["youth_budgets"],
  "source_period": ["116"]
}
```

資料選擇使用設定檔的明確 `budget_allocation_reference_year_roc: 116`，避免把 116 年預算誤併入目前 110～114 的年度趨勢，也避免日後新年度文件自動替換本次指定資料。若指定年度沒有完整四筆明細，輸出 `unavailable`／`partial` 與 quality reason，不使用常數補值。

## Quality and compatibility

- 驗證四筆 allocation 金額合計等於來源摘要「青年發展業務」金額乘以 1,000。
- 若總額不一致，保留資料但標記 `budget_allocation_total_mismatch`，analytics 不標示為 `observed`。
- `budget_allocation` 不含 `raw_record` 或 PDF bytes，符合 published public payload 規則。
- 每筆資料保留 snapshot、年度、allocation code、metric id 與來源 hash，未來可直接映射到 DynamoDB item；本次不實作寫入。

## Tests and acceptance

新增／修改測試涵蓋：

1. collector 能從詳細表文字抽取唯一的 01～04 一級列與正確頁碼。
2. collector 不把用途別科目當成一級分配列。
3. transform 接受 `allocation` row 與 `新臺幣元`，並維持既有摘要／決算 contract。
4. analytics 產生 116 年 `budget_allocation`、四筆金額、總額與四捨五入比例。
5. 既有 `budget.trend`／`budget.execution` 結果與 110～114 年期間不變。
6. full analytics published snapshot 包含新的 allocation payload，且 public payload 不含 raw fields。

驗收命令：

```bash
cd /Users/ray/Desktop/NewTaipeiHack/data-pipeline
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile monthly \
  --datasets youth_budgets \
  --force \
  --strict \
  --retention-years 8 \
  --output-dir data
PYTHONPATH=src .venv/bin/python src/run_analytics.py \
  --metric all \
  --publish \
  --output-dir data \
  --config-dir config
```
