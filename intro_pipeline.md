# Analytics Pipeline Intro

本文件介紹兩個負責「分析執行」與「分析發布」的核心程式：

- [`data-pipeline/src/run_analytics.py`](data-pipeline/src/run_analytics.py)：CLI 入口與 analytics orchestration。
- [`data-pipeline/src/analytics/published_snapshot.py`](data-pipeline/src/analytics/published_snapshot.py)：將分析結果整理成版本化、可被 Backend／Frontend 讀取的 published snapshot。

## 一、在整體資料流程中的位置

```text
官方公開資料
    ↓
collector / run_pipeline.py
    ↓
raw → transform → curated
    ↓
run_analytics.py
    ↓
analytics JSON + quality JSON
    ↓  --publish
published_snapshot.py
    ↓
current.json → manifest.json → dashboard / analysis artifacts
```

這兩支程式位於 pipeline 的 analytics 層。它們不負責直接抓取政府 API 或 PDF；輸入是已完成整理、並由 `data/quality/dataset_index.json` 指定的 curated data。

## 二、`run_analytics.py` 的責任

### 2.1 CLI 入口

`main()` 使用 `argparse` 提供以下主要參數：

| 參數 | 用途 |
| --- | --- |
| `--metric` | 指定要執行的分析；可用 `all`、`homepage`、`employment`、`fertility`、`youth_participation`、`policy_support`、`youth_topic_weight`、`youth_keyword_frequency`。 |
| `--output-dir` | 資料根目錄，預設為 `data`。 |
| `--config-dir` | 設定檔目錄，預設為 `config`。 |
| `--annual-start-roc` / `--annual-end-roc` | 年度分析的起訖民國年。 |
| `--population-reference-roc` | 人口參考年度。 |
| `--publish` | 在一般 analytics 輸出完成後，另外發布 snapshot。 |
| `--snapshot-id` | 指定 snapshot 資料夾名稱。未指定時會依生成時間建立 ID。 |

程式會先驗證年度範圍，再讀取 `config/homepage_analytics.json`，將 CLI 的年度參數套用到分析設定，最後建立 `HomepageInputResolver`，供各 analytics generator 讀取資料。

### 2.2 `--metric all` 的完整流程

`_run_all_analytics()` 是完整發布的主要 orchestration。執行順序如下：

1. 產生 homepage analytics。
2. 產生 employment analytics。
3. 產生 fertility analytics。
4. 產生 youth participation analytics。
5. 產生 policy support analytics。
6. 讀取 `join_proposals` 與 `youth_council_minutes`，產生 topic weight。
7. 使用相同兩份資料產生 keyword frequency。
8. 將每個結果的 `_quality` 分離保存，並從公開 payload 移除 `_quality`。
9. 若沒有 `--publish`，流程在一般 analytics 輸出後結束。
10. 若有 `--publish`，將所有結果一次交給 `publish_homepage_snapshot()`。

完整執行會先寫入各自的 analytics 與 quality 檔案：

```text
data/analytics/homepage/all.json
data/analytics/employment/all.json
data/analytics/fertility/all.json
data/analytics/youth_participation/all.json
data/analytics/policy_support/all.json
data/analytics/youth_topic_weight/all.json
data/analytics/youth_keyword_frequency/all.json
```

對應的品質報告位於 `data/quality/analytics_*.json`。這些檔案是 pipeline 內部的計算結果；published snapshot 則是提供下游消費者的公開版本。

### 2.3 資料索引與來源資訊

`_load_indexed_dataset()` 對 `join_proposals` 與 `youth_council_minutes` 使用 authoritative dataset index，不直接掃描 curated 目錄。若 index 缺少資料，程式會停止並提示使用 `run_pipeline.py` 重建該資料集，而不是默默使用未確認的檔案。

發布前，`run_analytics.py` 會載入 `config/sources.json`，將 analytics quality 中的 dataset 名稱轉換成 published manifest 可使用的 source catalog 與 source references。

### 2.4 完整發布指令

從 `data-pipeline` 目錄執行：

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python src/run_analytics.py \
  --metric all \
  --output-dir data \
  --config-dir config \
  --publish \
  --snapshot-id dev-full-20260912
```

這個模式會呼叫 publisher 時設定 `update_current=True`，因此只有完整的 `--metric all --publish` 會更新目前發布版本。

### 2.5 單一 metric 與完整發布的差異

單獨執行某些 metric 並加上 `--publish` 時，程式會建立 candidate snapshot，但使用 `update_current=False`。因此它不會把不完整的分析結果設成目前版本。

例如：

```bash
PYTHONPATH=src .venv/bin/python src/run_analytics.py \
  --metric youth_participation \
  --output-dir data \
  --config-dir config \
  --publish \
  --snapshot-id dev-youth-participation-debug
```

這個 snapshot 可以檢查，但 `data/analytics/published/current.json` 不會因此改指向它。

## 三、`published_snapshot.py` 的責任

### 3.1 對外的主要 API

核心函式是：

```python
publish_homepage_snapshot(
    homepage_payload,
    quality_payload,
    output_dir=output_dir,
    snapshot_id=snapshot_id,
    analyses=analyses,
    analysis_quality=analysis_quality,
    source_catalog=source_catalog,
    source_refs_by_dataset=source_refs_by_dataset,
    update_current=True,
)
```

它會回傳 `PublishedSnapshot`，包含：

- `snapshot_id`
- `snapshot_dir`
- `manifest_path`
- `current_path`

### 3.2 發布前驗證

Publisher 在寫檔前會驗證：

- homepage payload 必須有合法的 `generated_at`。
- `districts` 必須是陣列，且每筆 district 必須有 `district_id` 與 `district_name`。
- snapshot ID 與 analysis name 必須是安全的 path component。
- 每個 analysis 與 quality payload 必須是 mapping。
- public payload 不得包含 `raw_record` 或 `raw_records`。

這些檢查可避免把 raw 內容、任意路徑或不合法的檔名發布給下游服務。

### 3.3 產生的 snapshot 結構

```text
data/analytics/published/
├── current.json
└── <snapshot_id>/
    ├── dashboard_overview.json
    ├── district_details.json
    ├── manifest.json
    └── analyses/
        ├── employment.json
        ├── fertility.json
        ├── participation.json
        ├── policy_support.json
        ├── topic_weight.json
        └── keyword_frequency.json
```

`dashboard_overview.json` 是首頁層級資料，包含 KPI、district 資料、年度資料、政策資料、選舉資料、服務涵蓋率與 availability 狀態。

`district_details.json` 將每個行政區拆成：

```json
{
  "district_id": "65000010",
  "district_name": "板橋區",
  "metrics": {}
}
```

`analyses/*.json` 則保存各個分析模組的公開 payload。

### 3.4 `manifest.json`

Manifest 是 snapshot 的目錄與資料契約，主要包含：

- `schema_version`
- `snapshot_id`
- `generated_at`
- `artifacts`：homepage、district details 與各分析檔案的相對路徑
- `datasets`：每個資料集的 source period、地理層級、coverage 與 quality flags
- `sources`：來源 catalog
- `warnings`

完整發布通常會有一個 homepage 加上六個 analysis datasets。下游不應自行猜檔名或掃描資料夾，而應依照 manifest 的 `artifacts` 讀取檔案。

### 3.5 原子寫入與 `current.json`

實際 JSON 寫入由 [`analytics/io.py`](data-pipeline/src/analytics/io.py) 的 `atomic_json_write()` 完成：先在目標目錄建立 temporary file，寫完後再以 replace 取代正式檔案。

發布順序是：

```text
dashboard_overview.json
        ↓
district_details.json
        ↓
analyses/*.json
        ↓
manifest.json
        ↓
current.json
```

`current.json` 只保存目前 snapshot ID：

```json
{
  "snapshot_id": "dev-full-20260912"
}
```

因此讀取端應採用以下流程：

1. 讀取 `current.json`。
2. 取得 `snapshot_id`。
3. 開啟該 snapshot 的 `manifest.json`。
4. 依 manifest 的相對路徑讀取 `dashboard_overview.json`、`district_details.json` 與 `analyses/*.json`。

如果 snapshot artifacts 或 manifest 寫入失敗，`current.json` 不會被更新，上一個完整版本仍然可用。

## 四、兩支程式的責任分工

| 元件 | 負責 | 不負責 |
| --- | --- | --- |
| `run_analytics.py` | CLI、設定載入、分析執行順序、quality 分離、來源資訊組裝、呼叫 publisher | 抓取政府 API、解析 PDF、提供 Backend HTTP API |
| `published_snapshot.py` | public payload 驗證、首頁與 district artifact 組裝、manifest、原子寫入、current pointer | 計算人口、薪資、就業或青年參與指標 |
| `run_pipeline.py` 與 collectors | 抓取 raw、transform、建立 curated 與 dataset index | 產生完整 published analytics snapshot |
| Backend／Frontend | 讀取 current snapshot 並呈現 | 在 request 時重新執行 ETL 或重算指標 |

## 五、快速判斷資料來源

看到下列檔案時，可以這樣判斷：

- `data/analytics/*/all.json`：單一 analytics generator 的輸出。
- `data/quality/analytics_*.json`：該分析的 quality 與來源期間資訊。
- `data/analytics/published/<snapshot_id>/`：由 `published_snapshot.py` 組裝的公開 snapshot。
- `data/analytics/published/current.json`：目前 active snapshot 的 pointer，不是完整資料本身。

簡單來說，`run_analytics.py` 決定「算哪些資料」，`published_snapshot.py` 決定「怎麼把這些資料包成一個可安全讀取的版本」。
