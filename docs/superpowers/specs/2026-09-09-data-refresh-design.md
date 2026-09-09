# Data Pipeline Source-Aware Refresh Design

## Goal

讓 data pipeline 依資料來源的更新需求執行 daily、weekly、monthly refresh，避免每天重抓完整歷史資料，並讓失敗與查無資料的 execution unit 可以在下次到期時安全重試；資料保留最近五年，超過保留窗的 local JSON 在成功更新後清理。

## Current Problems

目前 `PeriodStrategy` 只描述來源資料如何分區：monthly、annual、snapshot、all_available；它不是 wall-clock scheduler。`run_pipeline.py` 仍需要人工執行，沒有依 dataset 選擇 refresh 頻率，也沒有獨立的 refresh state。`--resume` 會重用成功輸出或既有 raw，適合 recovery，不適合判斷來源是否已經有新資料。

先前 population 下載曾發生 `IncompleteRead`。目前 retry taxonomy 沒有把這類中斷讀取明確視為 transient error，因此 refresh mode 需要補上可重試分類。

## Confirmed Refresh Policy

這是第一版建議的檢查頻率，不代表來源機關的正式發布承諾：

| Profile | Datasets | Purpose |
|---|---|---|
| `daily` | `job_vacancies`, `job_vacancy_salaries` | 職缺與薪資變動較快 |
| `weekly` | `house_prices`, `rentals`, `vt_courses`, `training_numbers` | 完整快照資料量大，不每天重抓 |
| `monthly` | `population`, `movement`, `births`, `marriages`, `wages`, `college_majors`, `graduate_majors`, `talent_demand`, `youth_budgets`, `bus_stops`, `railway_stops`, `bike_stops` | 人口、年度資料、預算與靜態資料的定期檢查 |

daily 使用 24 小時間隔，weekly 使用 7 天間隔，monthly 以日曆月份切換判斷是否到期。年度資料使用 monthly profile 檢查來源是否已公布新的完整年度；資料尚未完整時維持 `skipped/no_data`，下一個 monthly window 到期後仍會重新檢查。青年預算平時每月檢查，預算文件集中發布期間可由外部 scheduler 額外呼叫 weekly profile 或手動執行。

設定檔可列出 TDX dataset；未指定 `--include-tdx` 時，這些名稱仍是合法的 supported dataset，但不會加入 active collector specs，也不會執行。指定 `--include-tdx` 後才會執行 TDX units。

## Architecture

`PeriodStrategy` 與 wall-clock refresh cadence 分離：

```text
refresh_profiles.json
        ↓
orchestration.refresh
        ↓ 只選目前到期的 datasets
orchestration.schedule
        ↓ 依 monthly/annual/snapshot/all_available 建立 execution units
run_pipeline.py
        ↓
collector → raw → transform → curated/quality/quarantine
        ↓ collection 成功後
orchestration.retention → local JSON cleanup + dataset index
```

refresh profile 只負責「哪些資料應該被檢查」。既有 `schedule.py` 的 source-aware period planning 仍負責「每個資料要用什麼 source period 與 output key」。

## Refresh State

新增 generated file：`data/quality/refresh_state.json`。每個 dataset/output key 記錄：

- `last_started_at`
- `last_success_at`
- `last_checked_at`
- `status`
- `source_period`
- `output_key`
- `attempts`
- `error` 或 `source_message`

state 不取代 raw、curated 或既有 collection reports。它只用來判斷 refresh 是否到期與是否需要 failed-only retry；資料清理由獨立 retention policy 控制，不由 state 直接刪除檔案。

## Rolling Retention

資料保留策略與儲存方式分離。第一版以 `data/` 下的 local JSON 為 storage operation，未來搬到 S3 時替換 storage operation，不把 S3 SDK 放入 collector 或 retention policy。

目前保留窗預設為前五個完整年度加上目前年度，也就是以目前 ROC 年往前推算五個完整歷史年度。以 `11509` 為例，月資料從 `11001` 保留到目前月份，年資料保留 `110`～`115`。月資料以 `source_period` 或 partition key 判斷；snapshot 保留最新 curated output；all-available 資料依 record 內可辨識的年度或日期欄位過濾，但未來年度資料不因為晚於目前年度而刪除。無法辨識期間的資料保留，不進行猜測式刪除。

清理只在本次 collection 沒有 error 時執行，並寫入 `data/quality/retention_report.json`。清理範圍包含可判斷期間的 raw、curated、quality、quarantine 與 `dataset_index.json` entries；清理後 index 必須只指向仍存在的 curated 檔案。首次建立資料仍使用 historical range 先抓最近五年，後續 refresh 只抓到期單位。

## CLI Contract

新增 refresh mode：

```bash
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile daily \
  --output-dir data \
  --strict
```

可選 dataset 與失敗重跑：

```bash
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile daily \
  --datasets job_vacancies,job_vacancy_salaries \
  --failed-only \
  --output-dir data \
  --strict
```

既有 `--period`、`--start-period/--end-period`、`--resume`、`--force` 與 `--input` replay contract 不變。`--refresh-profile` 不與歷史 range mode 混用。

refresh mode 對於已到期的 unit 會進行 fresh collection；未到期的 unit 不呼叫 collector。`--failed-only` 只選上一次 status 為 `error` 的 unit，不會把 `no_data` 當成永久失敗或永久忽略。

## Error and Retry Policy

以下錯誤可以 retry，最多 3 次，backoff 1 秒、2 秒：

- `TimeoutError`
- `socket.timeout`
- timeout 型態的 `URLError`
- `http.client.IncompleteRead`
- `ConnectionResetError`

schema、validation、unsupported-year 與 `CollectorNoDataError` 不 retry。`CollectorNoDataError` 產生 `skipped/no_data`，但 refresh state 仍保留 `last_checked_at`，下一個 cadence window 到期後可重新查詢。

## Output and Scheduling Boundary

本次只實作 repo 內的 refresh profile、CLI、state、report 與文件，不加入 AWS infrastructure。AWS EventBridge、ECS Fargate 或 Batch 之後只需要定時呼叫相同 CLI；本機可先用 cron 或手動命令驗證。

`data-pipeline/data/data_description.md` 不在本次修改範圍，因為它描述資料內容與欄位；更新頻率屬於 `refresh_profiles.json` 與 `data-pipeline.md` 的操作設定。

## Acceptance Criteria

1. daily、weekly、monthly profile 的 dataset 對應完整且無重複。
2. refresh mode 只執行到期的資料集，不重抓未到期資料。
3. monthly profile 能重新檢查之前的 annual `no_data`。
4. `--datasets` 能縮小執行範圍，`--failed-only` 只處理上一次錯誤 unit。
5. `IncompleteRead` 在前兩次失敗、第三次成功時會成功完成；三次失敗會留下 error 與 attempts=3。
6. 既有 historical range、resume、force、replay 測試不受影響。
7. collection 成功後只保留最近五年的可判斷資料，並同步更新 dataset index；collection 有 error 時不執行清理。
8. retention policy 不依賴 AWS SDK，未來可由 S3 storage operation 實作相同介面。
