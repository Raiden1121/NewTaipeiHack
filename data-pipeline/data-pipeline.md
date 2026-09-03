# Data Pipeline

## Purpose

Data Pipeline 是系統統計數字的主要計算來源，預計把政府 Open Data、新北市資料與青年局資源整理成可供 Backend 與 AI 使用的資料。

目前已建立本地完整 pipeline；`run_pipeline.py` 會依來源的期間策略排程 collect、raw output、transform、quality/quarantine output，並寫出可供後續 analytics 使用的 authoritative index。AWS load 與跨資料集 analytics 尚未接入。

## Responsibilities

規劃使用 Python、AWS Lambda、S3、DynamoDB、Step Functions 與 EventBridge：

```text
run_pipeline.py
  ├── Collect
  ├── Raw JSON
  ├── Transform
  ├── Quality / Quarantine
  └── Curated JSON
      ↓
Analytics
      ↓
Load
```

資料來源可能包含內政部戶政司、台灣就業通、勞動部、新北 Open Data、TDX 與新北市青年局。

## Project Usage

預計處理行政區名稱、日期、年齡、地址、座標與 Spatial Join，統一到新北市 29 區及明確資料期間。

Analytics 可能計算青年人口、YoY、Cohort Retention Signal、職缺／薪資、居住、交通、Resource Access、Resource Gap、Opportunity Index、Demand Index、Mismatch Index 與 Retention Risk inputs。

## Inputs & Outputs

- 完整流程輸入：資料來源 API／collector；raw 會先保存到本地，之後才進入 transform。
- 重跑流程輸入：已儲存的本地 raw JSON；使用 `--input` 時不會呼叫 live API。
- 本地輸出：`data/raw/`、`data/curated/`、`data/quality/`、`data/quarantine/`。
- 未來輸出：S3 Raw／Curated Data、DynamoDB 指標與 AI Evidence。

## Pipeline Usage

指定一個 ROC 月份，執行所有非 TDX collectors：

```bash
cd data-pipeline
python src/run_pipeline.py --period 11507 --output-dir data
```

抓取一段連續歷史期間（包含起訖月份）：

```bash
python src/run_pipeline.py \
  --start-period 11001 \
  --end-period 11507 \
  --output-dir data
```

歷史期間會依 source-aware schedule 分開輸出：`monthly` 每月一次、`annual` 每 ROC 年一次、`snapshot` 整段只抓一次並寫入 `{dataset}/latest.json`、`all_available` 整段只抓一次並寫入 `{dataset}/all.json`。有期間分區的輸出為 `data/curated/{dataset}/{period}.json`、`data/quality/{dataset}/{period}.json` 與 `data/quarantine/{dataset}/{period}.json`；空資料期間跳過 transform，其狀態與來源訊息記錄在 `data/quality/collection_range.json` 的 `execution_units`，整段執行摘要也使用同一檔案。

若要抓取 TDX 公車、鐵路、YouBike（這些是目前快照，不屬於歷史期間），且環境已設定 TDX credentials：

```bash
python src/run_pipeline.py --period 11507 --include-tdx --output-dir data
```

單一來源失敗時，預設會記錄到 `data/quality/collection.json` 並繼續其他來源；需要讓失敗回傳非零 exit code 時加上 `--strict`。

## Source-aware recovery / resume

歷史 recovery 的正式指令如下；它會把 monthly/annual 的缺漏單位與 snapshot/all-available 的單一執行單位分開處理，並在 `--strict` 下只要仍有 error 就以非零 exit code 結束。

```bash
cd data-pipeline
python src/run_pipeline.py \
  --start-period 10501 \
  --end-period 11507 \
  --output-dir data \
  --resume \
  --strict
```

排程與 output key：

| `period_strategy` | 執行方式 | curated / quality / quarantine key |
|---|---|---|
| `monthly` | 每個 ROC `yyyMM` 一次 | `{dataset}/{yyyMM}.json` |
| `annual` | 範圍內每個 ROC 年一次 | `{dataset}/{yyy}.json` |
| `snapshot` | 不當作歷史月，整段只抓一次 | `{dataset}/latest.json` |
| `all_available` | 完整來源只抓一次，資料期間由來源 record 決定 | `{dataset}/all.json` |

`--resume` 先讀前次 collection report 與相符 raw/output，決策如下：

- `reused_output`：前次為 `ok`、schema/transform version 相符且 curated output 存在；不呼叫 collector，也不重新 transform。
- `reused_raw`：有相符 raw（包含沒有 schema version 的 legacy report）；不下載，重新 transform 並寫出目前 output。
- `downloaded`：沒有可重用 raw/output、前次 error、output 遺失，或未使用 `--resume` 時進入 collector 下載路徑；成功時才寫 raw 再 transform。此 flag 表示本次嘗試 collect，即使 collector 最後 error 也可能為 `true`，不能單獨當作成功判定。
- `retried`：只針對 transient network timeout 的 collection retry；它在 terminal log 顯示為 `collect retry`，report 以 `attempts > 1` 表示，並沒有獨立的 `retried` boolean 欄位。schema、validation、`no_data` 與 unsupported-year 不 retry。
- `skipped/no_data`：`CollectorNoDataError` 或空 records 會標記 `status: "skipped"`、`reason: "no_data"`，不寫 curated output；resume 預設保留這個結果。

`--force` 與 `--resume` 互斥，會忽略既有 report/raw/output，重新下載所有已排程 execution units（包含 `latest` 與 `all` 的單一單位）。

每次 full/range run 都會更新 `data/quality/dataset_index.json`。它只列出本次 `status: "ok"` 的 authoritative curated files、dataset、period strategy、source period 與 transform version；analytics 應只讀這份 index。舊的重複 snapshot 或舊 partition 檔不會自動刪除，也不應由 analytics 直接掃描使用。

以上 partition/key 規則適用於 `--start-period`/`--end-period` range mode。相容的單月 `--period` full mode 仍寫入舊式平面路徑 `data/curated/{dataset}.json`、`data/quality/{dataset}.json`、`data/quarantine/{dataset}.json`；不可把這些平面輸出誤認成 range mode 的 `latest`、`all` 或歷史 partition。

## Raw Replay / Transform Usage

```bash
cd data-pipeline
python src/run_pipeline.py \
  --dataset population \
  --input data/raw/population/example.json \
  --output-dir data
```

青年核心資料只接受可證明包含 18–35 歲（含 18、35）的 `eligible` records。官方年齡組維持 `proxy_only`，沒有年齡欄位的資料維持 `context_only`。缺失值使用 JSON `null`，不可用 0 補值；縣市或全國粒度也不可人工拆成 29 區。完整欄位與規則見 `src/transform/transform.md`。

Dataset 名稱會由固定白名單轉為 canonical 名稱，例如 `moving_in → movement`、`job_vacancy_salary → job_vacancy_salaries`、`bus_stop → bus_stops`。9621/9622 教育資料使用 `overview_records/detail_records` 雙來源 envelope；官方薪資保留 collector 的 `records/metadata` envelope。完整支援清單與輸入格式見 `src/transform/transform.md`。

## Boundaries

Data Pipeline 負責抓資料、清理、標準化與計算數字。Frontend 與 LLM 不應取代這一層；職缺與畢業生資料也不能直接相減解釋成精確缺工人數。
