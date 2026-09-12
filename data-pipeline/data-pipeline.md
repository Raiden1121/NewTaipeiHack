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

### Source provenance

`config/sources.json` 是 source ID、中文名稱與官方查證網址的 versioned registry。新 Raw envelope 會保存 `source`、`source_url` 與 `source_url_type`；既有 Raw 維持 immutable，replay／transform 會以 dataset default 與 registry 補入 curated、published snapshot 與未來 DynamoDB projection。Frontend 不維護來源對照表；無法確認的來源保留 `null` 並寫入 quality warning。

### 青年局預算 PDF

`youth_budgets` 是 `all_available` source strategy：一次抓取官方列表頁上目前可發現的年度文件，輸出固定為 `curated/youth_budgets/all.json`。raw 會保留列表／文件 metadata 與 PDF artifact：

```text
data/raw/youth_budgets/{snapshot}.json
data/raw/youth_budgets/artifacts/{roc_year}_{status}_{sha256_prefix}.pdf
data/curated/youth_budgets/all.json
data/quality/youth_budgets/all.json
data/quarantine/youth_budgets/all.json
```

執行與 replay：

```bash
cd data-pipeline
PYTHONPATH=src python3 src/run_pipeline.py \
  --start-period 11501 --end-period 11601 --output-dir data

PYTHONPATH=src python3 src/run_pipeline.py \
  --dataset youth_budgets \
  --input data/raw/youth_budgets/{snapshot}.json \
  --output-dir data
```

`--input` 只讀 raw JSON、重新執行 transform，不重新呼叫列表頁或下載 PDF。analytics 應讀 `data/quality/dataset_index.json` 指向的 `curated/youth_budgets/all.json`，不可直接 glob curated 目錄；預算資料是 organization-level context，不可當成 29 區預算。

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

## Scheduled Refresh Operations

排程更新使用 `--refresh-profile`。它會讀取 `config/refresh_profiles.json`，依 daily、weekly 或 monthly 的 wall-clock cadence 檢查 `data/quality/refresh_state.json`，只執行已到期的 execution units；同一個 cadence 尚未到期的資料不會呼叫 collector。每次執行會產生對應的 refresh report，並更新 refresh state 與 authoritative `data/quality/dataset_index.json`。

pipeline 預設保留前五個完整年度加上目前年度；例如目前為 `11509` 時，年度資料保留 `110`～`115`，月資料從 `11001` 保留到目前月份。collection 全部成功後，會清除早於保留起點的 local JSON partition，並更新 `data/quality/retention_report.json`。只要有 collection error，就會跳過清理以保護既有資料。可用 `--retention-years N` 覆寫完整歷史年度數；清理規則依 monthly、annual、snapshot、all_available 分別處理，all_available 的未來年度資料不會因為超過目前年度而被誤刪。

以下命令可由本機手動執行，也可交給外部排程器執行：

```bash
# 每日職缺更新
cd data-pipeline
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile daily \
  --output-dir data \
  --strict

# 每週房價、租金與職訓更新
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile weekly \
  --output-dir data \
  --strict

# 每月人口、年度資料檢查、青年預算與 TDX 更新
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile monthly \
  --include-tdx \
  --output-dir data \
  --strict

# 只重跑 daily profile 中上次失敗的指定資料
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --refresh-profile daily \
  --datasets job_vacancies,job_vacancy_salaries \
  --failed-only \
  --output-dir data \
  --strict
```

`--refresh-profile` 是 refresh mode，依 refresh state 的到期判斷執行目前應更新的資料；`--datasets` 可縮小指定 profile 的範圍，`--failed-only` 則只挑選該 profile 上一次狀態為 `error` 的 units。加上 `--force` 會忽略目前 unit 的到期狀態並重新執行。沒有 due unit 時會跳過 retention，不會為了清理而重新掃描全部大型 JSON。`no_data` 不是永久失敗，annual 資料會在下一個 monthly window 重新檢查。

歷史 range mode 仍使用 `--start-period` 與 `--end-period`，依 `PeriodStrategy` 建立歷史月份、年度、snapshot 或 all-available units；它是補齊或重建指定期間，不等同於 daily、weekly、monthly 的 wall-clock refresh mode。歷史 range 也可用 `--datasets` 只選指定資料集；例如只重抓 `college_majors` 的 110～114 五個學年度：

```bash
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --start-period 11001 \
  --end-period 11412 \
  --datasets college_majors \
  --output-dir data \
  --force \
  --strict
```

`10901`～`11412` 是六個學年度（109、110、111、112、113、114），不是五年。`--period`、`--input` 與 `--resume` 仍屬既有的單月或 raw replay／recovery 操作；`--force` 可用於 historical range，也可用於 refresh mode。

refresh CLI 本身不包含定時器。外部 cron、GitHub Actions 或 AWS EventBridge Scheduler 只負責在指定時間呼叫上述同一個 CLI；本次 pipeline 不新增 AWS credentials、Lambda、EventBridge、部署資源或其他 AWS infrastructure。若尚未部署外部 scheduler，可以先在本機手動執行並確認 state、report 與 dataset index，再由部署環境設定實際頻率。

`data/data_description.md` 是資料欄位與輸出說明文件，不是排程的真實來源。profile、資料集清單與 cadence 以 `config/refresh_profiles.json`、orchestration code 與 `data/quality/refresh_state.json` 的執行狀態為準。

首次建立資料時，先用 historical range 抓前五個完整年度與目前年度，例如目前 ROC 月為 `11509` 時使用 `--start-period 11001 --end-period 11509`；之後再使用上述 refresh commands。未來搬到 S3 時只替換 storage operation，retention policy 不變。

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

## Youth Topic Word Cloud Data Flow

青年議題文字雲的數字計算在 Data Pipeline 的 analytics，不在 Frontend 排版，也不在 Backend 臨時計算：

```text
join.gov / data.gov ─┐
                     ├─ collectors → raw → transforms → analytics weight JSON
青年局會議 PDF ──────┘                                      ↓
                                                   Backend API → Frontend SVG
```

新增資料集：

- `join_proposals`：全國提案資料，青年關注由機關／關鍵字 proxy 推定。
- `youth_council_minutes`：新北市青年局會議 PDF，保存 PDF artifact、hash、逐頁文字與提案段落狀態。

兩者都是 `all_available`，curated output 為 `curated/{dataset}/all.json`。analytics 只讀 `quality/dataset_index.json` 列出的 authoritative files，輸出：

```text
data/analytics/youth_topic_weight/all.json
data/quality/analytics_youth_topic_weight.json
```

執行 analytics：

```bash
cd data-pipeline
PYTHONPATH=src python3 src/run_analytics.py \
  --metric youth_topic_weight \
  --output-dir data \
  --config-dir config
```

權重使用 22 個固定議題與同義詞，依年度計算 join 提案支持度、會議項目數、resolved、escalated，再量化為 1–5。會議訊號至少為 3，`escalated` 強制為 5；Frontend 目前只讀 `label` 與 `weight`，不產生 PNG/SVG。

目前另提供不限制 22 個議題的動態關鍵字分析，使用 `jieba`（若未安裝則使用明確標記的 fallback tokenizer）、動態停用詞與青年政策詞典。政策詞典是排序加分來源，不是動態候選詞白名單；候選詞先依至少 2 份文件的出現證據篩選。詞典以外的三字以上複合詞若出現在議題／提案文字，或同時出現在 join 與會議來源且累計達 `min_dynamic_frequency`，也能進入候選；二字詞則需額外具備議題重複證據或跨來源政策錨點。局處、會議程序與一般行政詞會排除；單一會議內重複很多次但沒有議題或跨來源證據的內文詞不會只因頻率高就保留。完整政策複合詞會由 user dictionary 保護，不會因單字停用詞被拆掉。會議詞的 `resolved`／`escalated` 只依 `resolution_text` 中實際命中的詞計算。政策詞、政策錨點與議題文字證據會計入 `policy_relevance`，輸出仍可包含詞典以外的動態詞。輸出為：

```text
data/analytics/youth_keyword_frequency/all.json
data/quality/analytics_youth_keyword_frequency.json
```

執行動態關鍵字 analytics：

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python src/run_analytics.py \
  --metric youth_keyword_frequency \
  --output-dir data \
  --config-dir config
```

動態關鍵字的設定在 `config/youth_keyword_config.json`；`youth_keyword_stopwords.txt` 管理行政／流程用語，`youth_policy_terms.json` 管理政策加分詞與複合詞，`policy_anchors` 管理政策相關性加分的領域詞，`youth_keyword_userdict.txt` 控制中文複合詞切分。`top_n`、`min_document_frequency`、`min_dynamic_frequency` 與 `frequency_weight` 可調整，不會限制只能輸出預先定義的 22 個議題。`raw_score` 會納入對數化的 `term_frequency`，並保留 join、會議、resolved、escalated 等資料訊號；輸出另含 `ranking_score`、`policy_relevance`、`frequency_score` 與 `topic_mentions`，其中 `ranking_score` 用於政策相關性排序與量化 `weight`。
