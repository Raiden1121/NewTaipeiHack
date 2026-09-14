# Infrastructure

## Purpose

Infrastructure 管理本專案的 AWS Cloud Resources，以及各服務之間的部署與權限連接。

Terraform root 就是這個資料夾（`main.tf`／`variables.tf`／`outputs.tf`／`versions.tf`）。`modules/frontend/` 已建立 Frontend 的 S3 + CloudFront（Origin Access Control、SPA fallback 到 `index.html`）；`terraform apply` 會連動 build 與部署 React（見 Project Usage）。`modules/api/` 已建立單一 Lambda（Python，`modules/api/lambda/handler.py`）+ API Gateway HTTP API，處理 `api_contract.md` 定義的 5 個讀取端點（`health`、`catalog`、`dashboard/overview`、`districts/{id}`、`analyses/{id}`）與同步的 `POST /api/v1/ai/query`；handler 已改成用 `BatchGetItem` 讀 DynamoDB 並依契約形狀組 response，不在 request 期間重新計算指標，router／envelope 沒變。`modules/raw_data/` 已建立一個私有、有版本控制的 S3 bucket，供 data-pipeline 之後上傳/維護抓取到的 raw data；目前還沒有任何程式接上去寫入，也還沒有對應的 IAM 存取權限，等實際串接時再補。`modules/transformed_data/` 同樣模式，另建一個私有、有版本控制的 S3 bucket，供存放 raw data 轉換後的資料；也還沒有程式接上去寫入或對應 IAM 權限。`modules/analytics_table/` 已建立單一 DynamoDB 表（`pk`/`sk`），儲存 data-pipeline 發布的 analytics snapshot，schema 與寫入約定見 `dynamodb_schema.md`。`modules/analytics_lambda/` 就是寫入這張表的程式：一支 Python zip Lambda（entrypoint `modules/analytics_lambda/lambda/handler.py`），從 transformed data bucket 讀 `curated/`＋`quality/`，跑跟 `run_analytics.py --metric all` 同一套 analytics（不重算 `keyword_frequency` metric——published 的 `participation` analysis 已經帶了 `topics.keyword_frequency`），用同一支 `publish_homepage_snapshot()` 在 `/tmp` 組出 published snapshot，再由 `modules/analytics_lambda/lambda/dynamodb_projection.py` 投影成 43 個 DynamoDB items 寫入（投影規則見 `dynamodb_schema.md`，單元測試在 `modules/analytics_lambda/tests/`）。封裝由 `modules/analytics_lambda/build.py` 組出：`pip install --platform manylinux2014_x86_64` 抓 Lambda runtime 平台的 wheel（所以**不需要 Docker**，Windows 也能 build），再把 `data-pipeline/src` 攤平進 zip 根目錄、`data-pipeline/config` 放成 handler 的同層 `config/`。實測 101MB 解壓／28MB 壓縮，離 250MB／50MB 上限還很遠——因為 analytics 實際只會 import 到 shapely 與 pyproj（`lambda/requirements.txt` 只列這兩個；jieba 是函式內延遲 import 且這支不跑該 metric，pypdf／pyshp 只有 `collectors/` 用）。curated 資料**不預先整包同步**（bucket 約 40GB），而是 `handler._install_s3_backing()` 攔截 `pathlib` 讀取、要哪個 dataset period 才抓哪個（實際約 2GB）。記憶體與 `/tmp` 都開到 10GB 上限，因為 `load_curated_periods()` 會把要求的期間一次全部載進記憶體。這支 Lambda **刻意沒有排程也沒有端點**——一次執行會讀數 GB 並整表覆寫，要跑就明確 invoke（見 Project Usage）。`modules/ai_service/` 已建立單一 Lambda（Node.js 22，ESM，打包用 esbuild 把 `ai-service/src/handlers/lambda.ts` bundle 成 `dist-lambda/index.mjs`，見 `ai-service/DEPLOYMENT.md`），有 `bedrock:InvokeModel` 權限（含跨區 inference profile 需要的兩層 ARN）。**刻意沒有掛 API Gateway 或 Function URL** —— 正式流量由既有 API Lambda 的 `POST /api/v1/ai/query` 經 IAM 同步呼叫，AI handler 本身不直接公開；AI Service 仍只接受 API Lambda role 的 `lambda:InvokeFunction`。模型使用 `var.bedrock_model_id`（目前預設 Sonnet 4.6，可覆寫），原因與延遲實測數字見 `ai-service/DEPLOYMENT.md` 第 5 節。部署前**要先在 Bedrock 主控台開通該模型的 Model access**——這是帳號層級設定，Terraform 管不到。其餘服務（Data Pipeline 的 Lambda/EventBridge）尚未建立實際資源，未來以 `module "xxx" { source = "./modules/xxx" ... }` 的方式陸續加入同一個 root。CDK package、`cdk.json` 與 `bin/`、`lib/` 仍是 placeholder，未使用。

## AI query serving path

`modules/api/lambda/handler.py` 是公開 API 邊界，除了既有 DynamoDB read endpoints
外，新增 `POST /api/v1/ai/query`。它驗證 `action`、`question`、focus、period 與
web search 欄位，拒絕 `context`、`evidence`、`webFindings`，再以
`InvocationType=RequestResponse` 呼叫固定名稱 `${project_name}-ai-service`。

AI Service Lambda 使用 `AI_EVIDENCE_SOURCE=dynamo` 與 `ANALYTICS_TABLE_NAME` 自己
讀取 evidence；`context` injection 只供本機與測試。API Lambda timeout 為 28 秒，
AWS Lambda client read timeout 約 25 秒，錯誤映射為 400/502/503/504。AI Service
仍維持 120 秒 timeout，且不直接掛 API Gateway 或 Function URL；`module.ai_service`
透過 IAM 將 `lambda:InvokeFunction` 授權給 API Lambda role。

## Responsibilities

Frontend、API（讀 DynamoDB）、raw data / transformed data 用的 S3、analytics 用的 DynamoDB、AI Service（Bedrock）都已用 Terraform 建立。其餘規劃：

- Data Pipeline：把 published snapshot 寫進 DynamoDB 的程式**已完成**（`modules/analytics_lambda/`，見上方）；在它跑過一次之前 DynamoDB 是空的，`handler.py` 的每個端點（除了 `/health`）都會回 503 `SNAPSHOT_UNAVAILABLE`。還沒做的：把 raw data 轉換後寫進 transformed data bucket 的程式（目前 bucket 內容是手動上傳的）、EventBridge Scheduler／Step Functions 排程。
- AI：Lambda 與 `bedrock:InvokeModel` 權限已建立（`modules/ai_service/`），並由既有 API Lambda 同步呼叫；DynamoDB evidence repository 已接上六類 `ANALYSIS#*` projection。尚未處理的是公開 API 的 authentication/rate limit 與 Knowledge Base / RAG resources（如果之後需要）。
- Storage：S3 與 DynamoDB。
- Source provenance：pipeline artifact 需一併打包 `data-pipeline/config/sources.json`；DynamoDB serving projection 保存 `source`、`sourceName`、`sourceUrl` 與 `sourceRefs`，不改變既有 snapshot PK/SK。
- Monitoring：未來可加入 CloudWatch、Logs 與 Alarms。

## Project Usage

```bash
cd infrastructure
terraform init
terraform apply
```

`terraform apply` 除了建立/更新 S3、CloudFront、API Gateway、Lambda，也會執行 `npm run build`（於 `frontend/`）、`aws s3 sync` 上傳 `dist/` 到 bucket，並對 CloudFront 發送 cache invalidation；每次 apply 都會重新 build 並部署目前的前端原始碼。同時會把根目錄 `slides/`（簡報用的 `index.html` + PDF + logo）同步到同一個 frontend bucket 的 `slides/` 路徑下，並只 invalidate `/slides/*`，不需要額外的 build 步驟；`modules/frontend/` 也掛了一個 CloudFront Function，把 `/slides`、`/slides/` 這兩個網址改寫成 `/slides/index.html`（S3 REST origin 不會像 S3 網站託管一樣自動補 index.html，沒改寫的話會 403 掉回 SPA 的 index.html）。`terraform apply` 也會 `npm ci` 並用 esbuild bundle `ai-service/`（見上方），同樣每次 apply 都重新打包。執行前需已設定好可用的 AWS credentials（`aws configure` 或環境變數）、Node/npm（frontend 與 ai-service 的 build 都靠它），以及在 Bedrock 主控台開通 `var.bedrock_model_id` 對應的模型。

API 端點在 apply 完成後可從 `terraform output api_endpoint` 取得，例如：

```bash
curl "$(terraform output -raw api_endpoint)/api/v1/dashboard/overview"
```

AI query 的公開 smoke test（由 API Lambda 驗證並同步 invoke AI Service）：

```bash
curl -X POST "$(terraform output -raw api_endpoint)/api/v1/ai/query" \
  -H 'content-type: application/json' \
  -d '{"action":"qa","question":"板橋區有多少青年？","webSearch":{"enabled":false}}'
```

Analytics Lambda 也沒有對外端點，要更新 DynamoDB 就明確 invoke 它（一次執行約 3–5 分鐘：下載 curated 約 2GB＋analytics 本機實測 145 秒）：

```bash
aws lambda invoke --function-name "$(terraform output -raw analytics_lambda_name)" \
  --cli-read-timeout 900 --payload '{}' out.json && cat out.json
```

回應會帶 `snapshot_id`、`items_written`、`elapsed_seconds` 與 `input_failures`（各 analytics 讀不到的 curated 輸入，依 dataset 分組；例如 `national_population` 出現在這裡代表 `curated/national_population/{yyyMM}.json` 沒上傳到 bucket，首頁全國青年人口會退回 proxy 常數）。要指定分析年度可帶 `{"annual_end_roc": 114}`，預設是「今年民國年減一」（最後一個完整年度）。

`terraform apply` 會執行 `modules/analytics_lambda/build.py` 重組這支 Lambda 的 zip（需要機器上有 `python` 與網路可連 PyPI，不需要 Docker）。build 的觸發條件是 `data-pipeline/src`、`data-pipeline/config`、`modules/analytics_lambda/lambda/` 與 `build.py` 的內容雜湊，原始碼沒變就不會重 build。

AI Service Lambda 沒有對外 HTTP endpoint；需要排查 ESM／Lambda 本身時，才用 AWS credentials 直接 invoke（測試方式見 `ai-service/DEPLOYMENT.md` 第 7 節）。正式查詢使用上面的 API route：

```bash
aws lambda invoke --function-name "$(terraform output -raw ai_service_lambda_name)" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"body":"{\"action\":\"qa\",\"question\":\"板橋區有多少青年？\",\"webSearch\":{\"enabled\":false}}","isBase64Encoded":false}' \
  out.json && cat out.json
```

其餘服務尚未建立實際 Stack 或指令。

Source metadata 的部署順序是：pipeline 產生含 `manifest.sources` 的 published snapshot，loader 將同一個 `snapshot_id` 寫入 DynamoDB，最後 Backend 才切換讀取該 snapshot。此來源欄位計畫不執行 Terraform apply，也不修改既有 Raw S3 object。

## Inputs & Outputs

- 輸入：各服務的部署設定、環境參數與資源依賴。
- 輸出：可部署的 AWS Cloud Resources、IAM permissions 與服務連接。

## Boundaries

Infrastructure 只負責 AWS 資源如何建立、連接與部署，不包含 Dashboard business logic、指標計算、React UI、AI Prompt 或 ETL logic。
