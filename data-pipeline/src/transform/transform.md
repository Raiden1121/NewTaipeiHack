# Transform Contract

`transform/` 只處理已儲存的 raw records，不呼叫 live API，也不計算 YoY、中位數、相關性、Opportunity Index 或 Retention Risk。這些跨資料集指標屬於 `analytics/`。

## Common metadata

每筆 curated record 均含 `dataset`、`source`、`source_record_id`、`geo_level`、`district_id`、`district_name`、`period_start`、`period_end`、`period_type`、`metric_id`、`value`、`unit`、`age_scope`、`age_min`、`age_max`、`youth_eligibility`、`fetched_at`、`quality_flags`。來源欄位另存於 `raw_record` 或 `raw_records`，不覆寫原值。

## Age rules

- `exact_18_35`／`derived_18_35` 包含 18 與 35，且只能搭配 `eligible`。
- 官方年齡組保留原分組，標為 `official_age_group_proxy/proxy_only`，不得拼成精確 18–35。
- 無年齡欄位的遷徙、婚姻、住宅、職缺、訓練與交通資料標為 `all_ages` 或 `not_age_specific`，並搭配 `context_only`。
- 缺失值一律是 JSON `null`，不以 0 代替。

## Geography rules

區級資料使用 `config/districts.json` 的新北市 29 區 `district_id`。名稱、官方代碼、郵遞區號與 TDX 座標只有在可靠對應時才填入；無法對應不得使用最近行政區。縣市與全國資料維持 `county`／`national`，不人工拆區。

## Local output

```text
data/raw/{dataset}/{snapshot}.json
data/curated/{dataset}/{period-or-key}.json
data/quality/{dataset}/{period-or-key}.json
data/quarantine/{dataset}/{period-or-key}.json
data/quality/dataset_index.json
```

完整抓取、清理與輸出：

```bash
cd data-pipeline
python src/run_pipeline.py --period 11507 --output-dir data
```

抓取連續歷史月份：

```bash
python src/run_pipeline.py \
  --start-period 11001 \
  --end-period 11507 \
  --output-dir data
```

來源採 source-aware schedule：`monthly` 每個 ROC 月執行一次、`annual` 每個 ROC 年執行一次、`snapshot` 在整個範圍只執行一次並使用 `latest.json`、`all_available` 只執行一次並使用 `all.json`。因此每個有期間分區的單位獨立寫入 `curated/{dataset}/{period}.json`、`quality/{dataset}/{period}.json` 與 `quarantine/{dataset}/{period}.json`；snapshot/all-available 分別寫入三個目錄的 `{dataset}/latest.json`／`{dataset}/all.json`。沒有資料的單位只保留 raw 與 collection report，不產生 curated；範圍摘要寫入 `quality/collection_range.json`。

加入 `--include-tdx` 才會執行需要 credentials 的 TDX collectors。來源失敗會寫入 `data/quality/collection.json`；加上 `--strict` 時，只要任一來源失敗就回傳非零 exit code。

## Recovery output contract

```bash
cd data-pipeline
python src/run_pipeline.py \
  --start-period 10501 \
  --end-period 11507 \
  --output-dir data \
  --resume \
  --strict
```

`--resume` 是 runner 的 collection/recovery 模式，而不是 `--input` replay 的替代品。每個 execution unit 的 collection report 至少記錄 `status`、`action`、`attempts`、`downloaded`、`reused_raw`、`reused_output`、`source_period`、`output_key` 與 `period_strategy`。

- `reused_output`：符合目前 schema/transform version 且檔案存在的 curated output；不會再 collect 或 transform。
- `reused_raw`：選到與 source period 相符的 raw（snapshot 取最新 raw）；只重新 transform。
- `downloaded`：本次進入 collector 下載路徑；成功時保存 raw。前次 error、缺 raw/output 或沒有 resume 時都會走此路徑；collector 最後 error 時此欄位仍可能是 `true`，所以成功與否必須看 `status`。
- `retried`：僅 transient network timeout 會在 collection 階段 retry；以 terminal `collect retry` 與 report 的 `attempts > 1` 表示，沒有獨立 boolean。
- `skipped/no_data`：來源明確無資料或 raw records 為空，report 為 `status: "skipped"`、`reason: "no_data"`，不產生 curated；resume 預設維持 skipped。

TaiwanJobs 若在有效回應中混入已知外縣市或其他新北市行政區，collector 只排除不符合 query 的列，不會將其改標；保留列會帶 `query_filtered_row_count` 與 `query_warnings`，transform 會將 warning 寫入 curated `quality_flags` 與 quality report。若整份回應都不符合，或 `CITYNAME` 格式無法辨識，collector 仍回報 error。

`--force` 與 `--resume` 互斥；它忽略既有狀態，重新下載所有排程 unit。`latest` 是 snapshot 的唯一 output key，`all` 是 all-available 的唯一 output key，兩者不應被當成歷史月。

`data/quality/dataset_index.json` 是 analytics 的 authoritative curated-file 清單。它只收錄本次成功的 `{dataset, path, period_strategy, source_period, transform_version}` entries；不要以目錄 glob 讀取 curated。為避免破壞既有資料，legacy 重複 snapshot/partition 檔不會自動刪除，也不會因為存在於目錄中而進入 index。

上述 `{period-or-key}` 路徑是 range mode 的輸出合約。相容的單月 `--period` full mode 仍寫入平面 `curated/{dataset}.json`、`quality/{dataset}.json`、`quarantine/{dataset}.json`；它不使用 range mode 的歷史 partition、`latest` 或 `all` key。

執行已儲存的 raw JSON：

```bash
cd data-pipeline
python src/run_pipeline.py --dataset population --input data/raw/population/example.json
```

`--input` 是相容的 replay 模式；它只執行 transform/output，不會重新呼叫 live API。

## Supported datasets

| Canonical dataset | Collector aliases | Raw input |
|---|---|---|
| `population` | — | `{"records": [...]}` |
| `movement` | `moving_in` | `{"records": [...]}` |
| `births` | `birth_nums` | `{"records": [...]}` |
| `marriages` | `marriage_nums` | `{"records": [...]}` |
| `house_prices` | `house_price` | `{"records": [...]}` |
| `rentals` | `rental_price` | `{"records": [...]}` |
| `job_vacancies` | `job_vacancy` | `{"records": [...], "fetched_at": "ISO timestamp"}` |
| `job_vacancy_salaries` | `job_vacancy_salary` | `{"records": [...], "fetched_at": "ISO timestamp"}` |
| `wages` | `wage` | `{"records": [...], "metadata": {"fetched_at": "..."}}` |
| `college_majors` | `college_major` | `{"overview_records": [...], "detail_records": [...]}` |
| `graduate_majors` | `graduate_major` | `{"records": [...]}` |
| `vt_courses` | `vt_course` | `{"records": [...]}` |
| `training_numbers` | `training_nums` | `{"records": [...]}` |
| `talent_demand` | — | `{"records": [...]}` |
| `youth_budgets` | — | `{"records": [...], "documents": [...], "source_artifacts": [...]}` |
| `bus_stops` | `bus_stop` | `{"records": [...]}` |
| `railway_stops` | `railway_stop` | `{"records": [...]}` |
| `bike_stops` | `bike_stop` | `{"records": [...]}` |
| `babysitting_places` | `babysitting_place`, `Babysitting_place` | `{"records": [...], "source_datasets": [...]}` |

Alias 會先轉成 canonical dataset；curated record 的 `dataset`、輸出檔名與資料夾一律使用 canonical 名稱。職缺是時間快照，raw envelope 應提供 `fetched_at`；缺少時仍保留資料，但 quality 會加入 `missing_snapshot`。

## `babysitting_places`：私托與公托名冊

collector 會呼叫新北市資料開放平台的私托與公托 JSON endpoint，合併成一個 `snapshot` dataset；每筆 raw record 帶有 `care_type`（`private`／`public`）與 `source_dataset_id`。來源沒有歷史年度參數，因此 `latest.json` 只代表最近一次抓取結果。

curated record 使用 district grain；`areacode` 優先透過 `config/districts.json` 對應行政區，無法對應時保留 `district_id=null`。來源沒有年齡欄位，所有列使用 `not_age_specific`／`context_only`。私托 `person` 轉為非負整數 `capacity`，公托缺少收托人數時保留 JSON `null`。

## `youth_budgets`：青年局年度預算

collector 只保存官方 PDF 的「計畫及預算統計表」；raw envelope 另含 `documents` 與 `source_artifacts`，PDF artifact 以 SHA-256 命名，讓 raw replay 不必重新下載來源文件。`proposed_budget` 與 `legal_budget` 由 `document_id`、ROC 年度、版本與 PDF hash 區分，不能用年度單一 key 覆蓋。

curated record 使用 organization grain，不將機關預算分配到新北市 29 區：

| Field | Contract |
|---|---|
| `geo_level` | `organization` |
| `district_id`, `district_name` | JSON `null` |
| `period_type` | `year`；ROC 年轉 Gregorian 年邊界 |
| `metric_id`, `value`, `unit` | `budget_amount`、解析後整數、`TWD_thousand` |
| `age_scope`, `youth_eligibility` | `not_age_specific`、`context_only` |
| `budget_ratio_percent` | 來源提供的比率；不由 pipeline 重算 |
| domain fields | `organization_name`、`budget_year_roc`、`document_status`、`row_type`、`business_plan`、`work_plan`、`source_pdf_sha256`、`raw_record` |

total row 與 detail row 分別保存；不加總 detail、不把千元換算成元。缺少 business/work plan、未知版本、非有限或負數值會進 quarantine，且保留 `raw_record`。
