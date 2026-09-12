# DynamoDB Schema — Analytics Store

儲存 data-pipeline 發布的 analytics snapshot，供 `infrastructure/modules/api/lambda/handler.py` 讀取後回應 `api_contract.md` 的 5 個端點。`handler.py` 只負責讀；把資料寫進這張表是另一支程式的責任（data-pipeline 把 published snapshot 依下面的 item 清單寫入），本檔案是雙方共用的 schema 定義。表目前是空的：任何端點在 `META/MANIFEST` 不存在時都回 503 `SNAPSHOT_UNAVAILABLE`（`/health` 除外，它回 200 並標示 `manifest_readable: false`）。

## 設計原則

DynamoDB 存的是 **api_contract.md 實際要用的形狀**，不是每個 pipeline artifact 的原始鏡射。理由：

- `dashboard_overview.json` 的 `service_coverage.villages[]`、`fertility.json` 的 `daycareCoverage.villages[]`（各 ~200KB，1032 筆村里明細）——契約沒有任何端點回傳村里層級資料，只回城市/區級彙總。
- `keyword_frequency`（172KB）——`api_contract.md` §6.4 明講文字雲要用 `topic_weight`，不要用這個。
- `elections.city_councilor_t1[]`（31 筆選區資料）——契約 §6.1 說這些 `district_id` 全部是 `null`，無法對應 29 區，只有 citywide 彙總能用。
- `proposal_funnel`、`grants`（原始物件）——目前沒有任何端點會回傳它們。

排除以上內容後，每個 item 都遠低於 DynamoDB 400KB 上限，不需要 S3 backing、不需要壓縮。這些原始資料仍完整保留在 data-pipeline 自己的 published JSON 裡，只是不重複搬進 DynamoDB。

另一條原則（`api_contract.md` §0.2、§1.5）：**任何需要算術的收斂（加總、除法、取比例）都必須是 data-pipeline 算好的純量，寫進表裡就是最終值**，Lambda 在 request 期間不重算。如果底層是多年/多屆的 Series 但契約只要「現在」一個數字，DynamoDB 存的是那個算好的 Scalar，不是叫 Lambda 從 Series 裡臨時挑一筆去算。像「從物件裡讀一個既有欄位」「把陣列重新包裝成另一種形狀」這種不含計算的整形，才可以留給 Lambda 做（例如 §6.3 的 `budgetTrend`、下面 `policy-outcomes` 的 `populationTrend[]`）。

## 資料表

- 名稱：`{project_name}-analytics`（單一表）
- Key：`pk`（String）+ `sk`（String）
- Billing：`PAY_PER_REQUEST`
- Point-in-time recovery：開啟（之後有其他程式會寫入這張表，PITR 是防誤寫的安全網，成本幾乎為 0）

每個 API 端點都只需要一次 `GetItem` 或一次 `BatchGetItem`，沒有 Query、Scan、GSI。

## Items

| pk | sk | 內容 | 實測大小＊ | 對應端點 |
|---|---|---|---|---|
| `META` | `MANIFEST` | `snapshot_id`、`generated_at`、`calculation_version`、`districts_count`、`time_policy{annual_years_roc, election_years_roc}`、`warnings[]` | <1KB | `GET /catalog`，以及每個 response 的 `meta` 區塊 |
| `DASHBOARD` | `KPIS` | `kpis{...}`、`availability{...}` | <1KB | §4.1、§1.3 |
| `DASHBOARD` | `POLICY` | `policy{currentBudget, budgetYoY, executionRate, executionFailure, budgetTrend[]}` | <1KB | §4.6；`budgetTrend`/`executionRate` 也被 §6.3 重用 |
| `DASHBOARD` | `SERVICE_COVERAGE` | 城市層級 `value`/`status` + 診斷欄位（`radius_m`、`verified_point_count`、`population_coverage_ratio`、`boundary_village_count`、`joined_village_count`、`blocking_reasons`）——**不含** `villages[]` | <1KB | §4.4、§6.2 診斷欄位 |
| `DASHBOARD` | `ELECTIONS` | `city_councilor_t1_citywide[3]`、`borough_chief_v1_citywide{year_roc, elected_count, youth_elected_count, ratio_percent}`（pipeline 算好的全市純量）、`borough_chief_v1[87]`（3 屆明細，保留供未來「近三屆趨勢」用，目前無端點直接消費整包） | ~44KB | §4.4、§6.1、§6.2 |
| `DASHBOARD` | `POPULATION_TREND` | `annual.population.years[]`（5 年 × 城市 + 29 區） | ~24KB | §4.1 趨勢註、§7.2 青年人口占比、§8.1 `populationTrend`（Lambda 從這裡重新組陣列，不重複存） |
| `DASHBOARD` | `FERTILITY_TREND` | `annual.fertility.years[]`（5 年 × 城市 + 29 區） | ~43KB | §4.5、§7.2 |
| `DASHBOARD` | `DISTRICTS` | 完整 `districts[]`，29 筆，每筆含 §3.1 全部 **29** 個欄位（含新增的 `youthBoroughChiefRatioPercent`） | ~86KB | `GET /dashboard/overview` |
| `DISTRICT#<district_id>` | `SUMMARY` | 與上面同一份逐區物件，單筆 | ~3KB ×29 | `GET /districts/{districtId}` |
| `ANALYSIS#employment-scatter` | `DATA` | `employment.json` 的 `scatter.knowledge_job_vs_estimated_wage` + `scatter.monthly_wage_vs_house_price`（含 `points[]`/`regression`/`note`） | 數 KB | §5.3 |
| `ANALYSIS#fertility-overlay` | `DATA` | `fertility.json` 的 `scatter`（`points[]`/`regression`） | ~3KB | §7.3 |
| `ANALYSIS#fertility-family-friendliness` | `DATA` | `fertility.json` 的 `fafi`（逐區 `fafi_score`/`fafi_level` + normalization 門檻） | ~5KB | §7.4 |
| `ANALYSIS#youth-topic-weight` | `DATA` | `topic_weight.json` 原樣（完整歷史年份，不只 114 年） | ~49KB | §6.4——**backend 讀取時**才挑 `year_roc === 114`，這只是挑一筆既有資料、不含計算，年份選擇邏輯不搬進 storage 層，未來要做「議題歷年變化」可直接復用 |
| `ANALYSIS#politics-resource-io` | `DATA` | `budget_by_department[]`，以及 `snapshot_id`、`analysis_id`、`budget_year_roc`、`document_status`、`sourceRefs` | 小 | §6.3——由 published `analyses/participation.json` 的 `budget_allocation.items[]` 投影而來：`name → label`、`amount ÷ 1000 → amount_thousand`、`share_percent` 原值保留。缺少 allocation 時寫入空陣列，不以 0 偽造資料。`budgetTrend`/`executionRate` 不重複存在這裡，backend 組 response 時去讀 `DASHBOARD/POLICY`。|
| `ANALYSIS#policy-outcomes` | `DATA` | `policy_support.json` 的 `policyOutcomes`：`wageTrend[]`、`currentWageGrowth`、`currentPopGrowth`、`desiredDirection{wageGrowth, populationChange}` | 數 KB | §8.1——**不存 `populationTrend[]`**，該陣列 Lambda 讀取時從 `DASHBOARD/POPULATION_TREND` 的 `annual.population.years[]` 重新組裝（純整形，非計算），跟 §6.3 重用 `DASHBOARD/POLICY` 是同一個作法 |

＊ 以 `dev-full-20260912` snapshot 實測。

## 明確排除、不寫進這張表

- `service_coverage.villages[]` / `daycareCoverage.villages[]` — 村里層級診斷資料，無端點使用
- `keyword_frequency` artifact — 契約要求改用 `topic_weight`
- `elections.city_councilor_t1[]`（31 筆選區） — `district_id` 全 `null`，只有 citywide 彙總可用
- `proposal_funnel`、`grants`（原始物件） — 目前無端點回傳

如果之後真的需要，補一個新 item（新的 `sk`）即可，不需要重新設計整張表。

## 給「之後維護這張表的程式」的寫入約定

- 每次發布**直接覆寫**對應的 item，DynamoDB 本身不做多版本保留——歷史版本的真實來源是 data-pipeline 自己的 `data/analytics/published/<snapshot_id>/` 資料夾，不需要在 DynamoDB 裡重複保留。
- **`META/MANIFEST` 最後寫**：`GET /catalog` 和每個 response 的 `meta.generated_at` 都是拿它判斷資料新鮮度，先寫完其他 item 再更新這筆，可以避免「manifest 已經指向新 snapshot，但其他 item 還沒寫完」的中間狀態被讀到。
- 逐區資料要寫兩處（`DASHBOARD/DISTRICTS` 的陣列裡一份 + `DISTRICT#<id>/SUMMARY` 各一份）：同一份算好的物件序列化兩次，不是兩份不同計算，維護時記得两邊同時更新。這條也適用於新增的 `youthBoroughChiefRatioPercent`。
- `youthBoroughChiefRatioPercent`（逐區）與 `elections.borough_chief_v1_citywide`（全市彙總）**必須是 data-pipeline 已經算好的純量**（`youth_elected_count / elected_count × 100`，固定 111 年屆），寫入時直接放算好的值；不要只寫 `borough_chief_v1[]` 原始明細，指望 Lambda 之後自己重新算一次比例。

## 讀取端

`infrastructure/modules/api/lambda/handler.py` 已改成讀這張表：每個 route 先用 `BatchGetItem` 把需要的 item 一次抓回來（`GetItem`/`BatchGetItem`/`Query` 權限已在 `infrastructure/modules/api/main.tf` 授予，表名也已寫入環境變數 `ANALYTICS_TABLE_NAME`），再依 `api_contract.md` 的形狀組 response，不重新計算指標。等 data-pipeline 有真實 snapshot 之後，用同一組 pk/sk 覆寫即可，`handler.py` 不需要再改。

`analyses/policy-outcomes` 的 `populationTrend[].yoy` 是唯一例外：這是逐年百分比變化，不是單純的欄位挑選或重新包裝，嚴格來說已經超出「Lambda 不計算」的邊界，是刻意接受、有記錄下來的例外，尚未解決（要解的話，得改成 data-pipeline 直接把算好的 `yoy` 存進 `DASHBOARD/POPULATION_TREND` 或 `ANALYSIS#policy-outcomes` 本身）。
