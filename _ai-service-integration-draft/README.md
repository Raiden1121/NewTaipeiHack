# AI Service ⟷ DynamoDB 串接草稿

背景：ai-service（Bedrock 那邊）目前**已經完全不讀本機檔案**——正式部署的
Lambda（`ai-service/src/handlers/lambda.ts`）從 request body 拿 evidence，
不會去讀 `data-pipeline/data/` 或任何資料庫（見 `ai-service/DEPLOYMENT.md`
第 1 節）。`CuratedFileEvidenceRepository` / `AnalyticsSnapshotEvidenceRepository`
只在本機開發腳本（`npm run dev:explain` 之類）用得到，不在 Lambda 的執行路徑上。

真正缺的那塊，是 `infrastructure.md` 列出來的：「backend 實際呼叫這支 Lambda
的程式碼」——也就是「誰去讀 DynamoDB、組成 AiRequestContext、再打給
ai-service」，架構圖上這是 Backend 的工作，IAM 也已經照這個方向開好了
（`modules/ai_service/main.tf` 的 `allow_backend_invoke`），只是 code 還沒寫。

這個資料夾是那塊程式碼的草稿，**沒有覆蓋任何現有檔案**——全部是加在
`_ai-service-integration-draft/` 底下的獨立副本，對照下面清單手動合併到
`infrastructure/` 對應位置後再刪掉這個資料夾。

## 改了什麼

| 檔案 | 改動 |
|---|---|
| `infrastructure/modules/api/lambda/handler.py` | 新增 `POST /api/v1/ai/{action}`：讀 DynamoDB → 組 `AiEvidence[]` → 直接 `lambda:invoke` ai-service |
| `infrastructure/modules/api/main.tf` | 新增 IAM 權限（允許呼叫 ai-service）、新增 `AI_SERVICE_LAMBDA_NAME` 環境變數、**新增 Lambda Function URL**（原因見下） |
| `infrastructure/modules/api/variables.tf` | 新增 `ai_service_lambda_name` / `ai_service_lambda_arn` / `timeout`（原本寫死 10 秒） |
| `infrastructure/modules/api/outputs.tf` | 新增 `ai_proxy_function_url` |
| `infrastructure/main.tf` | 把 `module.ai_service` 的輸出接進 `module.api` |
| `infrastructure/outputs.tf` | 新增 `ai_proxy_function_url` 輸出 |

## 兩個一定要知道的坑

**1. 這張 DynamoDB 表跟 ai-service 原本想要的「DynamoDB」不是同一種形狀。**

架構圖上寫「DynamoDB / AI Context」，容易讓人以為隊友建的表就是
`shared/src/aiContextTable.ts` 那份提案（PK=`DISTRICT#<id>`、每筆一個
metricId/value，還有 GSI 可以「一個指標查全 29 區」）。實際上隊友建的
`{project_name}-analytics` 表是給 Backend REST API 用的（`dynamodb_schema.md`），
存的是已經整理成 API 回應形狀的 item（`DASHBOARD/DISTRICTS` 整包 29 區、
`DASHBOARD/POLICY`、`ANALYSIS#employment-scatter/DATA`…），**不是**逐指標
一列。所以沒有現成的 metricId/value 可以照抄，這份草稿是自己把每個 item
的純量欄位攤平成一筆 `AiEvidence`（`_flatten_scalars()`），metricId 就是
DynamoDB 上的欄位名。

這樣做得到「能動」，但代價是：
- 每個欄位的 `unit`／`youthEligibility` 要手動填（`_METRIC_META`），沒填到的
  預設 `unit=null`、`youthEligibility=context_only`——保守但不精確，AI 回答
  可能因此漏掉單位或誤判是不是青年專屬數據。跑過幾次 QA 之後要回來補這張表。
- 巢狀欄位（`budgetTrend[]`、`populationTrend[]`、關鍵字清單…）目前**沒有**
  攤平進 evidence，只在 `knownLimitations` 裡誠實說「這次沒涵蓋」。如果
  demo 會被問到這些面向，需要另外寫攤平邏輯。

**2. AI 的 Q&A 不能走現有的 API Gateway。**

`modules/api/main.tf` 的 HTTP API 有寫死 30 秒的 integration timeout（AWS
平台限制，改不了）。而 Q&A 實測 14–30 秒，`BEDROCK_MAX_ATTEMPTS=2` 代表
驗證失敗時會重打一次，逼近甚至超過 30 秒。這就是為什麼草稿改用
**Lambda Function URL**（`aws_lambda_function_url.ai_proxy`）而不是加一條
API Gateway route——Function URL 沒有這個 30 秒上限，只吃 Lambda 自己的
`timeout`（草稿設 60 秒，跟 explain/policyCopilot 走預先算不同，Q&A 是即時算）。

前端會因此多一個 base URL：原本 5 個讀取端點還是打 `api_endpoint`
（API Gateway），AI 這條打新的 `ai_proxy_function_url`（Function URL）。

## 還沒做、需要人決定的事

- `_METRIC_META` 目前只填了少數幾個欄位，其餘全部保守處理成
  `context_only`——建議先用 `terraform apply` 部署後，拿真實 snapshot 跑
  `dev:qa-latency` 那類腳本觀察 AI 回答，缺什麼再補。
- `focusArea` 目前沒有拿來篩選要讀哪些 `ANALYSIS#*` item（ai-service 本機
  路徑的 `ANALYTICS_ARTIFACTS_BY_FOCUS_AREA` 做了這件事，這裡還沒做）——
  現在每次都只讀 `DASHBOARD/DISTRICTS` + 指定行政區的 `SUMMARY`，不會主動
  帶入 `ANALYSIS#employment-scatter` 之類的分析。夠不夠用要看 demo 題目。
- `api_contract.md` 沒有把這個新端點寫進去，前端也還沒接。
- Function URL 目前 `authorization_type = "NONE"`——跟 ai-service 自己的
  Lambda 一樣完全沒有 auth，公開後任何人都能打 Bedrock 帳單，上線前要處理
  （`ai-service/DEPLOYMENT.md` 也提過同樣的事）。

## 套用方式

確認沒問題後，把這 6 個檔案覆蓋回 `infrastructure/` 對應路徑（不含這個
`_ai-service-integration-draft` 資料夾本身），跑：

```bash
cd infrastructure
terraform init   # 如果還沒 init 過
terraform plan   # 先看 plan，確認只新增資源、沒有預期外的刪除
terraform apply
```

`terraform output ai_proxy_function_url` 可以拿到新端點測試：

```bash
curl -X POST "$(terraform output -raw ai_proxy_function_url)" \
  -H 'content-type: application/json' \
  -d '{"question":"板橋區青年人口有多少？","focusDistrict":"板橋區","focusArea":"population"}'
```
