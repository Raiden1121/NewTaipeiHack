# Infrastructure

## Purpose

Infrastructure 使用 AWS CDK 管理本專案的 AWS Cloud Resources，以及各服務之間的部署與權限連接。

目前只有 CDK package、`cdk.json` 與 `bin/`、`lib/` placeholder，尚未建立實際 Stack 或 AWS resource。

## Responsibilities

規劃使用 AWS CDK 與 TypeScript 管理：

- Frontend：S3、CloudFront。
- Backend：API Gateway、Lambda、DynamoDB permissions。
- Data Pipeline：Lambda、S3、EventBridge Scheduler、Step Functions。
- AI：Lambda、Amazon Bedrock permissions 與未來的 Knowledge Base / RAG resources。
- Storage：S3 與 DynamoDB。
- Monitoring：未來可加入 CloudWatch、Logs 與 Alarms。

## Project Usage

Infrastructure 預計由 CDK 定義、預覽並部署 AWS 資源；實際指令與 Stack 尚未建立。

## Inputs & Outputs

- 輸入：各服務的部署設定、環境參數與資源依賴。
- 輸出：可部署的 AWS Cloud Resources、IAM permissions 與服務連接。

## Boundaries

Infrastructure 只負責 AWS 資源如何建立、連接與部署，不包含 Dashboard business logic、指標計算、React UI、AI Prompt 或 ETL logic。
