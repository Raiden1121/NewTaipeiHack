# DynamoDB Schema — Analytics Store

儲存 data-pipeline 發布的 analytics snapshot，供 `infrastructure/modules/api/lambda/handler.py`（目前是 mock，之後換成真讀取）回應 `api_contract.md` 的 5 個端點。

## 設計原則

DynamoDB 存的是 **api_contract.md 實際要用的形狀**，不是每個 pipeline artifact 的原始鏡射。理由：

- `dashboard_overview.json` 的 `service_coverage.villages[]`、`fertility.json` 的 `daycareCoverage.villages[]`（各 ~200KB，1032 筆村里明細）——契約沒有任何端點回傳村里層級資料，只回城市/區級彙總。
- `keyword_frequency`（172KB）——`api_contract.md` §6.4 明講文字雲要用 `topic_weight`，不要用這個。
- `elections.city_councilor_t1[]`（31 筆選區資料）——契約 §6.1 說這些 `district_id` 全部是 `null`，無法對應 29 區，只有 citywide 彙總能用。
- `proposal_funnel`、`grants`（原始物件）——目前沒有任何端點會回傳它們。

排除以上內容後，每個 item 都遠低於 DynamoDB 400KB 上限，不需要 S3 backing、不需要壓縮。這些原始資料仍完整保留在 data-pipeline 自己的 published JSON 裡，只是不重複搬進 DynamoDB。

## 資料表

- 名稱：`{project_name}-analytics`（單一表）
- Key：`pk`（String）+ `sk`（String）
- Billing：`PAY_PER_REQUEST`
- Point-in-time recovery：開啟（之後有其他程式會寫入這張表，PITR 是防誤寫的安全網，成本幾乎為 0）

每個 API 端點都只需要一次 `GetItem` 或一次 `BatchGetItem`，沒有 Query、Scan、GSI。

## Items

| pk | sk | 內容 | 實測大小＊ | 對應端點 |
|---|---|---|---|---|
| `META` | `MANIFEST` | `snapshot_id`、`generated_at`、`calculation_version`、`time_policy{annual_years_roc, election_years_roc}`、`warnings[]` | <1KB | `GET /catalog`，以及每個 response 的 `meta` 區塊 |
| `DASHBOARD` | `KPIS` | `kpis{...}`、`availability{...}` | <1KB | §4.1、§1.3 |
| `DASHBOARD` | `POLICY` | `policy{currentBudget, budgetYoY, executionRate, executionFailure, budgetTrend[]}` | <1KB | §4.6；`budgetTrend`/`executionRate` 也被 §6.3 重用 |
| `DASHBOARD` | `SERVICE_COVERAGE` | 城市層級 `value`/`status` + 診斷欄位（`radius_m`、`verified_point_count`、`population_coverage_ratio`、`boundary_village_count`、`joined_village_count`、`blocking_reasons`）——**不含** `villages[]` | <1KB | §4.4、§6.2 診斷欄位 |
| `DASHBOARD` | `ELECTIONS` | `city_councilor_t1_citywide[3]`、`borough_chief_v1[87]` | ~44KB | §4.4、§6.1、§6.2（青年里長占比由 `youth_elected_count/elected_count` 算） |
| `DASHBOARD` | `POPULATION_TREND` | `annual.population.years[]`（5 年 × 城市 + 29 區） | ~24KB | §4.1 趨勢註、§7.2 青年人口占比、§8.1 `populationTrend` |
| `DASHBOARD` | `FERTILITY_TREND` | `annual.fertility.years[]`（5 年 × 城市 + 29 區） | ~43KB | §4.5、§7.2 |
| `DASHBOARD` | `DISTRICTS` | 完整 `districts[]`，29 筆，每筆含 §3.1 全部 28 個欄位 | ~86KB | `GET /dashboard/overview` |
| `DISTRICT#<district_id>` | `SUMMARY` | 與上面同一份逐區物件，單筆 | ~3KB ×29 | `GET /districts/{districtId}` |
| `ANALYSIS#employment-scatter` | `DATA` | `employment.json` 的 `scatter.knowledge_job_vs_estimated_wage` + `scatter.monthly_wage_vs_house_price`（含 `points[]`/`regression`/`note`） | 數 KB | §5.3 |
| `ANALYSIS#fertility-overlay` | `DATA` | `fertility.json` 的 `scatter`（`points[]`/`regression`） | ~3KB | §7.3 |
| `ANALYSIS#fertility-family-friendliness` | `DATA` | `fertility.json` 的 `fafi`（逐區 `fafi_score`/`fafi_level` + normalization 門檻） | ~5KB | §7.4 |
| `ANALYSIS#youth-topic-weight` | `DATA` | `topic_weight.json` 原樣（完整歷史年份，不只 114 年） | ~49KB | §6.4——**backend 讀取時**才挑 `year_roc === 114`，年份選擇邏輯不搬進 storage 層，未來要做「議題歷年變化」可直接復用 |
| `ANALYSIS#politics-resource-io` | `DATA` | `budget_by_department[]` | 小 / placeholder | §6.3——⚠️ pipeline 目前沒有對應資料源（`youth_budgets.business_plan` 只有 3 類，對不上前端 4 個新科別），這個 item 現在只能放空陣列或 null，等青年局科別拆分確認後再補。`budgetTrend`/`executionRate` 不重複存在這裡，backend 組 response 時去讀 `DASHBOARD/POLICY`。|

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
- 逐區資料要寫兩處（`DASHBOARD/DISTRICTS` 的陣列裡一份 + `DISTRICT#<id>/SUMMARY` 各一份）：同一份算好的物件序列化兩次，不是兩份不同計算，維護時記得两邊同時更新。

## 讀取端

`infrastructure/modules/api/lambda/handler.py` 對應的 Lambda 已經被授予這張表的 `dynamodb:GetItem`/`BatchGetItem`/`Query` 權限（見 `infrastructure/modules/api/main.tf`），表名也已經寫入 Lambda 環境變數 `ANALYTICS_TABLE_NAME`。但 handler 目前**還沒有**改成讀 DynamoDB，仍在回傳 mock 資料——把 `_build_*`/`_analysis_*` 換成 `boto3` 讀取是下一步，不在這次變更範圍內。
