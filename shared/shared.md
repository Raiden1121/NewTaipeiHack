# Shared

## Purpose

Shared 用來保存 Frontend、Backend 與 AI Service 共用的 TypeScript data types 與 contract，避免各模組使用不同欄位名稱或資料格式。

## 目前內容

| 檔案 | 狀態 | 內容 |
|---|---|---|
| `src/metrics.ts` | **已建立** | metric contract：`MetricValue`、`MetricStatus`、`YouthEligibility`、`PeriodType` |
| `src/aiContract.ts` | **提案** | AI Service 的 request / response contract：`AiEvidence`、`StructuredOutput`、`SourceAttribution` |
| `src/aiContextTable.ts` | **提案** | DynamoDB「AI Context」表的 key schema 與 item 形狀 |

其餘跨模組 DTO 仍依各 feature plan 擴充。

`aiContract.ts` 與 `aiContextTable.ts` 是 **ai-service 主動提出的提案，還沒定案**。
由 ai-service 先寫是因為那邊進度最快，等其他模組定案只會變成回頭改。
有意見直接改檔案並通知 ai-service，不要各自在自己的模組裡另立一套欄位名。

`aiContract.ts` 的權威實作在 `ai-service/src/types/`（那邊是 zod schema，會實際驗證）。
這裡是純 TypeScript 型別，刻意不依賴任何套件。兩邊不一致時以 ai-service 的 zod schema 為準。

`PeriodType` 與 `YouthEligibility` 的**單一定義在 `metrics.ts`**，`aiContract.ts` 從那裡
import。原本兩邊各自宣告了一份（值相同，因為都是照 pipeline 欄位 1:1 對過來的），
兩份併存會讓改其中一邊時另一邊靜默不動 —— 理由見 `src/index.ts` 的註解。

### 需要 data-pipeline 隊友注意的兩件事

1. **DB 的資料來源欄位建議拆成兩個**：`source`（機關／系統識別碼，用來查中文機關名稱）
   ＋ `sourceUrl`（能點進去的網址）。只有其中一個都不夠 —— 細節見
   `src/aiContextTable.ts` 的註解。
2. **複合指標必須帶 `computation`**，說明算法與母體大小，例如
   `"median of house_prices.price_per_ping, n=1832, period=11507"`。
   沒有它，AI 引用中位數時無法在「判斷依據」交代數字的來歷。

## 命名規則（已決定）

pipeline 的 snake_case 欄位一律 **1:1 對應成 camelCase**，不發明語意名稱：

| pipeline | shared / ai-service |
|---|---|
| `district_name` | `districtName` |
| `youth_eligibility` | `youthEligibility`（**不是** `ageQualifier`） |
| `metric_id` | `metricId` |
| `fetched_at` | `fetchedAt` |

snake_case ↔ camelCase 的轉換只發生在 `ai-service/src/context/` 一層。

## Responsibilities

未來可能包含：

- `District` 與 `DistrictMetrics`。
- `OpportunityIndex` 與 `RetentionRisk`。
- `YouthResource`、API Request / Response。
- `PolicyAdvice` 與 `AI Evidence`。

Metric source 欄位統一為 `source`、`sourceName`、`sourceUrl` 與 `sourceRefs`。單一來源使用前三個欄位；多來源衍生指標使用 `source: null`、`sourceUrl: null` 與 `sourceRefs`，不由 Frontend 自行查表。

共用格式應讓各模組對同一個欄位有一致理解，例如不要讓 Frontend 使用 `opportunityIndex`，Backend 卻回傳 `opportunity_score`。

## Project Usage

```text
frontend
backend
ai-service
    ↓
共用 Type Definition / Contract
```

## Inputs & Outputs

- 輸入：跨模組需要共享的資料結構與 API contract。
- 輸出：可被各 workspace package 引用的 TypeScript types。

## Boundaries

Shared 不是 AWS Service，不會獨立部署；不負責 business logic、資料庫、ETL、AI Prompt 或 API request 的執行。
