# Infrastructure

## Purpose

Infrastructure 管理本專案的 AWS Cloud Resources，以及各服務之間的部署與權限連接。

Terraform root 就是這個資料夾（`main.tf`／`variables.tf`／`outputs.tf`／`versions.tf`）。`modules/frontend/` 已建立 Frontend 的 S3 + CloudFront（Origin Access Control、SPA fallback 到 `index.html`）；`terraform apply` 會連動 build 與部署 React（見 Project Usage）。`modules/api/` 已建立單一 Lambda（Python，`modules/api/lambda/handler.py`）+ API Gateway HTTP API，處理 `api_contract.md` 定義的 5 個讀取端點（`health`、`catalog`、`dashboard/overview`、`districts/{id}`、`analyses/{id}`）；handler 已改成用 `BatchGetItem` 讀 DynamoDB 並依契約形狀組 response，不在 request 期間重新計算指標，router／envelope 沒變。`modules/raw_data/` 已建立一個私有、有版本控制的 S3 bucket，供 data-pipeline 之後上傳/維護抓取到的 raw data；目前還沒有任何程式接上去寫入，也還沒有對應的 IAM 存取權限，等實際串接時再補。`modules/transformed_data/` 同樣模式，另建一個私有、有版本控制的 S3 bucket，供存放 raw data 轉換後的資料；也還沒有程式接上去寫入或對應 IAM 權限。`modules/analytics_table/` 已建立單一 DynamoDB 表（`pk`/`sk`），儲存 data-pipeline 發布的 analytics snapshot，schema 與寫入約定見 `dynamodb_schema.md`；目前是空的，寫入這張表是另一支程式（data-pipeline 的 loader）的責任，不需要再改 `handler.py`。`modules/ai_service/` 已建立單一 Lambda（Node.js 22，ESM，打包用 esbuild 把 `ai-service/src/handlers/lambda.ts` bundle 成 `dist-lambda/index.mjs`，見 `ai-service/DEPLOYMENT.md`），有 `bedrock:InvokeModel` 權限（含跨區 inference profile 需要的兩層 ARN）。**刻意沒有掛 API Gateway 或 Function URL** —— 這支 handler 目前沒有任何 authentication，公開掛出去等於任何人都能刷 Bedrock 帳單；只用 IAM 讓 `module.api` 的 Lambda 執行角色可以直接 `lambda:InvokeFunction` 呼叫它（同帳號呼叫不需要 resource-based policy），但 backend 目前還沒有真的去呼叫它的程式碼，這個授權先開著等 backend 接上。模型預設是 Haiku 4.5（`var.bedrock_model_id`，可覆寫），原因與延遲實測數字見 `ai-service/DEPLOYMENT.md` 第 5 節。部署前**要先在 Bedrock 主控台開通該模型的 Model access**——這是帳號層級設定，Terraform 管不到。其餘服務（Data Pipeline 的 Lambda/EventBridge）尚未建立實際資源，未來以 `module "xxx" { source = "./modules/xxx" ... }` 的方式陸續加入同一個 root。CDK package、`cdk.json` 與 `bin/`、`lib/` 仍是 placeholder，未使用。

## Responsibilities

Frontend、API（讀 DynamoDB）、raw data / transformed data 用的 S3、analytics 用的 DynamoDB、AI Service（Bedrock）都已用 Terraform 建立。其餘規劃：

- Data Pipeline：Lambda、EventBridge Scheduler、Step Functions、把 raw data 轉換後寫進 transformed data bucket、把 published snapshot 寫進 DynamoDB 的程式（bucket 已建立，見上方；DynamoDB schema 見 `dynamodb_schema.md`）——這支程式寫完、跑過一次之前，DynamoDB 是空的，`handler.py` 的每個端點（除了 `/health`）都會回 503 `SNAPSHOT_UNAVAILABLE`。
- AI：Lambda 與 `bedrock:InvokeModel` 權限已建立（`modules/ai_service/`）。還沒做的：backend 實際呼叫這支 Lambda 的程式碼（見 `backend/backend.md` 的 Boundaries）、DynamoDB evidence repository（見 `ai-service/DEPLOYMENT.md` 第 1 節）、Knowledge Base / RAG resources（如果之後需要）。
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

AI Service 沒有對外端點，只能用 AWS credentials 直接 invoke（測試方式見 `ai-service/DEPLOYMENT.md` 第 7 節）：

```bash
aws lambda invoke --function-name "$(terraform output -raw ai_service_lambda_name)" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"body":"{\"action\":\"explain\",\"context\":{\"question\":null,\"focusDistrict\":\"板橋區\",\"focusArea\":\"population\",\"evidence\":[],\"knownLimitations\":[]}}"}' \
  out.json && cat out.json
```

其餘服務尚未建立實際 Stack 或指令。

Source metadata 的部署順序是：pipeline 產生含 `manifest.sources` 的 published snapshot，loader 將同一個 `snapshot_id` 寫入 DynamoDB，最後 Backend 才切換讀取該 snapshot。此來源欄位計畫不執行 Terraform apply，也不修改既有 Raw S3 object。

## Inputs & Outputs

- 輸入：各服務的部署設定、環境參數與資源依賴。
- 輸出：可部署的 AWS Cloud Resources、IAM permissions 與服務連接。

## Boundaries

Infrastructure 只負責 AWS 資源如何建立、連接與部署，不包含 Dashboard business logic、指標計算、React UI、AI Prompt 或 ETL logic。
