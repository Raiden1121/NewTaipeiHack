# Infrastructure

## Purpose

Infrastructure 管理本專案的 AWS Cloud Resources，以及各服務之間的部署與權限連接。

Terraform root 就是這個資料夾（`main.tf`／`variables.tf`／`outputs.tf`／`versions.tf`）。`modules/frontend/` 已建立 Frontend 的 S3 + CloudFront（Origin Access Control、SPA fallback 到 `index.html`）；`terraform apply` 會連動 build 與部署 React（見 Project Usage）。`modules/api/` 已建立單一 Lambda（Python，`modules/api/lambda/handler.py`）+ API Gateway HTTP API，處理 `api_contract.md` 定義的 5 個讀取端點（`health`、`catalog`、`dashboard/overview`、`districts/{id}`、`analyses/{id}`），目前回傳的是 mock 資料；等 data-pipeline 把 analytics 寫進 DynamoDB 後，換掉 handler 裡的 `_build_*`/`_analysis_*` builder 即可，router／envelope 不用動。`modules/raw_data/` 已建立一個私有、有版本控制的 S3 bucket，供 data-pipeline 之後上傳/維護抓取到的 raw data；目前還沒有任何程式接上去寫入，也還沒有對應的 IAM 存取權限，等實際串接時再補。`modules/analytics_table/` 已建立單一 DynamoDB 表（`pk`/`sk`），儲存 data-pipeline 發布的 analytics snapshot，schema 與寫入約定見 `dynamodb_schema.md`；API Lambda 已有讀取權限與表名環境變數，但 `handler.py` 還沒有改成真的讀取。其餘服務（Data Pipeline 的 Lambda/EventBridge、AI）尚未建立實際資源，未來以 `module "xxx" { source = "./modules/xxx" ... }` 的方式陸續加入同一個 root。CDK package、`cdk.json` 與 `bin/`、`lib/` 仍是 placeholder，未使用。

## Responsibilities

Frontend、API（mock data）、raw data 用的 S3、analytics 用的 DynamoDB 都已用 Terraform 建立。其餘規劃：

- Backend：把 API Lambda 換成真的 DynamoDB 讀取（見 `dynamodb_schema.md`）。
- Data Pipeline：Lambda、EventBridge Scheduler、Step Functions、把 published snapshot 寫進 DynamoDB 的程式（raw data bucket 已建立，見上方）。
- AI：Lambda、Amazon Bedrock permissions 與未來的 Knowledge Base / RAG resources。
- Storage：S3 與 DynamoDB。
- Monitoring：未來可加入 CloudWatch、Logs 與 Alarms。

## Project Usage

```bash
cd infrastructure
terraform init
terraform apply
```

`terraform apply` 除了建立/更新 S3、CloudFront、API Gateway、Lambda，也會執行 `npm run build`（於 `frontend/`）、`aws s3 sync` 上傳 `dist/` 到 bucket，並對 CloudFront 發送 cache invalidation；每次 apply 都會重新 build 並部署目前的前端原始碼。同時會把根目錄 `slides/`（簡報用的 `index.html` + PDF + logo）同步到同一個 frontend bucket 的 `slides/` 路徑下，並只 invalidate `/slides/*`，不需要額外的 build 步驟；`modules/frontend/` 也掛了一個 CloudFront Function，把 `/slides`、`/slides/` 這兩個網址改寫成 `/slides/index.html`（S3 REST origin 不會像 S3 網站託管一樣自動補 index.html，沒改寫的話會 403 掉回 SPA 的 index.html）。執行前需已設定好可用的 AWS credentials（`aws configure` 或環境變數）。

API 端點在 apply 完成後可從 `terraform output api_endpoint` 取得，例如：

```bash
curl "$(terraform output -raw api_endpoint)/api/v1/dashboard/overview"
```

其餘服務尚未建立實際 Stack 或指令。

## Inputs & Outputs

- 輸入：各服務的部署設定、環境參數與資源依賴。
- 輸出：可部署的 AWS Cloud Resources、IAM permissions 與服務連接。

## Boundaries

Infrastructure 只負責 AWS 資源如何建立、連接與部署，不包含 Dashboard business logic、指標計算、React UI、AI Prompt 或 ETL logic。
