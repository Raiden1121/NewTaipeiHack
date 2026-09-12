# Infrastructure

## Purpose

Infrastructure 管理本專案的 AWS Cloud Resources，以及各服務之間的部署與權限連接。

Terraform root 就是這個資料夾（`main.tf`／`variables.tf`／`outputs.tf`／`versions.tf`）。`modules/frontend/` 已建立 Frontend 的 S3 + CloudFront（Origin Access Control、SPA fallback 到 `index.html`）；`terraform apply` 會連動 build 與部署 React（見 Project Usage）。`modules/api/` 已建立單一 Lambda（Python，`modules/api/lambda/handler.py`）+ API Gateway HTTP API，處理 `api_contract.md` 定義的 5 個讀取端點（`health`、`catalog`、`dashboard/overview`、`districts/{id}`、`analyses/{id}`），目前回傳的是 mock 資料；等 data-pipeline 把 analytics 寫進 DynamoDB 後，換掉 handler 裡的 `_build_*`/`_analysis_*` builder 即可，router／envelope 不用動。其餘服務（Data Pipeline、AI、Storage）尚未建立實際資源，未來以 `module "xxx" { source = "./modules/xxx" ... }` 的方式陸續加入同一個 root。CDK package、`cdk.json` 與 `bin/`、`lib/` 仍是 placeholder，未使用。

## Responsibilities

Frontend 與 API（mock data）資源已用 Terraform 建立。其餘規劃：

- Backend：DynamoDB permissions（API Gateway、Lambda 已建立，見上方）。
- Data Pipeline：Lambda、S3、EventBridge Scheduler、Step Functions。
- AI：Lambda、Amazon Bedrock permissions 與未來的 Knowledge Base / RAG resources。
- Storage：S3 與 DynamoDB。
- Monitoring：未來可加入 CloudWatch、Logs 與 Alarms。

## Project Usage

```bash
cd infrastructure
terraform init
terraform apply
```

`terraform apply` 除了建立/更新 S3、CloudFront、API Gateway、Lambda，也會執行 `npm run build`（於 `frontend/`）、`aws s3 sync` 上傳 `dist/` 到 bucket，並對 CloudFront 發送 cache invalidation；每次 apply 都會重新 build 並部署目前的前端原始碼。執行前需已設定好可用的 AWS credentials（`aws configure` 或環境變數）。

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
