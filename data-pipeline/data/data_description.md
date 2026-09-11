# Data Pipeline 資料說明

本文件依據 `data/curated/` 內的既有處理結果、2026-09-11 真實資料刷新、官方來源 live check 與 analytics 資料契約撰寫，涵蓋目前已串接的 canonical datasets。`elections`、`youth_service_points`、`population_villages`、`village_boundaries` 與 `youth_budgets` 決算來源均由 pipeline 管理；首頁與青年就業 analytics 分別寫入 `data/analytics/homepage/`、`data/analytics/employment/`，並各自產生品質報告。範例值直接取自 generated JSON 或官方 live response，沒有自行編造或重新計算；未能安全解析的來源會保留 raw artifact 並記錄在 `document_failures`。

> 範例只展示標準化後較重要的欄位。完整來源內容仍保存在各筆資料的 `raw_record`、`raw_records`、`overview_raw_record` 或 `detail_raw_records`，因內容很大，不在本文件重複展開。

## 目前資料完整度

- 2026-09-10 targeted range pipeline（`11509`，指定 `youth_budgets,elections,youth_service_points`）三個 execution units 全部成功：分別為 31、5,577、9 筆 raw → curated，`rows_rejected=0`。
- 2026-09-11 真實資料刷新：年度人口／里級人口、出生、薪資與大專資料共 132 個成功 execution units、3 個官方來源無法取得；snapshot／空間資料 10 個成功、村里界 1,039 筆 curated，另補抓 elections 5,577 筆與 talent demand 117 筆。
- `youth_budgets` 現在會同時讀取預算公告與「統計專區 → 預決算公告」；本次解析 6 份文件、8 份 PDF artifact，另有 111、112 年影像型決算 PDF 解析失敗紀錄，沒有丟棄來源檔。
- `elections` 只收錄中選會 2014／2018／2022 新北市直轄市議員 T1 與村里長 V1：T1 337 筆、V1 5,240 筆；不混入總統、立委或市長資料。
- `youth_service_points` 取得青年局青創基地 9 筆詳細頁；collector 原始頁面中 3 筆地址可由新北市門牌位置資料唯一匹配，另外 6 筆使用版本控管的官方地址參照資料補入地址與座標。transform 後 9 筆均有可驗證的 EPSG:3826 座標，沒有把地址猜測成座標。
- `college_majors` 的 114 學年度年度 canonical 輸出 `data/curated/college_majors/114.json` 為 919 筆、`geo_level=district`，學校所在地可對應 13 個新北市行政區；進行 29 區 analytics 時應使用此年度檔。
- 首頁 analytics 已實際產出：29 區 YOI、ROC 110–114 年人口／生育率／預算序列、2014／2018／2022 選舉事件，以及服務涵蓋率全市 49.2266230851%（`partial`；9 verified、0 excluded；1,039 個里界中 1,032 個接上里級人口）。青年就業 analytics 另產出 29 區資料與兩張各 29 點散點圖；職缺與房價來源期間為 `11509`。
- `babysitting_places` 已加入 collector、transform 與 pipeline registry；2026-09-09 live smoke 取得私托 261 筆、公托 130 筆，共 391 筆，391 筆均通過 transform，來源本身沒有歷史年度參數。
- 2026-09-04 的 TDX 執行成功取得 `bus_stops`、`railway_stops`、`bike_stops`。
- 2026-09-09 的 `11201`～`11601` range 執行結果為 102 組成功、28 組來源無資料、1 組傳輸失敗；唯一失敗的是 `population` 的 `11206`，原因為 HTTP 回應中途截斷 (`IncompleteRead`)。
- `data/quality/collection_range.json` 記錄本次 `11509` range 執行結果；三個新增／擴充 dataset 的 status 都是 `ok`，詳細的 111／112 年決算 PDF 解析失敗則在 raw envelope 的 `document_failures` 保存。
- 資料來源沒有提供的期間不會以 0 補值；缺失欄位一律保留為 JSON `null`。
- 首頁年度指標固定使用 ROC 110–114；ROC 109 只作 ROC 110 的人口 YoY 基準。YOI 使用各資料集最新可得快照，不回填成歷史年度，也不計算 YOI YoY。
- `population_villages` 與 `village_boundaries` 是服務涵蓋率專用輸入；沒有驗證座標的青創基地會保留 raw／curated，但 analytics 會排除並記錄 excluded count，不把它當成 0 覆蓋。

## 共同資料結構

每筆 curated record 都有下列共同 Keys：

| Key | 說明 |
|---|---|
| `dataset` | canonical 資料集名稱 |
| `source` | 資料來源識別名稱 |
| `source_record_id` | 可穩定辨識來源資料的 ID |
| `geo_level` | 地理粒度：`district`、`village`、`county`、`national` 或 `organization` |
| `district_id` | 新北市行政區代碼；無可靠區級資料時為 `null` |
| `district_name` | 新北市行政區名稱；無可靠區級資料時為 `null` |
| `period_start` | 資料代表期間起日 |
| `period_end` | 資料代表期間迄日 |
| `period_type` | `day`、`month`、`year` 或 `snapshot` |
| `metric_id` | 指標名稱；單筆明細型資料可為 `null` |
| `value` | 指標值；單筆明細型資料可為 `null` |
| `unit` | `value` 的單位；單筆明細型資料可為 `null` |
| `age_scope` | 年齡口徑，例如 `derived_18_35`、`exact_18_35`、`all_ages` |
| `age_min` | 年齡下限；沒有精確年齡口徑時為 `null` |
| `age_max` | 年齡上限；沒有精確年齡口徑時為 `null` |
| `youth_eligibility` | `eligible`、`proxy_only` 或 `context_only` |
| `fetched_at` | pipeline 取得資料的時間 |
| `quality_flags` | 該筆資料的品質警告陣列 |

18–35 歲核心分析只能使用 `youth_eligibility=eligible`。`proxy_only` 只能作近似參考，`context_only` 只能作青年生活環境背景。

## JSON 檔案索引與格式

`data/` 下的 JSON 是 pipeline 的執行結果，並非全部都是可以直接給前端使用的資料。相同資料集可能同時有原始快照、標準化資料、分析結果、品質報告與隔離資料；以下列出目前實際使用的邏輯路徑。`raw` 檔名包含抓取時間，因此不逐一列出每個 timestamp 檔案。

| 層級 | 路徑 | 內容與用途 |
|---|---|---|
| Raw | `data/raw/<dataset>/<period>_<timestamp>.json` | collector 保存的來源快照；保留原始欄位與抓取時間，供重跑、稽核與除錯，不是前端資料契約。PDF 原檔另放在 `data/raw/<dataset>/artifacts/`。 |
| Curated | `data/curated/<dataset>.json`、`data/curated/<dataset>/<period>.json`、`latest.json` 或 `all.json` | transform 標準化後的資料，供 analytics 或 backend 讀取。 |
| Analytics | `data/analytics/<metric>/<period>.json` 或 `all.json` | 由 curated 資料計算的指標，例如青年關鍵字與議題權重；不是來源明細。 |
| Quality | `data/quality/<dataset>/<period>.json` 及根目錄報告 | 筆數、錯誤、缺欄位、品質狀態與執行紀錄，不應當成業務資料使用。 |
| Quarantine | `data/quarantine/<dataset>/<period>.json` | 未通過 transform 或欄位驗證的資料，保留原因供人工檢查，不納入 curated。 |

### Curated JSON 的共同外層

大部分 curated 檔案的外層格式如下：

```json
{
  "dataset": "population",
  "generated_at": "...",
  "period": "11507",
  "records": []
}
```

`period` 只在期間型或 all-available 輸出需要時存在；真正的資料列在 `records` 陣列，每列包含前述共同 Keys 與資料集專屬欄位。常見的 curated JSON 邏輯檔案如下：

| 資料集 | 目前 JSON 路徑規則 |
|---|---|
| `population`、`movement` | `data/curated/<dataset>.json`、`data/curated/<dataset>/<yyyMM>.json` |
| `population_villages` | `data/curated/population_villages/<yyyMM>.json` |
| `births`、`marriages`、`wages` | `data/curated/<dataset>/<period>.json` |
| `house_prices`、`rentals` | `data/curated/<dataset>.json`、`data/curated/<dataset>/<period>.json`、`latest.json` |
| `job_vacancies`、`job_vacancy_salaries` | `data/curated/<dataset>.json`、`data/curated/<dataset>/latest.json` |
| `college_majors`、`graduate_majors` | `data/curated/<dataset>/<period>.json` |
| `vt_courses`、`training_numbers` | `data/curated/<dataset>.json`、`data/curated/<dataset>/<period>.json` 或 `latest.json` |
| `talent_demand` | `data/curated/talent_demand.json`、`data/curated/talent_demand/<period>.json`、`all.json` |
| `bus_stops`、`railway_stops`、`bike_stops` | `data/curated/<dataset>.json` |
| `youth_budgets` | `data/curated/youth_budgets/all.json` |
| `babysitting_places` | `data/curated/babysitting_places/latest.json` |
| `elections` | `data/curated/elections/all.json` |
| `youth_service_points` | `data/curated/youth_service_points/latest.json` |
| `village_boundaries` | `data/curated/village_boundaries/latest.json` |
| `homepage` analytics | `data/analytics/homepage/all.json`；品質報告為 `data/quality/analytics_homepage.json` |
| `employment` analytics | `data/analytics/employment/all.json`；品質報告為 `data/quality/analytics_employment.json` |
| `join_proposals` | `data/curated/join_proposals/all.json` |
| `youth_council_minutes` | `data/curated/youth_council_minutes/all.json` |

### 青年文字分析 JSON

目前有兩份 analytics JSON，兩者都由 `run_analytics.py` 讀取 `join_proposals` 與 `youth_council_minutes` 的 curated JSON 產生：

1. `data/analytics/youth_keyword_frequency/all.json`

   外層 Keys：`metric_id`、`calculation_version`、`source_datasets`、`config_version`、`normalization`、`generated_at`、`years`。`years` 的每個元素包含 `year_roc` 與 `keywords`；每個 keyword 包含：

   `term`、`weight`、`signal`、`term_frequency`、`document_count`、`join_mentions`、`minutes_mentions`、`join_support_score`、`frequency_score`、`raw_score`、`ranking_score`、`policy_relevance`、`topic_mentions`、`resolved`、`escalated`。

2. `data/analytics/youth_topic_weight/all.json`

   外層結構相同，但 `years` 的每個元素改為 `year_roc` 與 `topics`；每個 topic 包含 `label`、`weight`、`signal`、`join_mentions`、`minutes_mentions`、`join_support_score`、`raw_score`、`resolved`、`escalated`。這份檔案保留固定 22 個標準議題，供既有前端格式相容使用。

兩份 analytics 都是「年度結果」，不是逐筆提案或逐份會議紀錄。若要追溯原文，應回到 `data/curated/join_proposals/all.json`、`data/curated/youth_council_minutes/all.json`，再視需要查閱 `data/raw/` 的來源快照或 PDF artifact。

### 目前文字雲輸出摘要

以下是目前 `data/analytics/` 內 JSON 的實際快照摘要；完整內容仍以 JSON 為準，pipeline 重新執行後，`generated_at`、詞彙、次數與分數都可能更新。

| 輸出 | calculation version | config version | generated_at | 年度／筆數 |
|---|---:|---:|---|---|
| `youth_keyword_frequency` | 5 | 5 | `2026-09-10T17:55:09Z` | ROC 110～113：各 100 個；ROC 114：19 個 |
| `youth_topic_weight` | 1 | 1 | `2026-09-10T13:31:10Z` | ROC 110、112、114：各 22 個固定議題 |

#### 動態關鍵字各年度前 10 名

這裡的排名依 `ranking_score`，不是單純依 `term_frequency` 或 `raw_score`；完整輸出仍包含 `raw_score`、`ranking_score`、`policy_relevance` 與次數欄位。

| ROC 年度 | 前 10 個詞（依輸出順序） |
|---:|---|
| 110 | 問題、台灣、以及、工作、應該、一個、規定、能夠、生活、或是 |
| 111 | 台灣、問題、工作、勞動、規定、以及、應該、安全、生活、以上 |
| 112 | 合作、心理健康、大家、活動、未來、不同、工作、地方、台灣、是否 |
| 113 | 問題、學習、台灣、安全、勞動、一個、工作、健康、心理健康、這些 |
| 114 | 青年創業、青少年、勞動、青年影視創作、共享工具庫、陪伴支持網絡、高關懷青少年、安全、產業聚落、勞工 |

ROC 114 的前 10 筆實際欄位如下；`weight` 是前端文字大小使用的 1～5 級距，`signal` 表示主要訊號來源：

| 排名 | term | weight | term_frequency | document_count | raw_score | ranking_score | signal |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | 青年創業 | 5 | 4 | 4 | 3.460299 | 4.260299 | minutes |
| 2 | 青少年 | 5 | 12 | 5 | 3.819865 | 4.019865 | minutes |
| 3 | 勞動 | 5 | 32 | 3 | 3.076656 | 3.943322 | minutes |
| 4 | 青年影視創作 | 5 | 3 | 3 | 2.946480 | 3.879813 | minutes |
| 5 | 共享工具庫 | 5 | 3 | 3 | 2.946480 | 3.879813 | minutes |
| 6 | 陪伴支持網絡 | 5 | 4 | 3 | 3.010299 | 3.810299 | minutes |
| 7 | 高關懷青少年 | 5 | 3 | 3 | 2.946480 | 3.746480 | minutes |
| 8 | 安全 | 4 | 14 | 7 | 3.124501 | 3.324501 | minutes |
| 9 | 產業聚落 | 4 | 3 | 2 | 2.496480 | 3.296480 | minutes |
| 10 | 勞工 | 4 | 18 | 3 | 2.918764 | 3.118764 | minutes |

114 年只有 19 個動態候選詞，是因為詞頻、文件數、政策關聯與行政／流程詞排除條件共同篩選後，實際符合條件的詞少於 `top_n=100`；不是資料讀取失敗。

#### 固定議題文字雲的非零結果

`youth_topic_weight` 每年仍輸出完整 22 個標準議題；未列出的議題在該年度為 `raw_score=0`、`join_mentions=0`、`minutes_mentions=0`，通常會保留 `weight=1` 以維持前端格式。

| ROC 年度 | 有訊號的議題（label：weight） |
|---:|---|
| 110 | 社會住宅：5、青年創業：5、公共參與：5、租金補貼：5、心理健康：5、托育支持：5 |
| 112 | 社會住宅：3、青年創業：5、租金補貼：3、心理健康：5、地方創生：4 |
| 114 | 青年創業：5、公共參與：3、心理健康：3、社會安全網：3 |

文字雲的責任分工是：analytics JSON 負責產生詞彙、次數與 `weight`；backend 未來只需讀取並提供 JSON；frontend 再依 `term`／`label` 與 `weight` 進行文字雲排版。`word_cloud` 類套件屬於繪製／排版工具，不會取代本 pipeline 的資料計算。

### Quality JSON

- `data/quality/dataset_index.json`：最近一次成功執行單元的索引；不是所有歷史期間的完整清單。
- `data/quality/collection.json`、`collection_range.json`：單次或區間 pipeline 執行結果。
- `data/quality/<dataset>/<period>.json`：各資料集的筆數、欄位與品質檢查結果。
- `data/quality/analytics_youth_keyword_frequency.json`、`analytics_youth_topic_weight.json`：兩份青年文字分析的輸入筆數、年度數、版本與輸出數量檢查。

## 資料集總覽

| Dataset | 統計內容 | 實際可用期間 | 地理粒度 | 18–35 歲用途 |
|---|---|---|---|---|
| `population` | 總人口與 18–35 歲人口 | 2018-01～2026-07，缺 2024-08 | 新北市 29 區 | 青年人口可直接使用 |
| `movement` | 遷入、遷出與淨遷徙 | 2018-01～2026-07，缺 2024-08 | 新北市 29 區 | 背景指標 |
| `births` | 生母 18–35 歲出生數 | 2019～2025 | 新北市 29 區 | 可直接使用 |
| `marriages` | 全年結婚對數 | 2017 | 新北市 29 區 | 背景指標 |
| `house_prices` | 房屋實價登錄完整交易快照 | 最新完整 CSV snapshot | 新北市 29 區 | 背景指標 |
| `rentals` | 租賃實價登錄完整交易快照 | 最新完整 CSV snapshot | 新北市 27 區／來源缺坪林、平溪 | 背景指標 |
| `job_vacancies` | 台灣就業通職缺 | 2026-09-03 快照 | 區／市 | 背景指標 |
| `job_vacancy_salaries` | 有可解析薪資的職缺 | 2026-09-03 快照 | 區／市 | 背景指標 |
| `wages` | 新北市官方年齡組薪資 | 2019～2024 | 新北市整體 | 年齡組 proxy |
| `college_majors` | 新北市大專校院科系、學生、教師 | 學年度 105～114 | 依學校所在地分至行政區 | 背景指標 |
| `graduate_majors` | 全國科系畢業人數 | 學年度 106～114 | 全國 | 背景指標 |
| `vt_courses` | 公共職訓課程區域數量 | 2026-09-01 取得的快照 | 2 區 | 背景指標 |
| `training_numbers` | 新北市訓練課程、人數與費用 | 2026-08-14～2027-01-16 | 新北市整體 | 背景指標 |
| `talent_demand` | 全國職類人才需求與僱用 | 2013～2025 | 全國 | 背景指標 |
| `youth_budgets` | 青年局年度預算與單位決算 | ROC 112～116 預算；ROC 113 已解析決算，ROC 111／112 決算 PDF 已保存但待 OCR | organization | 背景指標 |
| `elections` | 中選會新北市 T1 議員與 V1 村里長候選人名冊 | 2014、2018、2022 選舉屆次 | T1 選區／V1 行政區 | 青年參選 analytics 原始資料 |
| `youth_service_points` | 青年局青創基地詳細頁與地址 | 2026-03-31 最新頁面快照 | 點位／可對應行政區 | 服務涵蓋 analytics 原始資料 |
| `population_villages` | ODRP014 村里戶數及單一年齡人口的里級彙總 | 依月份 | 新北市村里 | 服務涵蓋青年人口分母 |
| `village_boundaries` | 國土測繪中心村里界 polygon | 最新下載快照 | 新北市村里 | 服務涵蓋面積交集 |
| `bus_stops` | TDX 公車站點與業者 | 2026-09-03 快照 | 新北市 29 區／未對應 | 背景指標 |
| `railway_stops` | 臺鐵、高鐵、捷運及輕軌站點 | 2026-09-03 取得的快照 | 新北市 18 區 | 背景指標 |
| `bike_stops` | YouBike 靜態站點與容量 | 2026-09-04 快照 | 新北市 29 區／未對應 | 背景指標 |
| `babysitting_places` | 私立托嬰機構與公共托育中心名冊 | 最新年度 snapshot | 新北市 29 區／未對應 | 背景指標 |

## 1. `population`：人口資料

### 資料名稱與統計內容

內政部戶政 ODRP014 村里戶數及單一年齡人口。transform 將村里資料彙總成行政區月份，保留全體人口，並加總 18～35 歲男性、女性及總人口。

### 處理後 Keys

共同 Keys，加上：

- `source_record_ids`：被彙總的村里來源 ID。
- `raw_records`：被彙總的原始村里資料。
- `metric_id` 可為 `people_total`、`youth_18_35_male`、`youth_18_35_female`、`youth_18_35_total`。

### 前五筆實際資料

| district_name | period_start | metric_id | value | unit | age_scope | youth_eligibility |
|---|---|---|---:|---|---|---|
| 板橋區 | 2026-07-01 | people_total | 548271 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | youth_18_35_male | 54892 | people | derived_18_35 | eligible |
| 板橋區 | 2026-07-01 | youth_18_35_female | 51581 | people | derived_18_35 | eligible |
| 板橋區 | 2026-07-01 | youth_18_35_total | 106473 | people | derived_18_35 | eligible |
| 三重區 | 2026-07-01 | people_total | 382569 | people | all_ages | context_only |

### 其他說明

- 代表檔：`data/curated/population.json`；歷史檔在 `data/curated/population/{yyyMM}.json`。
- 可用民國年月為 10701～11507，共 102 個月，11308 缺資料；10501～10612 來源查無資料。
- 每月 29 區，最新檔 116 筆，即 29 區 × 4 個指標。

### 1.1 `population_villages`：里級青年人口

這是與 `population` 分開保存的同一 ODRP014 原始資料彙總。既有
`population` 維持 29 區相容輸出；本資料集每個「村里＋月份」輸出一筆，讓
服務涵蓋率可以用穩定的 `village_code` 與里界 polygon join，不需要 analytics
解析 `population.raw_records`。

### 處理後 Keys

除共同 Keys 外，包含 `geo_level=village`、`village_code`、`village_name`、
`people_total`、`youth_18_35_male`、`youth_18_35_female`、
`youth_18_35_total`、`source_period` 與 `raw_records`。任一年齡欄位缺失時，
青年欄位保留 `null`，並在 quality warning 標記
`incomplete_youth_age_fields`，不把缺值當成 0。

### 其他說明

- 輸出路徑：`data/curated/population_villages/{yyyMM}.json`。
- 這個 dataset 只供里級空間 analytics；不要用它取代既有區級 `population`。
- 2026-09-11 刷新後，ROC 110–114 除來源無資料的 11308 外，每月約 1,032 個里級 records；ROC 114 的 12 個月份共 12,384 筆，供本次服務涵蓋率使用。

## 2. `movement`：人口遷徙資料

### 資料名稱與統計內容

內政部戶政 ODRP011 村里遷入遷出資料。transform 彙總至行政區月份，保存遷入、遷出來源／去向、性別、總遷入、總遷出與淨遷徙等 59 個指標。

### 處理後 Keys

共同 Keys，加上 `source_record_ids`、`raw_records`。實際遷徙分類放在 `metric_id`，例如 `in_total_m`、`out_total_f`、`movement_in_total`、`movement_out_total`、`net_movement_total`。

### 前五筆實際資料

| district_name | period_start | metric_id | value | unit | age_scope | youth_eligibility |
|---|---|---|---:|---|---|---|
| 板橋區 | 2026-07-01 | in_foreign_f | 62 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | in_foreign_m | 40 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | in_fu_f | 11 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | in_fu_m | 11 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | in_kh_f | 22 | people | all_ages | context_only |

### 其他說明

- 代表檔：`data/curated/movement.json`；歷史檔在 `data/curated/movement/{yyyMM}.json`。
- 可用民國年月為 10701～11507，共 102 個月，11308 缺資料；10501～10612 來源查無資料。
- 最新月份 1,711 筆，即 29 區 × 59 個指標。
- 原始資料沒有年齡欄位，只能作青年環境背景，不能視為 18–35 歲遷徙。

## 3. `births`：18–35 歲生母出生數

### 資料名稱與統計內容

內政部戶政 ODRP056 出生統計。只加總生母年齡 18～35 歲，並彙總為行政區年度出生數。

### 處理後 Keys

共同 Keys，加上：

- `according`：統計依據，例如「按發生日期分」。
- `raw_records`：該區年度被彙總的來源列。
- `metric_id` 固定為 `births_mother_age_18_35`。

### 前五筆實際資料

| district_name | period_start | metric_id | value | unit | age_min | age_max | youth_eligibility |
|---|---|---|---:|---|---:|---:|---|
| 板橋區 | 2025-01-01 | births_mother_age_18_35 | 1293 | births | 18 | 35 | eligible |
| 三重區 | 2025-01-01 | births_mother_age_18_35 | 921 | births | 18 | 35 | eligible |
| 中和區 | 2025-01-01 | births_mother_age_18_35 | 878 | births | 18 | 35 | eligible |
| 永和區 | 2025-01-01 | births_mother_age_18_35 | 327 | births | 18 | 35 | eligible |
| 新莊區 | 2025-01-01 | births_mother_age_18_35 | 1200 | births | 18 | 35 | eligible |

### 其他說明

- 歷史檔在 `data/curated/births/{ROC-year}.json`。
- 實際可用民國 108～114 年，每年 29 區；105～107 與 115 年來源查無資料。
- 這是精確包含 18 與 35 歲的 `eligible` 核心青年資料。

## 4. `marriages`：結婚對數

### 資料名稱與統計內容

內政部戶政 ODRP003 結婚登記資料。transform 將村里月份加總成行政區年度結婚對數。

### 處理後 Keys

共同 Keys，加上 `raw_records`；`metric_id` 固定為 `marriage_pairs_total`。

### 前五筆實際資料

| district_name | period_start | metric_id | value | unit | age_scope | youth_eligibility |
|---|---|---|---:|---|---|---|
| 板橋區 | 2017-01-01 | marriage_pairs_total | 3495 | pairs | all_ages | context_only |
| 三重區 | 2017-01-01 | marriage_pairs_total | 2455 | pairs | all_ages | context_only |
| 中和區 | 2017-01-01 | marriage_pairs_total | 2544 | pairs | all_ages | context_only |
| 永和區 | 2017-01-01 | marriage_pairs_total | 1286 | pairs | all_ages | context_only |
| 新莊區 | 2017-01-01 | marriage_pairs_total | 2728 | pairs | all_ages | context_only |

### 其他說明

- 實際檔案：`data/curated/marriages/106.json`，共 29 區。
- 目前只有民國 106 年完整；105、107～115 年來源月份不完整或查無資料。
- 沒有配偶年齡欄位，因此不能當成 18–35 歲結婚資料。

## 5. `house_prices`：房屋實價登錄

### 資料名稱與統計內容

新北市不動產實價登錄買賣交易。預設保留來源的所有交易標的與用途，包括房地、土地、車位、建物及其他來源類型；同時保留每筆交易價格、建物面積、每平方公尺與每坪單價，不在 transform 計算中位數或 YoY。若只需要住宅子集，collector 可明確傳入 `residential_only=True`。

### 處理後 Keys

共同 Keys，加上：`total_price`、`total_price_unit`、`building_area`、`building_area_unit`、`price_per_sqm`、`price_per_sqm_unit`、`price_per_ping`、`price_per_ping_unit`、`transaction_type`、`snapshot_fetched_at`、`raw_record`。

### 前五筆實際資料

以下為 2026-09-09 完整 CSV 來源及最新 curated snapshot 的前五筆。

| district_name | period_start | total_price | building_area | price_per_ping | transaction_type |
|---|---|---:|---:|---:|---|
| 林口區 | 2024-01-02 | 38880000 | 264.87 | 485252.87436500005 | 房地(土地+建物) |
| 土城區 | 2024-01-06 | 14800000 | 99.01 | 568515.68116 | 房地(土地+建物)+車位 |
| 新店區 | 2024-01-07 | 30450000 | 149.14 | 774555.342855 | 房地(土地+建物)+車位 |
| 土城區 | 2024-01-08 | 18850000 | 119.8 | 567814.85474 | 房地(土地+建物)+車位 |
| 土城區 | 2024-01-12 | 19320000 | 125.54 | 570466.0943100001 | 房地(土地+建物)+車位 |

### 其他說明

- 實際檔案：`data/curated/house_prices/latest.json`，50,065 筆，涵蓋新北市 29 區。
- `transaction_type`（來源 `rps01`）目前有 5 種：

| transaction_type | 筆數 |
|---|---:|
| 房地(土地+建物) | 21,061 |
| 房地(土地+建物)+車位 | 21,499 |
| 土地 | 5,951 |
| 車位 | 1,455 |
| 建物 | 99 |

- 完整來源包含平溪區與坪林區；平溪區的來源紀錄目前是純土地交易，不代表住宅房屋交易。
- 原始 `rps01`（交易標的）、`rps11`（建物型態）與 `rps12`（用途）會保留在 `raw_record`，不再由 collector 只留下住宅用途。
- 來源單價為 0 或缺失時，`price_per_ping` 保留為 `null`，不以 0 代替。
- 無年齡欄位，只能作青年居住成本背景。

## 6. `rentals`：租賃實價登錄

### 資料名稱與統計內容

新北市租賃實價登錄。預設保留來源的所有租賃交易標的與用途，包括住宅、套房、店舖、辦公、車位及其他來源類型；同時保留單筆租金、面積、每平方公尺／每坪租金與出租型態，不在 transform 計算中位數或 YoY。若只需要住宅子集，collector 可明確傳入 `residential_only=True`。

### 處理後 Keys

共同 Keys，加上：`rent_total`、`rent_total_unit`、`building_area`、`building_area_unit`、`rent_per_sqm`、`rent_per_sqm_unit`、`rent_per_ping`、`rent_per_ping_unit`、`rent_per_sqm_source`、`rental_type`、`snapshot_fetched_at`、`raw_record`。

### 前五筆實際資料

以下為 2026-09-09 完整 CSV 來源及最新 curated snapshot 的前五筆。

| district_name | period_start | rent_total | building_area | rent_per_ping | rental_type |
|---|---|---:|---:|---:|---|
| 五股區 | 2025-04-28 | 16800 | 83.56 | 664.462785 | 獨立套房 |
| 五股區 | 2025-05-03 | 8900 | 30.37 | 968.595005 | 獨立套房 |
| 五股區 | 2025-04-28 | 18000 | 120.4 | 495.86775 | 整戶 |
| 新莊區 | 2025-04-21 | 22000 | 105.17 | 690.909065 | 整戶 |
| 泰山區 | 2025-05-02 | 22200 | 134.5 | 545.454525 | 整戶 |

### 其他說明

- 實際檔案：`data/curated/rentals/latest.json`，44,852 筆，涵蓋 27 區。
- `rental_type`（來源 `rps29`；`整棟(戶)出租` 標準化為 `整戶`）目前有 6 種：

| rental_type | 筆數 |
|---|---:|
| 整戶 | 31,184 |
| 獨立套房 | 6,916 |
| 分租套房 | 3,527 |
| 分租雅房 | 938 |
| 分層出租 | 114 |
| 未知 | 2,173 |

- `未知` 代表來源 `rps29` 為空白或尚未對應的值，原始值仍保留在 `raw_record`。
- 官方租賃來源本身沒有坪林區、平溪區資料；取消住宅篩選也不會產生這兩區的紀錄。
- 原始 `rps01`（交易標的）、`rps11`（建物型態）與 `rps12`（用途）會保留在 `raw_record`，不再由 collector 只留下住宅用途。
- 無年齡欄位，只能作青年租屋環境背景。

## 7. `job_vacancies`：職缺快照

### 資料名稱與統計內容

台灣就業通新北市職缺。保留每筆職缺需求人數、薪資上下限、薪資單位、截止日期及查詢品質標記。

### 處理後 Keys

共同 Keys，加上：`position_count`、`position_count_unit`、`closing_date`、`salary_type`、`salary_lower`、`salary_upper`、`salary_midpoint`、`salary_unit`、`salary_estimate_type`、`snapshot_fetched_at`、`query_truncated`、`county_name`、`raw_record`。

### 前五筆實際資料

| district_name | position_count | salary_type | salary_lower | salary_upper | salary_unit | closing_date |
|---|---:|---|---:|---:|---|---|
| 板橋區 | 5 | 月薪 | 36500 | 38000 | TWD_per_month | null |
| 板橋區 | 10 | 月薪 | 35000 | null | TWD_per_month | null |
| 板橋區 | 10 | 時薪 | 201 | null | null | null |
| 板橋區 | 5 | 月薪 | 30500 | 34000 | TWD_per_month | null |
| 板橋區 | 1 | 月薪 | 33000 | 38000 | TWD_per_month | null |

### 其他說明

- 實際檔案：`data/curated/job_vacancies/latest.json`，3,944 筆；快照日期為 2026-09-11（來源期間 `11509`）。
- 3,900 筆為區級、44 筆無法可靠對應行政區；analytics 只使用 `geo_level=district`。
- 目前 3,944 筆 `closing_date` 全為 `null`，但 raw 有截止日期欄位，屬待修正的 transform 欄位對應問題。
- 職缺的薪資上下限可能只有單邊；單邊薪資不會猜測另一端，只有完整上下限才可使用 `salary_midpoint`。

## 8. `job_vacancy_salaries`：具薪資職缺快照

### 資料名稱與統計內容

從台灣就業通職缺中保留具可解析薪資的職缺，方便分析職缺薪資範圍，但不在 transform 計算統計量。

### 處理後 Keys

Keys 與 `job_vacancies` 相同：共同 Keys，加上 `position_count`、`position_count_unit`、`closing_date`、`salary_type`、`salary_lower`、`salary_upper`、`salary_midpoint`、`salary_unit`、`salary_estimate_type`、`snapshot_fetched_at`、`query_truncated`、`county_name`、`raw_record`。

### 前五筆實際資料

| district_name | position_count | salary_type | salary_lower | salary_upper | salary_unit | closing_date |
|---|---:|---|---:|---:|---|---|
| 板橋區 | 5 | 月薪 | 36500 | 38000 | TWD_per_month | null |
| 板橋區 | 10 | 月薪 | 35000 | null | TWD_per_month | null |
| 板橋區 | 5 | 月薪 | 30500 | 34000 | TWD_per_month | null |
| 板橋區 | 1 | 月薪 | 33000 | 38000 | TWD_per_month | null |
| 板橋區 | 3 | 月薪 | 29500 | null | TWD_per_month | null |

### 其他說明

- 實際檔案：`data/curated/job_vacancy_salaries/latest.json`，3,111 筆；快照日期為 2026-09-11（來源期間 `11509`）。
- 3,104 筆為區級、7 筆無法可靠對應行政區；其中 2,270 筆有完整上下限並可計算 `salary_midpoint`，其餘不猜測缺少的另一端。
- `closing_date` 目前同樣全部為 `null`，需先修正後才能分析職缺有效期限。

## 9. `wages`：新北市年齡組薪資

### 資料名稱與統計內容

官方表 6 的新北市年度薪資資料。保留官方年齡組及統計方式，不將「未滿 25 歲」「25–29 歲」「30–39 歲」拼成虛假的 18–35 歲數值。

### 處理後 Keys

共同 Keys，加上：`county_name`、`official_age_group`、`statistic_method`、`raw_record`。

### 前五筆實際資料

| period_start | county_name | official_age_group | statistic_method | value | unit | youth_eligibility |
|---|---|---|---|---:|---|---|
| 2024-01-01 | 新北市 | 總計 | 平均數 | 71.1 | 萬元 | proxy_only |
| 2024-01-01 | 新北市 | 未滿30歲 | 平均數 | 56.7 | 萬元 | proxy_only |
| 2024-01-01 | 新北市 | 未滿25歲 | 平均數 | 48.3 | 萬元 | proxy_only |
| 2024-01-01 | 新北市 | 25-29歲 | 平均數 | 59.9 | 萬元 | proxy_only |
| 2024-01-01 | 新北市 | 30-39歲 | 平均數 | 69 | 萬元 | proxy_only |

### 其他說明

- 歷史檔在 `data/curated/wages/{ROC-year}.json`。
- 實際可用民國 108～113 年，即 2019～2024；105～107、114、115 年來源無資料。
- 粒度只有新北市整體，不能推估 29 區差異；全部標記為 `proxy_only`。

## 10. `college_majors`：新北市大專校院科系

### 資料名稱與統計內容

教育部資料集 9621 與 9622。以學年度、學校、科系、日／進修、等級與體系配對，保留學生、教師、上學年度畢業生及男女／年級學生明細；另以教育部大專校院名錄的學校代碼、地址與第三級行政區對照，將學校所在地映射至新北市行政區。

### 處理後 Keys

共同 Keys，加上：`county_name`、`academic_year`、`school_code`、`school_name`、`department_code`、`department_name`、`student_count`、`teacher_count`、`previous_graduate_count`、`detail_student_count`、`male_student_count`、`female_student_count`、`detail_counts`、`school_address`、`school_postal_code`、`school_location_district`、`school_location_source`、`school_location_status`、`school_location_raw_record`、`overview_raw_record`、`detail_raw_record`、`detail_raw_records`。

### 前五筆實際資料

| district_name | school_name | department_name | student_count | teacher_count | previous_graduate_count | detail_student_count | male_student_count | female_student_count |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 三峽區 | 國立臺北大學 | 歷史學系 | 28 | 0 | 4 | 28 | 19 | 9 |
| 三峽區 | 國立臺北大學 | 歷史學系 | 182 | 14 | 32 | 182 | 85 | 97 |
| 三峽區 | 國立臺北大學 | 民俗藝術與文化資產研究所 | 40 | 5 | 3 | 40 | 19 | 21 |
| 三峽區 | 國立臺北大學 | 應用外語學系 | 243 | 12 | 51 | 243 | 73 | 170 |
| 三峽區 | 國立臺北大學 | 創新華語文教學學士學位學程 | 35 | 2 | 0 | 35 | 10 | 25 |

### 其他說明

- 歷史檔在 `data/curated/college_majors/{academic-year}.json`。
- 學年度 105～114 可用；115 尚無資料。重新執行 pipeline 後，資料粒度為學校所在地行政區，不是學生戶籍行政區。
- `data/curated/college_majors/114.json` 是 114 學年度的年度 canonical 檔；目前同目錄的 `11412.json` 實際為 `geo_level=county` 且 `district_id=null` 的期間輸出，不作 29 區 analytics 輸入。選取資料時必須依 `geo_level` 與 `district_id` 檢查，而不能只依檔名中的期間。
- `district_id` 與 `district_name` 是正式的行政區欄位；本表的 `district_name` 來自學校地址對照，前五筆的國立臺北大學位於三峽區。
- 學校所在地對照來源為教育部大專校院名錄；`school_code` 以代碼對照，`school_location_status=matched` 才代表成功映射。對不到的學校保留 `district_id=null`，不使用最近行政區猜測。
- `1084`（亞東科技大學）與 `1085`（馬偕醫學大學）使用教育部校碼沿革對應至名錄中的歷史代碼，確保不同學年度仍可映射到校址行政區。
- 學年度 105～112 沒有 detail 資料。114 年 919 筆中，101 筆 overview 無法配到 detail、8 筆 detail 無法配到 overview；分析男女或年級前應檢查 `quality_flags`。

## 11. `graduate_majors`：全國科系畢業人數

### 資料名稱與統計內容

教育部資料集 9620，依學年度、學門分類與科系統計男女及總畢業人數。

### 處理後 Keys

共同 Keys，加上：`academic_year`、`classification_code`、`classification_name`、`department_name`、`graduate_male_count`、`graduate_female_count`、`graduate_count`、`raw_record`。

### 前五筆實際資料

| academic_year | classification_name | department_name | graduate_male_count | graduate_female_count | graduate_count |
|---|---|---|---:|---:|---:|
| 114 | 綜合教育細學類 | 人文社會學院教育經營碩士在職專班 | 1 | 11 | 12 |
| 114 | 綜合教育細學類 | 人文社會學院教育經營碩士班 | 0 | 2 | 2 |
| 114 | 綜合教育細學類 | 文教事業經營研究所 | 2 | 9 | 11 |
| 114 | 綜合教育細學類 | 文教事業經營研究所 | 5 | 13 | 18 |
| 114 | 綜合教育細學類 | 文教事業經營碩士在職學位學程 | 0 | 4 | 4 |

### 其他說明

- 歷史檔在 `data/curated/graduate_majors/{academic-year}.json`。
- 學年度 106～114 可用；105、115 無資料。114 年代表檔共 5,391 筆。
- 來源沒有縣市欄位，因此是全國資料，不能直接代表新北市青年畢業供給。

## 12. `vt_courses`：公共職業訓練課程數

### 資料名稱與統計內容

勞動部公共職訓課程。transform 依行政區去重課程 ID，產生各區不重複課程數。

### 處理後 Keys

共同 Keys，加上：`course_ids`、`raw_records`；`metric_id` 固定為 `distinct_course_count`。

### 實際資料

此資料處理後只有 2 筆，因此列出全部資料：

| district_name | metric_id | value | unit | course_ids（前 3 個） |
|---|---|---:|---|---|
| 五股區 | distinct_course_count | 32 | courses | 156211, 156212, 156243 ...(+29) |
| 泰山區 | distinct_course_count | 42 | courses | 156309, 156311, 156357 ...(+39) |

### 其他說明

- 實際檔案：`data/curated/vt_courses.json`；2026-09-01 取得 74 筆 raw，彙總成五股、泰山 2 筆。
- raw 有「訓練期間」，但目前 curated 的 `period_start`、`period_end`、`period_type` 都是 `null`，屬待補的期間標準化問題。

## 13. `training_numbers`：訓練課程、人數與費用

### 資料名稱與統計內容

勞動部新北市訓練課程資料，保留課程代碼、名稱、訓練期間、時數、訓練人數與每人費用。

### 處理後 Keys

共同 Keys，加上：`county_name`、`course_code`、`course_name`、`training_hours`、`training_hours_unit`、`training_people`、`training_people_unit`、`fee_per_person`、`fee_per_person_unit`、`raw_record`。

### 前五筆實際資料

| county_name | period_start | period_end | course_code | course_name | training_hours | training_people | fee_per_person |
|---|---|---|---|---|---:|---:|---:|
| 新北市 | 2026-08-23 | 2026-10-18 | 172991 | 新多益聽力與閱讀能力培訓班 | 47 | 22 | 9180 |
| 新北市 | 2026-08-25 | 2026-10-13 | 173075 | 貴金屬成型銼焊與精緻飾品設計實務班 | 54 | 25 | 11800 |
| 新北市 | 2026-08-30 | 2026-11-08 | 173092 | 永生花藝與香氛石文創商品設計實務班 | 54 | 20 | 10000 |
| 新北市 | 2026-08-23 | 2026-11-29 | 173309 | 沙龍凝膠彩繪美甲設計班 | 77 | 25 | 17800 |
| 新北市 | 2026-09-03 | 2026-09-29 | 172979 | 甲種職業安全衛生業務主管教育訓練班 | 42 | 16 | 8000 |

### 其他說明

- 實際檔案：`data/curated/training_numbers.json`，87 筆。
- 課程期間涵蓋 2026-08-14～2027-01-16。
- 只有新北市 county 粒度，沒有可靠行政區，也沒有年齡欄位。

## 14. `talent_demand`：人才需求與僱用

### 資料名稱與統計內容

勞動部全國職類人才需求資料，按年度及職類保存新增需求、新僱用及有效僱用人次。

### 處理後 Keys

共同 Keys，加上：`occupation`、`new_demand_count`、`new_hired_count`、`valid_hired_count`、`count_unit`、`raw_record`。

### 前五筆實際資料

| period_start | occupation | new_demand_count | new_hired_count | valid_hired_count | count_unit |
|---|---|---:|---:|---:|---|
| 2013-01-01 | 民意代表、主管及經理人員 | 14989 | 2457 | 7243 | person_times |
| 2013-01-01 | 專業人員 | 118899 | 20222 | 58297 | person_times |
| 2013-01-01 | 技術員及助理專業人員 | 367366 | 90907 | 219061 | person_times |
| 2013-01-01 | 事務支援人員 | 100277 | 25018 | 56095 | person_times |
| 2013-01-01 | 服務及銷售工作人員 | 273045 | 59743 | 170511 | person_times |

### 其他說明

- 實際檔案：`data/curated/talent_demand.json`，117 筆，涵蓋 2013～2025。
- 來源是全國資料，不是新北市或 29 區資料，也沒有年齡欄位。

## 15. `bus_stops`：TDX 公車站點

### 資料名稱與統計內容

TDX 新北市公車站點，合併 Stop 與 StopOfRoute 的營運業者，並用座標對應新北市行政區。

### 處理後 Keys

共同 Keys，加上：`station_id`、`source_station_id`、`name_zh`、`name_en`、`latitude`、`longitude`、`operators`、`raw_record`。

### 前五筆實際資料

| station_id | name_zh | district_name | latitude | longitude | operators |
|---|---|---|---:|---:|---|
| NWT10353 | 管理中心 | 新莊區 | 25.063771 | 121.457635 | 三重客運 |
| NWT10354 | 標準廠房 | 新莊區 | 25.06504 | 121.456024 | 三重客運 |
| NWT10355 | 五權三五工路口 | 五股區 | 25.065315 | 121.453673 | 三重客運 |
| NWT10356 | 勞工活動中心 | 新莊區 | 25.06236578 | 121.450092 | 三重客運 |
| NWT10357 | 工商展覽中心 | 五股區 | 25.065092 | 121.449031 | 三重客運 |

### 其他說明

- 實際檔案：`data/curated/bus_stops.json`，32,994 筆；快照日期 2026-09-03。
- 28,845 筆可映射到 29 區，4,149 筆座標無法可靠映射，保留 `district_id=null`，不以最近行政區猜測。
- 無年齡欄位，只能作交通可及性背景資料。

## 16. `railway_stops`：TDX 軌道站點

### 資料名稱與統計內容

TDX 臺鐵、高鐵、捷運與新北輕軌站點，保留軌道系統、運具類型及所屬路線，並以座標對應行政區。

### 處理後 Keys

共同 Keys，加上：`station_id`、`source_station_id`、`name_zh`、`name_en`、`latitude`、`longitude`、`rail_system`、`transport_type`、`line_ids`、`line_nos`、`raw_record`。

### 前五筆實際資料

| station_id | name_zh | district_name | latitude | longitude | rail_system | line_ids |
|---|---|---|---:|---:|---|---|
| TRA-0950 | 五堵 | 汐止區 | 25.07799 | 121.66758 | TRA | WL |
| TRA-0960 | 汐止 | 汐止區 | 25.0679 | 121.66113 | TRA | WL |
| TRA-0970 | 汐科 | 汐止區 | 25.06406 | 121.65233 | TRA | WL |
| TRA-1020 | 板橋 | 板橋區 | 25.01434 | 121.46377 | TRA | WL |
| TRA-1030 | 浮洲 | 板橋區 | 25.00419 | 121.44477 | TRA | WL |

### 其他說明

- 實際檔案：`data/curated/railway_stops.json`，104 筆，全部成功映射，分布於 18 個行政區。
- 本次取得時間為 2026-09-03；個別來源列的更新日期介於 2023-08-03～2026-09-03。
- 無年齡欄位，只能作交通環境背景。

## 17. `bike_stops`：TDX YouBike 站點

### 資料名稱與統計內容

TDX 新北市 YouBike 靜態站點，保留站點名稱、座標與容量。collector 可選擇合併即時可借／可還數量，但本次執行只抓靜態站點。

### 處理後 Keys

共同 Keys，加上：`station_id`、`source_station_id`、`name_zh`、`name_en`、`latitude`、`longitude`、`capacity`、`availability`、`available_rent_bikes`、`available_return_bikes`、`static_data`、`raw_record`。

### 前五筆實際資料

| station_id | name_zh | district_name | latitude | longitude | capacity | available_rent_bikes | available_return_bikes |
|---|---|---|---:|---:|---:|---|---|
| NWT500201001 | YouBike2.0_下庄市場 | 八里區 | 25.14678 | 121.3999 | 20 | null | null |
| NWT500201002 | YouBike2.0_八里行政中心 | 八里區 | 25.15397 | 121.40721 | 20 | null | null |
| NWT500201003 | YouBike2.0_八里中庄市場綜合大樓 | 八里區 | 25.15993 | 121.41407 | 28 | null | null |
| NWT500201004 | YouBike2.0_大崁國小 | 八里區 | 25.16064 | 121.41938 | 20 | null | null |
| NWT500201006 | YouBike2.0_龍形停車場 | 八里區 | 25.13041 | 121.4513 | 40 | null | null |

### 其他說明

- 實際檔案：`data/curated/bike_stops.json`，1,600 筆；快照日期為 2026-09-04。
- 1,595 筆可映射到 29 區，5 筆座標無法可靠映射並保留 `district_id=null`。
- 本次未啟用 `include_availability=True`，因此 `availability`、`available_rent_bikes`、`available_return_bikes` 為 `null`；這不是即時可借／可還資料。

## 18. `youth_budgets`：青年局年度預算

### 資料名稱與統計內容

資料來自新北市政府青年局兩個官方公告列表：預算公告與「統計專區 → 預決算公告」。collector 動態追蹤詳情 URL、保存 PDF artifact，預算版抽取「計畫及預算統計表」，決算版抽取「歲出機關別決算表」。2026-09-10 live output 為 31 筆 raw／31 筆 curated；成功解析 6 份文件、保存 8 份 PDF，quality 為 `rows_rejected=0`。

| budget_year_roc | document_status | document_status_label | published_date | updated_date | source_page_number | row_count |
|---|---|---|---|---|---:|---:|
| 116 | `proposed_budget` | 預算案 | 115-09-01 | 115-09-01 | 28 | 4 |
| 115 | `legal_budget` | 法定版 | 114-09-30 | 115-02-09 | 28 | 4 |
| 114 | `legal_budget` | 法定版 | 113-08-29 | 114-02-10 | 26 | 4 |
| 113 | `legal_budget` | 法定預算 | 113-01-29 | 113-01-29 | 27 | 4 |
| 112 | `legal_budget` | 法定預算 | 113-10-11 | 113-10-11 | 25 | 4 |
| 113 | `final_settlement` | 單位決算 | 114-08-01 | 114-08-01 | 13 | 11 |

111、112 年決算公告 PDF 也已下載並保存，但兩份是影像型表格，現有 `pypdf` 文字層不足以安全辨識數值，因此 raw envelope 的 `document_failures` 分別記錄 `target settlement table was not found in PDF`；不可把這兩份視為已完成的 curated 決算資料。

### 實際 curated rows

| budget_year_roc | document_status | row_type | business_plan | value | budget_ratio_percent | period_start |
|---|---|---|---|---:|---:|---|
| 116 | proposed_budget | total | 新北市政府青年局合計 | 220101 | 100.00 | 2027-01-01 |
| 116 | proposed_budget | detail | 一般行政 | 60280 | 27.39 | 2027-01-01 |
| 116 | proposed_budget | detail | 青年發展業務 | 159521 | 72.47 | 2027-01-01 |
| 116 | proposed_budget | detail | 第一預備金 | 300 | 0.14 | 2027-01-01 |
| 115 | legal_budget | total | 新北市政府青年局合計 | 213022 | 100.00 | 2026-01-01 |
| 115 | legal_budget | detail | 一般行政 | 56819 | 26.67 | 2026-01-01 |
| 115 | legal_budget | detail | 青年發展業務 | 155903 | 73.19 | 2026-01-01 |
| 115 | legal_budget | detail | 第一預備金 | 300 | 0.14 | 2026-01-01 |
| 114 | legal_budget | total | 新北市政府青年局合計 | 196153 | 100.00 | 2025-01-01 |
| 114 | legal_budget | detail | 一般行政 | 52645 | 26.84 | 2025-01-01 |
| 114 | legal_budget | detail | 青年發展業務 | 143208 | 73.01 | 2025-01-01 |
| 114 | legal_budget | detail | 第一預備金 | 300 | 0.15 | 2025-01-01 |
| 113 | legal_budget | total | 新北市政府青年局合計 | 158650 | 100.00 | 2024-01-01 |
| 113 | legal_budget | detail | 一般行政 | 51228 | 32.29 | 2024-01-01 |
| 113 | legal_budget | detail | 青年發展業務 | 107122 | 67.52 | 2024-01-01 |
| 113 | legal_budget | detail | 第一預備金 | 300 | 0.19 | 2024-01-01 |
| 112 | legal_budget | total | 新北市政府青年局合計 | 149029 | 100.00 | 2023-01-01 |
| 112 | legal_budget | detail | 一般行政 | 51291 | 34.42 | 2023-01-01 |
| 112 | legal_budget | detail | 青年發展業務 | 97438 | 65.38 | 2023-01-01 |
| 112 | legal_budget | detail | 第一預備金 | 300 | 0.20 | 2023-01-01 |
| 113 | final_settlement | total | 合計 | 151676193 | null | 2024-01-01 |
| 113 | final_settlement | detail | 新北市政府青年局主管 | 148567285 | null | 2024-01-01 |

### 其他說明

- curated output：`curated/youth_budgets/all.json`；raw envelope 的成功 `documents` 有 6 筆、`source_artifacts` 有 8 筆（含 111／112 影像型決算 PDF），PDF 存在 `raw/youth_budgets/artifacts/`。
- 預算列的 `value` 單位為 `TWD_thousand`，保留來源千元，不換算成元；決算列的 `value` 是 `settlement_amount`，單位為 `TWD`。
- 決算 raw／curated 保留 `budget_amount`、`original_budget_amount`、`budget_adjustment_amount`、`realized_amount`、`payable_amount`、`reserved_amount`、`settlement_amount`、`surplus_amount` 與來源 `source_execution_ratio_percent`。執行率不在 collector／transform 計算，analytics 才能依定義計算。
- 所有 curated rows 的 `geo_level` 是 `organization`，`district_id` 與 `district_name` 是 JSON `null`，`youth_eligibility` 是 `context_only`；不可拆配到新北市 29 區，也不是精確 18–35 歲指標。
- 首頁年度範圍雖固定為 ROC 110–114，但目前官方預算 curated 只提供 ROC 112–114 法定預算；ROC 110／111 在 `budgetTrend` 保留為 `unavailable`，不以 112 年以前的資料補值。ROC 113 可依單位換算後計算執行率，其他年度若沒有可解析 `realized_amount` 則保留 `execution_rate=null`。
- 實際輸出：`data/curated/youth_budgets/all.json`、`data/quality/youth_budgets/all.json`、`data/raw/youth_budgets/11509_20260910T192425616501Z.json`；PDF 位於 `data/raw/youth_budgets/artifacts/`。
- 預算來源列表：<https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?module=youth0008&id=108>；決算來源列表：<https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?module=youth0008&id=109>。列表頁目前可發現的文件不代表歷史年度完整性；若要追蹤新版本，應重新執行 collector 並保留新的 raw snapshot 與 PDF hash。

## 19. `elections`：中選會新北市 T1／V1 候選人

### 資料名稱與統計內容

collector 下載中選會官方 <https://data.cec.gov.tw/選舉資料庫/votedata.zip>，從 ZIP 只選取 2014、2018、2022 三屆的新北市代碼 `65`，以及直轄市區域議員 `T1`、村里長 `V1` 候選人檔與選區／村里名稱檔。沒有把總統、立法委員或市長資料混入本資料集。

2026-09-10 live output：5,577 筆，2014／2018／2022 分別為 1,819／1,956／1,802 筆；T1 為 337 筆、V1 為 5,240 筆，`data/quality/elections/all.json` 的 `rows_rejected=0`、`unmapped_district_count=0`。

### 地理與年齡契約

| Field | Contract |
|---|---|
| `source_code` | `T1`（直轄市區域議員）或 `V1`（村里長） |
| `election_term` | `2014`、`2018`、`2022`；`period_type=snapshot` |
| `birth_date_roc`, `birth_year_roc`, `birth_date`, `source_age` | 出生日期／年次與中選會原始年齡並存；不在 collector 推導青年資格 |
| T1 geography | 保留 `election_district_code`／`election_district_name`，`district_id=null`；不把跨行政區選區硬套單一 29 區 |
| V1 geography | 以來源 `district_name` 精確對應 29 區，另保留 `village_code`／`village_name` |
| raw provenance | `source_zip_sha256`、`source_zip_member`、`raw_fields`／`raw_record` |

候選人、政黨、性別、現任／當選標記、教育、出生地與選區代碼等原始欄位都保留。`age_scope=all_ages`、`youth_eligibility=context_only`；18–35 歲篩選、候選人率與分區 analytics 留在後續 analytics，不在 collector／transform 計算。

### 實際欄位範例

| election_term | source_code | candidate_name | birth_date_roc | source_age | election_district_code | district_id |
|---:|---|---|---|---:|---|---|
| 2022 | T1 | 鄭宇恩 | 0750407 | 36 | 01 | `null` |
| 2022 | V1 | 黃承亮 | 0430101 | 68 | 00／留侯里 | 65000010（板橋區） |

### 實際輸出

- curated：`data/curated/elections/all.json`；raw：`data/raw/elections/11509_20260910T192456277782Z.json`。
- 中選會 ZIP artifact：`data/raw/elections/artifacts/`；quality：`data/quality/elections/all.json`；本次 `failures=[]`。
- 此資料集採 `all_available`；retention 會保留帶有 `election_term` 的歷屆選舉 records，不因 snapshot 日期超過五年而刪除 2014／2018。

## 20. `youth_service_points`：青年局青創基地

### 資料名稱與統計內容

collector 讀取青年局「找基地」列表 <https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?module=youth0001&id=145>，逐頁擷取 9 個青創基地詳細頁。每列固定 `point_type=startup_base`，保存名稱、地址、區名、電話、Email、公告／更新日期、詳細頁 URL、完整 `content_text` 與 HTML artifact。

2026-09-11 live output：9 筆 raw／9 筆 curated，`data/quality/youth_service_points/latest.json` 的 `rows_rejected=0`。collector 原始 envelope 的 `matched_count=3` 代表頁面地址直接匹配成功 3 筆；另外 6 筆由固定參照檔 `config/reference/youth_service_points_locations.json` 補入官方公告地址與官方門牌位置資料座標。transform 後 9 筆均為 `geocode_status=matched`。

座標 lookup 來源為新北市政府「新北市門牌位置數值資料」：
`https://data.ntpc.gov.tw/api/datasets/d7b568ab-3819-40c8-a6e7-a6b199443101/csv/zip`。

### 地理與服務範圍契約

| Field | Contract |
|---|---|
| `point_type` | 固定 `startup_base` |
| `address`, `source_district_name` | 先保留來源文字；缺值為 JSON `null` |
| `latitude`, `longitude` | 官方新北門牌座標唯一匹配後轉成 WGS84；無法驗證時為 `null` |
| `x_3826`, `y_3826` | 官方門牌資料的 TWD97 / TM2 121 分帶座標；空間計算優先使用這兩欄 |
| `geocode_status` | `matched` 或 `excluded_no_verified_coordinate`；舊快照尚未重抓時可能為 `not_attempted` |
| `geocode_provider`, `geocode_crs`, `geocode_source_period`, `geocode_source_url` | 座標來源與來源快照 provenance |
| `location_source_type`, `location_source_url`, `location_verified_at` | 固定地址參照的來源類型、官方公告來源與驗證日期；沒有參照合併時為 `null` |
| `geocode_query`, `address_alternatives` | 固定參照使用的門牌查詢字串與官方公告的其他地址寫法 |
| `detail_url`, `source_html_sha256`, `artifact_filename`, `content_text` | 原始頁面 provenance |

collector 對頁面已有地址做官方門牌資料的「唯一、精確」匹配；不以最近點或猜測地址補座標。對固定且不常變動的 6 筆地址，transform 另依 `point_id` 讀取 `config/reference/youth_service_points_locations.json`，合併官方公告地址與官方門牌座標；不覆寫 raw。analytics 只選 `geocode_status=matched` 的點做 2.5 km buffer；若未來仍有無法驗證的點，會保留但在服務涵蓋率的 `excluded_point_count` 與 quality 報告中列出，不當成 0 km 覆蓋。

### 實際欄位範例

| name | point_type | address | district_name | latitude | geocode_status |
|---|---|---|---|---:|---|
| 新北創力坊 | `startup_base` | 新北市三重區重新路一段108號3樓 | 三重區 | 25.063165 | `matched` |
| 新北青創土城綠創基地 | `startup_base` | 新北市土城區莊園街151號2樓 | 土城區 | 24.981714 | `matched` |

### 實際輸出

- curated：`data/curated/youth_service_points/latest.json`；raw：`data/raw/youth_service_points/11509_20260911T030212277094Z.json`。
- 固定地址參照：`config/reference/youth_service_points_locations.json`；HTML 與門牌 ZIP artifacts：`data/raw/youth_service_points/artifacts/`；quality：`data/quality/youth_service_points/latest.json`；本次 `document_failures=[]`，collector `matched_count=3`，curated `geocode_status=matched` 為 9 筆。

## 20.1 `village_boundaries`：官方村里界

collector 下載國土測繪中心的「村(里)界(TWD97_121分帶)」ZIP，保存 ZIP
artifact、SHA-256、來源 URL 與 SHP member metadata；transform 僅保留新北市
代碼 `65`，並以 `village_code`、`district_id` 作為穩定 join key。

來源 URL：`https://maps.nlsc.gov.tw/download/村(里)界(TWD97_121分帶).zip`。

### 處理後 Keys

- `village_code`、`village_name`、`district_id`、`district_name`。
- `geometry`：GeoJSON Polygon／MultiPolygon；`geometry_crs=EPSG:3826`。
- `raw_properties`：來源 SHP 屬性；未知行政區、重複里代碼與無效 geometry 進 quarantine。

2026-09-11 live output 為 1,039 個新北市村里 polygon；輸出為
`data/curated/village_boundaries/latest.json`，供
`service_coverage` 在 EPSG:3826 等面積座標系計算 buffer 與里界交集；不以
centroid 或單一經緯度取代 polygon。

## 21. `babysitting_places`：私托與公托名冊

### 資料名稱與統計內容

資料來自新北市政府資料開放平台的「新北市私立托嬰機構名冊」與「新北市公共托育中心名冊」。兩個來源都標示為每年更新；collector 每次執行都抓取兩個 JSON endpoint，使用 `page`／`size` 分頁取得完整名冊，再合併為同一個 canonical dataset，並以 `care_type` 區分 `private` 與 `public`。未帶分頁參數的 endpoint 只提供 30 筆預覽，不能直接當成完整資料。

### 處理後 Keys

共同 Keys，加上：

- `care_type`：`private` 或 `public`。
- `facility_name`：私托使用來源 `title`，公托使用來源 `name`。
- `operator_name`：公托使用來源 `unit`；私托沒有此欄位時為 `null`。
- `county_name`、`county_code`：來源縣市欄位。
- `source_district_name`、`source_district_code`：來源 `area`／`town` 與 `areacode`。
- `address`、`phone`：來源地址與聯絡電話。
- `capacity`：私托來源 `person` 解析後的可收托人數；公托來源沒有此欄位時為 `null`。
- `capacity_unit`：有 `capacity` 時為 `child_slots`，缺失時為 `null`。
- `source_dataset_id`、`source_row_id`：來源資料集與來源序號。
- `raw_record`：未覆寫的來源列與 collector 加入的來源類型標記。

### 前五筆實際資料

| care_type | facility_name | district_name | address | phone | capacity | capacity_unit |
|---|---|---|---|---|---:|---|
| private | 茵幼爾股份有限公司附設新北市私立寶貝媽咪托嬰中心 | 板橋區 | 莊敬路46號2樓 | (02)82529955 | 90 | child_slots |
| private | 新北市私立卡爾威特托嬰中心 | 板橋區 | 板新路101號1樓、107號2樓 | (02)89518905 | 140 | child_slots |
| private | 新北市私立捧馨園托嬰中心 | 板橋區 | 四川路1段151號 | (02)29563008 | 25 | child_slots |
| private | 新北市私立喜閱寶寶托嬰中心 | 板橋區 | 廣和街61號1.2樓 | (02)89516588 | 30 | child_slots |
| private | 新北市私立卡爾威特托嬰中心亞東園 | 板橋區 | 南雅南路2段144巷66號 | (02)89664098 | 32 | child_slots |

### 其他說明

- 實際檔案：`data/curated/babysitting_places/latest.json`，391 筆；私托 261 筆、公托 130 筆；快照日期為 2026-09-09。
- 來源 API：私托 <https://data.ntpc.gov.tw/api/datasets/69cecdb0-7796-48df-84e5-99e4f1274245/json>；公托 <https://data.ntpc.gov.tw/api/datasets/b3faf2aa-e96b-4f2f-b647-da47dc094860/json>。
- 完整查詢使用 `?page=0&size=1000`，collector 會持續分頁直到取得完整名冊。
- 官方資料頁：<https://data.ntpc.gov.tw/datasets/69cecdb0-7796-48df-84e5-99e4f1274245>、<https://data.ntpc.gov.tw/datasets/b3faf2aa-e96b-4f2f-b647-da47dc094860>。
- 此資料集是 `snapshot` source strategy，不把目前名冊複製成過去年度。輸出位置為 `data/raw/babysitting_places/`、`data/curated/babysitting_places/latest.json`、`data/quality/babysitting_places/latest.json` 與 `data/quarantine/babysitting_places/latest.json`。
- 執行命令：`PYTHONPATH=src .venv/bin/python src/run_pipeline.py --refresh-profile monthly --datasets babysitting_places --output-dir data`。此命令只更新 `babysitting_places`。
- `areacode` 優先用來對應 `config/districts.json`；無法可靠對應時保留 `district_id=null`，不使用最近行政區猜測。
- `capacity` 只代表來源列提供的私托可收托人數；公托沒有此欄位時保留為 `null`，不補成 0。
- 資料沒有年齡欄位，因此 `age_scope=not_age_specific`、`youth_eligibility=context_only`，只能作托育資源背景，不是 18–35 歲核心指標。
- 公托與私托的定義、欄位與更新內容由來源機關維護；兩者可以分別統計，也可以用 `care_type` 做資源比較。
- 若需行政區托育據點數、私托容量總和或人均資源，應在 `analytics/` 依可靠 `district_id` 計算；collector 與 transform 只保存單一機構資料。

## 22. `join_proposals`：公共政策提案

來源為 data.gov.tw 公共政策網路參與平臺「提點子」，必要時退回 join.gov.tw 列表／detail。此來源沒有提案人年齡與新北行政區，因此 curated 使用 `geo_level=national`、`district_id=null`、`age_scope=not_age_specific`、`youth_eligibility=context_only`。`youth_topic_proxy` 只代表命中青年相關機關或關鍵字，不是 18–35 歲身分證明。

主要欄位：`proposal_id`、`proposal_url`、`title`、`content`、`endorsement_count`、`submitted_at`、`year_roc`、`status`、`agency`、`category`、`proxy_reasons`、`raw_record`。附議跨年仍依 `submitted_at` 的 ROC 年度分箱。all-available 輸出為 `data/curated/join_proposals/all.json`；尚未執行 live collector 前，不在本文件填入 mutable row count。

## 23. `youth_council_minutes`：青年局會議紀錄

來源為新北市青年局公開會議紀錄 PDF。collector 保存 `data/raw/youth_council_minutes/artifacts/` 下的原始 PDF、SHA-256 與逐頁文字；transform 再拆出提案項目。curated 使用 `geo_level=organization`、`organization_name=新北市青年局`，以會議日期的 ROC 年度分箱。

主要欄位：`meeting_id`、`meeting_name`、`meeting_date`、`term`、`item_no`、`source_page_start`、`source_page_end`、`topic_text`、`discussion_text`、`resolution_text`、`source_text`、`discussed`、`resolved`、`escalated`、`parse_status`、`manual_review_required`、`source_pdf_sha256`、`raw_record`。`topic_text` 保存提案／議題標題，供關鍵字 analytics 提高政策議題辨識度；`discussion_text` 與 `resolution_text` 保留分段文字。PDF 版面無法辨識決議段落時，保留 partial record 並標記人工檢查，不補推 `resolved=true`。all-available 輸出為 `data/curated/youth_council_minutes/all.json`。

## 24. `youth_topic_weight` analytics

analytics 只讀 `data/quality/dataset_index.json` 指向的兩份 curated all-available 檔案，使用 `config/youth_topic_rules.json` 與 `config/youth_topic_weights.json`。輸出為 `data/analytics/youth_topic_weight/all.json`，每個可用 `year_roc` 固定輸出 22 個 topic：`label`、`weight`、`signal`、`join_mentions`、`minutes_mentions`、`resolved`、`escalated` 與計算追蹤欄位。`weight` 範圍固定 1–5；會議訊號至少為 3，`escalated` 為 5。Frontend 只負責依 weight 排版文字雲。

## 25. `youth_keyword_frequency` analytics

此 analytics 從青年 proxy 提案與青年局會議提案文字動態抽取關鍵字，不限制於 22 個固定議題。設定檔為 `config/youth_keyword_config.json`，目前使用 `jieba`、keyword user dictionary、政策加分詞典、政策領域錨點與行政／流程停用詞。政策詞不是候選白名單；詞先依 `min_document_frequency` 篩選，詞典以外的三字以上複合詞若出現在議題／提案文字，或同時出現在 join 與會議來源且達 `min_dynamic_frequency`，也可進入正式候選；二字詞則需額外具備議題重複證據或跨來源政策錨點。局處、會議程序與一般行政詞會排除。會議詞的 `resolved`／`escalated` 只在該詞實際出現在 `resolution_text` 時成立。`raw_score` 納入對數化的 `term_frequency`，避免長文件單純重複造成過度放大。輸出為 `data/analytics/youth_keyword_frequency/all.json`，每年最多輸出 `top_n` 個 keyword，包含 `term`、`term_frequency`、`document_count`、`join_mentions`、`minutes_mentions`、`frequency_score`、`raw_score`、`ranking_score`、`policy_relevance`、`topic_mentions`、`weight`、`resolved` 與 `escalated`。

## 26. `homepage` analytics

執行 `run_analytics.py --metric homepage` 會讀取 curated dataset，不讀 raw
artifact，也不在 request time 重新抓資料。輸出：

- `data/analytics/homepage/all.json`：首頁可讀的年度指標、最新快照 YOI、選舉事件與服務涵蓋率。
- `data/quality/analytics_homepage.json`：實際輸入期間、筆數、proxy／imputation、排除數與阻塞原因。

時間口徑固定如下：

- 年度人口、生育率與預算趨勢：ROC 110–114；ROC 109 只作 ROC 110 YoY 基準。
- YOI：每個資料集的最新可得 snapshot，人口錨點使用 ROC 114；不產生 YOI YoY。
- 選舉：2014／ROC 103、2018／ROC 107、2022／ROC 111；T1 保留選舉區，V1 才按 29 區。

YOI 依 `docs/homepage_analysis.md` 的五個子指數與權重計算。已知缺值會
保留 `null` 並標記品質資訊：VT 以觀察到的最低課程數補值、缺租金／房價
以觀察最低值作 proxy、房價只以住宅資料計算（平溪可回退全部類型）、
無鐵路站為 structural zero；公車與自行車無法可靠對應行政區的列不納入。
職缺薪資只有同時有上下限的 `salary_midpoint` 才納入中位數。

首頁的高薪職缺比例使用同一個全市薪資中位數門檻，但分母是該區
`job_vacancies` 的全部區級 `position_count`；不是只有具完整薪資上下限的
職缺。薪資資料若只有單邊上下限，會保留原始欄位、排除出
`salary_midpoint`，並在品質報告記錄排除數。

服務涵蓋率使用 `population_villages`、`village_boundaries` 與已驗證座標的
青創基地，對聯集 2.5 km buffer 做里界面積比例分攤。沒有可驗證座標的
據點不會被當成 0 覆蓋；結果會回傳 `unavailable` 或 `partial`，並列出
`blocking_reasons`、`verified_point_count` 與 `excluded_point_count`。

2026-09-11 實際輸出摘要：`current_yoi.districts` 29 筆；年度人口、生育率
與預算均為 ROC 110–114；T1 31 個選舉區列與 V1 87 個行政區／年度列均保留
各自 grain；服務涵蓋率全市 `49.2266230851`%、狀態 `partial`，9 個據點
通過座標驗證、0 個據點排除，里界 1,039 筆中有 1,032 筆接上里級人口。
品質報告另記錄 3,111 筆職缺薪資中 2,270 筆有完整上下限可作 midpoint、
公車 4,149 筆與自行車 5 筆無法對應行政區，以及平溪／坪林租金缺區的
observed-minimum proxy。

## 27. `employment` analytics

執行 `run_analytics.py --metric employment` 會先產生首頁 YOI，再直接沿用
`current_yoi.districts` 的五個 `yoiComponents`，不重新計算五個子指數。
輸出如下：

- `data/analytics/employment/all.json`：青年就業頁 29 區資料與兩張散點圖。
- `data/quality/analytics_employment.json`：來源期間、輸入筆數、29 區／散點圖覆蓋率、OLS 有效樣本數與品質警告。

每區公開欄位包含 `score_job`、`score_salary`、`score_talent`、
`score_housing`、`score_transport`、`knowledge_job_ratio`、
`estimated_wage`、`estimated_monthly_wage`、`house_price_median_wan` 與
`quality_status`。薪資欄位單位為萬元／年、萬元／月；
`house_price_median_wan` 單位為萬元／坪；`knowledge_job_ratio` 單位為百分比。

`knowledge_job_ratio` 只使用 `geo_level=district` 的職缺，分子為 raw
`EDGRDESC（最低學歷要求）` 含「大學」「專科」「學士」「碩士」或「博士」的
`position_count`，分母為該區全部職缺 `position_count`。沒有有效職缺時輸出
`null`，不以 0 代替。

兩張散點圖的 regression 都由 pipeline 以純 Python OLS 計算，忽略 `null`、
NaN、Infinity；0 是有效數值，不會因為布林判斷而排除。輸出
`method`、`sample_size`、`slope`、`intercept`、`r_squared`；有效點不足兩筆
或 X 無變異時，回歸係數保留 `null`。

目前真實來源期間為 `11509`，job vacancies 與 house prices 各產生 29 個行政區
點；薪資代理沿用 homepage 的最新可得 25–29 歲官方薪資，並在品質報告標示
proxy／latest available。公開 analytics 不包含 `raw_record` 或 `raw_records`。

## 28. 開發用 published snapshot

首頁或青年就業 analytics 可用 `run_analytics.py --metric homepage --publish`
或 `run_analytics.py --metric employment --publish` 發布為
Backend 可讀的版本化本機 snapshot。發布層只讀已產生的 homepage analytics，
不重新抓政府 API，也不重新計算指標。使用目前真實資料產生開發 snapshot 的指令為：

```bash
cd data-pipeline
.venv/bin/python src/run_analytics.py \
  --metric homepage \
  --publish \
  --snapshot-id dev-homepage-20260911
```

本次輸出為：

```text
data/analytics/published/dev-homepage-20260911/manifest.json
data/analytics/published/dev-homepage-20260911/dashboard_overview.json
data/analytics/published/dev-homepage-20260911/district_details.json
data/analytics/published/current.json
```

青年就業 snapshot 另包含：

```text
data/analytics/published/dev-employment-20260911/manifest.json
data/analytics/published/dev-employment-20260911/dashboard_overview.json
data/analytics/published/dev-employment-20260911/district_details.json
data/analytics/published/dev-employment-20260911/analyses/employment.json
data/analytics/published/current.json
```

`manifest.json` 的 `artifacts.analyses.employment` 指向就業 analytics，
`datasets` 同時記錄其 `source_period`、`coverage` 與品質旗標。

`current.json` 只保存目前 snapshot id；Backend 先讀取此指標，再依
`manifest.json` 的相對 artifact 路徑讀取同一個 snapshot。overview 保留首頁
KPI、29 區、年度資料、選舉、預算與服務涵蓋率；district details 將 29 區列
拆成行政區與 metrics。`null`、`partial`、`unavailable` 會保留，不轉成 0。
發布 artifact 不包含 `raw_record`、`raw_records` 或原始 PDF；完整缺值與來源
品質仍保留在 `data/quality/analytics_homepage.json`。

## 使用建議

1. Analytics 應先按 `youth_eligibility` 篩選：核心青年指標只用 `eligible`。
2. 區級比較只能使用 `geo_level=district` 且 `district_id` 不為 `null` 的資料。
3. `county` 或 `national` 資料與行政區資料並用時，必須標示為 proxy 或背景比較。
4. 房價、租金、職缺與交通目前都是明細／快照；中位數、YoY、密度或綜合指數應在 `analytics/` 計算。
5. 在修正 authoritative index 前，不能只讀最新 `dataset_index.json` 來判斷完整歷史資料範圍。
