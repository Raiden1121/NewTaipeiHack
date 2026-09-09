# 新北市青年局預算 PDF 資料源設計

## Goal

將新北市政府青年局官方預算公告頁上的年度預算 PDF，擷取「計畫及預算統計表」，接入既有 NewTaipeiHack data pipeline，產生可追溯、可重跑、可區分預算案與法定預算的 JSON 資料。

## Scope

- 從青年局官方預算列表頁動態發現公告與文件詳情頁，不硬編碼單一 PDF URL。
- 下載公告文件，保留 PDF 原始 artifact、SHA-256、文件標題、公告日期與來源 URL。
- 只解析「計畫及預算統計表」：業務計畫、工作計畫、本年度預算數、比率。
- 保留列表頁可取得的所有年度與版本；至少能同時保存 115 年度法定預算與 116 年度預算案。
- 將資料接入既有 raw、transform、curated、quality、quarantine 流程。
- 預算資料標記為 organization 粒度，不分配到新北市 29 區。

## Non-goals

- 不解析 PDF 內其他費用明細表、歲出計畫說明或資本支出分析表。
- collector 與 transform 不計算年度增減、跨年度占比、青年人均預算或其他 analytics 指標。
- 不修改 Backend、Frontend、AI service 或 AWS deployment。
- 不以 OCR 作為目前文件的主要路徑；目前兩份驗證文件可直接抽取文字。若未來遇到掃描 PDF，應先 quarantine，另行增加 OCR 設計。

## Source facts

- 列表來源：官方青年局預算公告頁。
- 公告標題可包含 預算案、法定版 或 法定預算；後兩者統一為 legal_budget，前者為 proposed_budget。
- 115 與 116 年度驗證文件的目標表均位於 PDF 第 28 頁，標題為 計畫及預算統計表，單位為 新臺幣千元、%。
- PDF 解析應搜尋表格標題與欄位，而非只依賴固定頁碼；頁碼只作為 provenance。

## Dataset contract

Canonical dataset name 為 youth_budgets，使用 PeriodStrategy.ALL_AVAILABLE。一次抓取列表頁上符合標題規則的文件，輸出 key 為 all；每筆 record 以 budget_year_roc、document_status 與 document_id 區分版本。

### Raw record

Collector 回傳的 raw row 保留 PDF 解析後的來源型態，數值欄位先保留字串，讓 transform 負責型別驗證：

    {
      "document_id": "youth_budgets:115:legal_budget:0123456789abcdef",
      "budget_year_roc": "115",
      "document_status": "legal_budget",
      "document_status_label": "法定預算",
      "row_type": "detail",
      "business_plan": "一般行政",
      "work_plan": "一般行政",
      "budget_amount": "56,819",
      "ratio_percent": "26.67",
      "unit_label": "新臺幣千元",
      "table_title": "計畫及預算統計表",
      "source_page_number": 28,
      "source_document_url": "https://www.youth.ntpc.gov.tw/youth/ch/app/data/doc",
      "source_pdf_sha256": "sha256:0123456789abcdef"
    }

### Curated record

Curated records use the common metadata contract with these values:

- dataset: youth_budgets
- source: ntpc_youth_bureau_budget
- geo_level: organization
- district_id and district_name: null
- period_type: year
- period_start / period_end: Gregorian year boundaries converted from ROC year
- metric_id: budget_amount
- value: parsed integer in source unit
- unit: TWD_thousand
- age_scope: not_age_specific
- youth_eligibility: context_only
- domain fields: organization_name, budget_year_roc, document_status, row_type, business_plan, work_plan, budget_ratio_percent, source_pdf_sha256, raw_record

The total row remains a record with row_type=total; detail rows remain separate records. The source-provided ratio is preserved and not recomputed.

## Architecture

### Collector

collectors/youth_budget.py owns HTTP source discovery, HTML link parsing, PDF download validation, SHA-256 calculation, target-page detection, and table-row extraction. It must expose injectable open_url and PDF text-reader seams so tests never call the live source.

The collector returns a typed payload containing JSON-serializable records/metadata plus binary source artifacts. It does not write pipeline JSON itself.

### Artifact persistence

The pipeline adds a small generic source-artifact contract. run_pipeline.py writes PDF bytes under the dataset raw directory and records relative artifact paths in the raw JSON envelope. transform/io.py remains the only layer that writes pipeline files.

### Transform

transform/budget.py parses ROC year, amount, and percentage; validates required labels and non-negative values; builds common metadata; preserves source provenance; and quarantines malformed rows. It does not calculate cross-row or cross-year metrics.

transform/common.py adds the organization geo level. Existing district, county, and national behavior remains unchanged.

### Orchestration

DEFAULT_COLLECTOR_SPECS registers youth_budgets as ALL_AVAILABLE. The output is:

    data/raw/youth_budgets/11501_20260909T120000Z.json
    data/raw/youth_budgets/artifacts/115_legal_budget_0123456789ab.pdf
    data/curated/youth_budgets/all.json
    data/quality/youth_budgets/all.json
    data/quarantine/youth_budgets/all.json

## Validation and failure behavior

Document validation must reject non-PDF bytes, empty downloads, unsupported status labels, missing budget year, missing table title/header, malformed numeric cells, duplicate total rows, and a total row that is absent. A source PDF is not published as curated data when its target table cannot be safely extracted.

After parsing, quality validation checks that the total row exists, detail rows have amounts and ratios, and the source-provided amount/ratio values are finite and non-negative. The amount sum and ratio sum are consistency checks only; they must not replace the source values.

If one listed document fails, the collector records the failed document in the source/quality report and continues only if the remaining documents still produce a valid collection. If no valid document remains, the source execution is an error. Failed raw artifacts and diagnostics remain available for investigation.

## Acceptance criteria

1. Fake listing/detail/PDF responses produce rows for 115 legal and 116 proposed documents without network access.
2. The two verified tables produce four rows each: one total row and three detail rows.
3. 115 values are 213022, 56819, 155903, 300; 116 values are 220101, 60280, 159521, 300 in TWD_thousand.
4. proposed_budget and legal_budget records coexist and do not overwrite each other.
5. Curated records use geo_level=organization, null district fields, and context_only youth eligibility.
6. Raw JSON contains source metadata and artifact references; the downloaded PDFs are hash-addressed and recoverable.
7. Replaying raw JSON does not call the network or require the PDF parser to redownload documents.
8. Focused tests, the full data-pipeline unittest suite, compilation, and git diff --check pass.
