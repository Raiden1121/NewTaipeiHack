# AI API Contract — 青年參政頁（`/politics`）↔ Backend ↔ ai-service

本文件定義**青年參政頁面的 AI 語言模型回答**在三個模組之間的介面：前端送什麼、backend 組什麼、ai-service 回什麼、前端該怎麼渲染。

`api_contract.md` 負責的是 Read API（統計數字）；AI 回答不在那份契約裡（見該檔 §8.2）。這份就是補上那個洞。

> 本文件**不重新發明 ai-service 的形狀**。`AiRequestSchema` / `AiSuccessResponse` / `StructuredOutput` 已由程式碼定死，以下一律照抄並標明出處檔案。新定義的只有 Backend 對前端的那一層。

---

## 0. 範圍與邊界

| 模組 | 在 AI 回答這件事上負責 | 不負責 |
|---|---|---|
| `frontend` | 送出「哪一區、哪一塊」、渲染回傳的結構化結果與來源 | **組 evidence**、挑資料、判斷資料夠不夠 |
| `backend` | 從 published snapshot 組 `context.evidence`、代理呼叫 ai-service、套用 `{ data, meta }` envelope | prompt、模型參數、輸出驗證 |
| `ai-service` | prompt、Bedrock、輸出 schema 驗證、來源推導、預先算 | 統計指標計算、HTTP 對外授權 |
| `data-pipeline` | published snapshot（evidence 的唯一真值來源） | AI |

本次涵蓋的 action：**`explain`（各區塊 AI 解讀）** 與 **`policyCopilot`（頁面級政策建議）**。
`qa`（自由問答聊天框）屬 `/policy-support` 的 `PolicyDecisionAssistant`，**不在本次範圍**。

---

## 1. 兩層呼叫路徑

```text
Frontend                Backend                        ai-service (Lambda)
   │                       │                                  │
   │ POST /api/v1/assistant│                                  │
   │ { action, focusArea,  │                                  │
   │   focusDistrict }     │                                  │
   ├──────────────────────►│                                  │
   │                       │ 讀 published snapshot            │
   │                       │ buildAiContext() 組 evidence     │
   │                       │                                  │
   │                       │ POST { action, context }         │
   │                       ├─────────────────────────────────►│
   │                       │                                  │ 指紋比對預先算結果
   │                       │◄─────────────────────────────────┤ hit → 回現成的
   │                       │ AiSuccessResponse                │ miss → 即時算（50–58s）
   │◄──────────────────────┤                                  │
   │ { data, meta }        │                                  │
```

**前端永遠不直接打 ai-service。** 理由有二：(a) ai-service Lambda **目前完全沒有 authentication**（見 `src/handlers/lambda.ts` 的警告），直接暴露等於把 Bedrock 帳單開放給任何人；(b) `context.evidence` 必須跟 read API 來自**同一個 snapshot**，前端自己組必然會漂移。

---

## 2. Frontend → Backend（本文件新定義）

### 2.1 Endpoint

```text
POST /api/v1/assistant
Content-Type: application/json
```

### 2.2 Request

```jsonc
{
  "action": "explain",                    // "explain" | "policyCopilot"
  "focusArea": "participation_hotspot",   // 見 §6 的合法值表
  "focusDistrict": "板橋區"                // 中文區名；null = 全市
}
```

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `action` | `"explain" \| "policyCopilot"` | ✅ | 對應 `AI_ACTIONS`（`src/handlers/lambda.ts`）。本頁不使用 `qa`。 |
| `focusArea` | `string` | ✅ | 決定讀哪些 analytics artifact，見 §6。 |
| `focusDistrict` | `string \| null` | ✅ | 新北市 29 區中文名（對照表見 `api_contract.md` 附錄 A）。`null` 代表全市，語意與 `ParticipationKpiGrid` 未選取行政區時一致。 |

**前端不得傳的欄位**（傳了一律 `400`）：

- `evidence` / `webFindings` / `knownLimitations` — 這些是 backend 從 snapshot 組的。前端能塞 evidence 就等於能餵模型任意數字，來源可追溯性直接歸零。
- `question` — `explain` 與 `policyCopilot` 沒有使用者問題，`context.question` 固定 `null`。
- `webSearch` — 見 §2.3。

### 2.3 為什麼前端不能控制 `webSearch`

預先算的快取鍵是**輸入指紋**（`src/precompute/fingerprint.ts`），而 `webSearch.enabled` 與 `webSearch.scope` **都在雜湊裡**。前端每切一次開關就換一個指紋，等於保證 miss——而 miss 在這兩個 action 上代表逾時（見 §5）。

所以：`explain` / `policyCopilot` 的 `webSearch` 由 **backend 固定帶入，且必須與批次預先算時使用的設定完全相同**。前端這兩張卡不提供上網搜尋開關。

> ⚠️ `buildAiContext()` 的 `webSearch` **預設是開啟**（`enabled: true, contextSize: 'low', scope: 'all'`）。backend 與 `npm run precompute` 必須明確帶同一組值，不能一邊用預設一邊手寫——那會靜默地永遠 miss。建議把該組設定寫成單一常數，兩邊都引用它。

### 2.4 Response（成功）

沿用 Read API 的 `{ data, meta }` envelope（`api_contract.md` §1.2），`data` 就是 ai-service 的 `AiSuccessResponse` 原樣：

```jsonc
{
  "data": {
    "action": "explain",
    "generatedBy": "bedrock:apac.anthropic.claude-sonnet-4-6(ap-northeast-1)",
    "cache": "hit",
    "precomputedAt": "2026-09-13T02:11:40.512Z",
    "output": { /* StructuredOutput，見 §4 */ },
    "sources": [ /* SourceAttribution[]，見 §4.3 */ ]
  },
  "meta": {
    "api_version": "v1",
    "snapshot_id": "dev-full-youth-keyword-20260913",
    "generated_at": "2026-09-12T17:41:50.918015+00:00",
    "as_of": null,
    "warnings": []
  }
}
```

| `data` 欄位 | 型別 | 說明 |
|---|---|---|
| `action` | `"explain" \| "policyCopilot"` | 回聲，前端可用來對應是哪張卡 |
| `generatedBy` | `string` | `BedrockClient.description`，含模型 id 與 region。**Mock client 時這裡會寫明是 mock**——demo 當天忘了設環境變數，靠這個欄位才看得出畫面上是假分析 |
| `cache` | `"hit" \| "miss" \| "disabled" \| "bypass"` | 見 §5 |
| `precomputedAt` | `string \| null` | ISO 時間。**這是這份結果當初產生的時間，不是現在。** `cache != "hit"` 時為 `null` |
| `output` | `StructuredOutput` | §4 |
| `sources` | `SourceAttribution[]` | §4.3。**每個回應一定有這個欄位**；沒引用任何資料時是 `[]`，那種情況 `output.dataSufficiency` 必為 `insufficient` |

### 2.5 錯誤

沿用 `api_contract.md` §1.4 的錯誤形狀：

```json
{ "error": { "code": "AI_RESULT_NOT_READY", "message": "...", "details": [] }, "request_id": "..." }
```

| HTTP | code | 何時 | 前端該做什麼 |
|---|---|---|---|
| 400 | `INVALID_QUERY` | `action` / `focusArea` 不在允許值、`focusDistrict` 不是 29 區之一、送了禁止欄位 | 這是前端的 bug，修呼叫端 |
| 503 | `AI_RESULT_NOT_READY` | 預先算沒有這一組結果（見 §5） | 顯示「本區分析尚未產生」，**不要自動重試**——重試不會讓它變快 |
| 502 | `AI_UPSTREAM_ERROR` | ai-service 回 502：Bedrock 不可用、輸出驗證重試用盡、模型引用了不存在的 `evidenceId` | 顯示「AI 分析暫時無法使用」，可提供手動重試 |
| 503 | `SNAPSHOT_UNAVAILABLE` | snapshot 讀不到，evidence 無從組起 | 同整站的 snapshot 失效處理 |
| 500 | `INTERNAL_ERROR` | 其他 | — |

**「這一區這個主題沒有資料」不是錯誤。** 那是 `200` + `output.dataSufficiency = "insufficient"`，見 §4.2。回 4xx/5xx 會讓前端把一個正常且需要呈現的狀態畫成錯誤畫面。

---

## 3. Backend → ai-service（照抄現況）

### 3.1 Request

`src/handlers/lambda.ts` 的 `AiRequestSchema`，**不修改**：

```jsonc
{
  "action": "explain",
  "context": {
    "question": null,
    "focusDistrict": "板橋區",
    "focusArea": "participation_hotspot",
    "evidence": [ /* AiEvidence[]，見 src/types/aiEvidence.ts */ ],
    "knownLimitations": ["..."],
    "webFindings": [],
    "webSearch": { "enabled": true, "contextSize": "low", "scope": "all" }
  }
}
```

### 3.2 Backend 組 context 的責任

backend 呼叫 `buildAiContext(repository, options)`（`src/context/buildContext.ts`），前端欄位對應如下：

| 前端送的 | → `BuildAiContextOptions` | 備註 |
|---|---|---|
| `focusDistrict` | `focusDistrict` | 非 null 時 `buildAiContext` 會自動加上 `districtNames: [focusDistrict]` 篩選 |
| `focusArea` | `focusArea` | 決定讀哪些 analytics artifact（§6） |
| — | `question: null` | 這兩個 action 沒有使用者問題 |
| — | `webSearch` | §2.3 的固定值 |
| — | `comparisonMetrics` | **不傳**。那是 Q&A 用來回答排名問題的；dashboard 卡片沒有使用者問題，不需要 |
| — | `focusMetricIds` | **不傳**。它從 `question` 推導，這裡 `question` 是 null，推導必然落空 |

`knownLimitations` 由 context builder 產生（取樣筆數、`context_only` 標記等），**backend 不得自行編寫或刪改**——它們會原封不動出現在 `output.limitations`，是誠實性的一部分。

### 3.3 ai-service 的錯誤 → backend 的錯誤

| ai-service | backend 對前端 |
|---|---|
| `400`（zod 驗證失敗） | `500 INTERNAL_ERROR` — 前端沒碰 context，驗證失敗是 backend 組錯了，不該讓前端以為是自己傳錯 |
| `502` | `502 AI_UPSTREAM_ERROR` |
| 逾時 | `503 AI_RESULT_NOT_READY` |

---

## 4. `StructuredOutput` → UI 對照

來源：`src/types/structuredOutput.ts`。欄位順序有意義（模型依序生成），前端渲染順序可自訂，但**不可省略任何一項的呈現責任**。

### 4.1 八個欄位

| 欄位 | 型別 | `/politics` 怎麼渲染 |
|---|---|---|
| `evidenceReview` | `{ availableMetrics[], youthSpecificMetrics[], contextOnlyMetrics[], missingForQuestion[] }` | **預設收起**，放在「查看依據」展開區。前三個陣列由**程式**盤點（模型碰不到），`missingForQuestion` 是模型判斷的 |
| `dataSufficiency` | `"sufficient" \| "partial" \| "insufficient"` | 決定整張卡的呈現模式，見 §4.2。**不要自己去讀 `limitations` 的中文猜有沒有資料** |
| `answer` | `string \| null` | 這兩個 action **固定 `null`**。前端不渲染 |
| `issues` | `string[]` | 「問題辨識」條列 |
| `strengths` | `string[]` | 「發展優勢」條列 |
| `resourceGaps` | `string[]` | 「資源缺口」條列 |
| `policyDirections` | `string[]` | 「政策方向」條列 |
| `basis` | `{ evidenceId, note }[]` | 「判斷依據」。**必須與 `webReferences` 分開顯示** |
| `webReferences` | `{ findingId, note }[]` | 「網路補充資料」，需標示「未經驗證」 |
| `limitations` | `string[]` | 「資料限制」。**永遠要顯示，即使是空陣列也要保留區塊** |
| `disclaimer` | `string` | 卡片底部。schema 強制包含「不代表政府正式政策決定」 |

四塊結論（`issues` / `strengths` / `resourceGaps` / `policyDirections`）**允許空陣列**——某個面向真的沒有發現。前端要能渲染「本次沒有」，不要因為陣列空就崩或畫成載入中。

### 4.2 `dataSufficiency` 三態 → 三種畫面

| 值 | 意思 | 畫面 |
|---|---|---|
| `sufficient` | evidence 足以回答，結論有依據 | 正常渲染四塊 + 依據 |
| `partial` | 部分面向有資料、部分缺漏 | 正常渲染，但**必須在卡片顯眼處標示「部分資料缺漏」**，並把 `limitations` 從收起改成展開 |
| `insufficient` | 沒有足夠 evidence | **四塊保證為空**（schema 強制）。畫「目前資料不足，無法產生分析」，並列出 `evidenceReview.missingForQuestion`。**不要把空陣列渲染成空白卡片** |

schema 層已保證的不變式，前端可以依賴、不必自己再驗：

- `insufficient` 時四塊必為空，且 `missingForQuestion` 必非空
- 有任何結論時，`basis` 或 `webReferences` 至少一筆非空（不可能有無依據的結論）
- `webReferences` 非空時，`dataSufficiency` 不可能是 `sufficient`，且 `limitations` 必有一條提到網路
- `basis` 空但 `webReferences` 非空（純網路回答）時，`limitations` 必有一條說明沒有官方統計支撐

### 4.3 `sources[]` 的渲染規則

來源：`src/types/sourceAttribution.ts`。

**這個陣列是程式從實際被 `basis` 引用的 evidence 推導的，模型碰不到**，所以不會有捏造的機關名稱或網址。

| 欄位 | 渲染 |
|---|---|
| `organization` | 中文機關名，主要顯示文字 |
| `datasetLabel` | 中文資料集名稱 |
| `url` | 資料集官方頁面。`null` 時**不要放假連結**，只顯示機關名 |
| `recordUrls[]` | 逐筆層級網址（預算書 PDF 等） |
| `kind` | `dataset` / `document` / `web`——`web` 必須視覺上與另外兩者可區分 |
| `fetchedAt` | 「資料抓取於 X」 |
| `citedEvidenceIds[]` / `sourcePaths[]` | 收在展開區，給查證用 |

> 🔴 **禁止**：從 `output` 的中文句子裡剖析機關名稱或網址來組來源清單。那正是這個欄位存在的原因——模型寫的中文裡出現的名稱沒有經過任何驗證，`sources[]` 有。

### 4.4 `cache` / `precomputedAt` 必須顯示

`cache === "hit"` 時，卡片上**必須**顯示 `precomputedAt`（例如「分析產生於 2026-09-13 10:11」）。

使用者看到的可能是幾小時前算的內容。不講就等於暗示它是剛剛依當前資料算出來的——那對拿它做政策判斷的人是誤導。

---

## 5. 延遲、30 秒上限與預先算

**這是這兩個 action 最重要的限制，不是效能優化問題。**

- 實測 `explain` 約 **50 秒**、`policyCopilot` 約 **58 秒**（Sonnet 4-6）
- API Gateway HTTP API 的整合逾時**固定 30 秒，不可調**（見 `ai-service/DEPLOYMENT.md`）

結論：**即時算一定超時。** 這兩張卡的正式路徑只有「讀預先算好的結果」一條。

### 5.1 `cache` 四個值的意思

| 值 | 意思 | backend 行為 |
|---|---|---|
| `hit` | 命中預先算的結果 | `200`，正常回傳 |
| `miss` | 指紋沒命中，走了即時算 | 正式環境下這代表**已經逾時**了 → `503 AI_RESULT_NOT_READY` |
| `disabled` | 沒設 `AI_PRECOMPUTE_DIR`，快取層關閉 | 同 `miss` |
| `bypass` | 這個 action 不可預先算（只有 `qa`） | 本頁不會出現 |

### 5.2 為什麼 miss 要回 503 而不是等

等一個注定在 30 秒被 API Gateway 砍掉的請求，使用者付出 30 秒等待換一個逾時錯誤。直接回 `503 AI_RESULT_NOT_READY` 至少是即時且誠實的。

### 5.3 指紋為什麼會 miss

快取鍵是輸入內容的 sha256（`src/precompute/fingerprint.ts`），納入雜湊的有：`action`、`focusDistrict`、`focusArea`、每筆 evidence 的 `evidenceId` + `value` + `unit`、`knownLimitations`、`webSearch.enabled` + `scope`。

所以以下任一情況都會 miss，且都是**正確行為**（寧可 miss，不要回用別的資料算出來的答案）：

- data-pipeline 重新發布 snapshot，指標值變了 → **必須重跑批次**
- backend 改了組 evidence 的方式（篩選條件、`limitPerDataset`）→ 必須重跑批次
- `webSearch` 設定與批次不同 → 見 §2.3

### 5.4 批次怎麼跑

```bash
# ai-service/
npm run precompute -- --dry --all --areas=participation_hotspot,participation_kpi,participation_resource,participation_voice
npm run precompute -- --all --areas=participation_hotspot,participation_kpi,participation_resource,participation_voice --actions=explain
npm run precompute -- --districts=  --areas=participation --actions=policyCopilot   # 全市層級
```

需要的組數：`explain` 4 個區塊 × 30（29 區 + 全市）＝ **120 組**，加 `policyCopilot` 30 組，共 **150 組**。以每組約 55 秒估，`--concurrency=3` 下約 **46 分鐘**，並產生對應的 Bedrock 費用。**先用 `--dry` 確認組數再跑。**

> ⚠️ 現階段先跑 `participation_hotspot` / `participation_kpi` / `participation_resource` 三個（90 組，約 28 分鐘）。`participation_voice` 要等 `api_contract.md` §6.4 的文字雲期間語意定案，理由見 §6.2。

---

## 6. 青年參政頁的四張 AI 解讀卡

`/politics` 目前四個區塊（見 `frontend/src/features/politics/PoliticsPage.tsx`）各配一張 `explain` 卡，頁面另有一張 `policyCopilot`。

### 6.1 `focusArea` 合法值與 analytics 範圍

| 卡片 | 對應區塊 | `focusArea` | 讀哪些 analytics artifact |
|---|---|---|---|
| 參政熱點解讀 | `ParticipationHotspotMap` + `ParticipationHotspotList` | `participation_hotspot` | `dashboard_overview`, `participation` |
| 三大 KPI 解讀 | `ParticipationKpiGrid` | `participation_kpi` | `dashboard_overview`, `participation` |
| 資源投入產出解讀 | `ResourceIoCharts` | `participation_resource` | `dashboard_overview`, `participation`, `policy_support` |
| 青年聲音解讀 | `YouthTopicWordCloud` | `participation_voice` | `keyword_frequency`, `topic_weight` |
| 頁面級政策建議 | 整頁 | `participation`（既有值，不動） | `dashboard_overview`, `participation`, `topic_weight`, `keyword_frequency` |

**為什麼要細分而不是全頁共用一張 `explain`**：預先算的鍵是 `(action, focusDistrict, focusArea)` 的指紋，**沒有「區塊」這個維度**。不細分的話四張卡會拿到同一份文字。而且文字雲那張卡的解讀不該去讀預算數字——`participation_voice` 只讀 `keyword_frequency`，模型就不可能拿預算執行率去解釋青年關注議題。

> ⚠️ **未實作（ai-service 待辦）**：`ANALYTICS_ARTIFACTS_BY_FOCUS_AREA`（`src/context/analyticsSnapshotRepository.ts:145`）目前只有 `participation` 一個值，上表的四個細分值**尚未加入**。在加入之前，送這些值會落到 `selectArtifacts()` 的「沒有對應設定」分支：讀取**全部** analytics 並在 `knownLimitations` 留一條 note——結果會是「能跑但很慢很貴、而且四張卡看的資料一樣」。

### 6.2 各卡的資料語意提醒

這些是 `api_contract.md` §6 已經寫明、但模型只看得到 evidence 的數字，所以**必須靠 `knownLimitations` 傳達**的語意：

| 卡片 | 必須讓模型知道的事 |
|---|---|
| 參政熱點 | `youthCandidacyRatePer100k` 是**青年里長候選人數 ÷ 青年人口 × 100,000**，單位 `per_100k_youth`，**不是 0–100 指數**，也不是市議員參選率；只有 111 年一屆為 `observed`，實際值域 0–64.68、中位數 6.27 |
| 三大 KPI | `youthBoroughChiefRatioPercent`（席次占比）、`yrr`（代表性比值，`proxy: true`）、`youthCandidacyRatePer100k`（參選密度）**三者語意不同，不可互相代換**；服務涵蓋率是 `partial`，29 區中位數為 0，來自只有 9 個據點的 `youth_service_points` |
| 資源投入產出 | `budget_by_department` 是**民國 116 年預算案**；執行率取最新可得年度並標示年份；`budgetTrend` 只有 112–114 有值 |
| 青年聲音 | `weight` 是標準化後的字級（1–5），**不是原始頻次**，不可拿來比較絕對熱度；資料涵蓋期間必須讓模型知道，否則它會把累計值講成「今年的熱度」 |

> 🔴 **青年聲音這張卡目前無法定案**：`api_contract.md` §6.4 的文字雲來源在本次對話進行中被改動過，工作目錄版本與 HEAD 版本互相矛盾——
> - HEAD 版：canonical 是 `youth-keyword-frequency`，`period_scope: "all_available"`（全期間累計），欄位是 `keywords[].term`
> - 目前工作目錄版：用 `youth_topic_weight`（22 個固定議題詞），backend 固定取 `year_roc = 114`（單一年度），欄位是 `topics[].label`
>
> 兩者的**期間語意完全相反**（全期間累計 vs 單一年度）。在 §6.4 定案之前，`participation_voice` 這張卡的 `knownLimitations` 無法寫對，**不要先跑它的預先算批次**——寫錯期間語意的解讀會比沒有解讀更糟。另外三張卡不受影響。

> 這些語意由 data-pipeline 的 `computation` 欄位與 context builder 的 `knownLimitations` 傳達。**backend 不得在 prompt 層另外手寫**——手寫的說明不會跟著資料更新走。

---

## 7. 現況 Checklist

### ✅ 已存在，可直接依賴

- [x] ai-service 的 `AiRequestSchema` / `AiSuccessResponse` / `StructuredOutput`（`src/handlers/lambda.ts`、`src/types/structuredOutput.ts`）
- [x] 輸出不變式驗證（結論必須有依據、資料不足不可給結論、網路來源必須標示）
- [x] `sources[]` 由程式推導，不可被模型捏造（`src/types/sourceAttribution.ts`）
- [x] 「資料不足」回合法輸出而非錯誤（`src/handlers/insufficientData.ts`）
- [x] 預先算機制與批次腳本（`src/precompute/`、`npm run precompute`）
- [x] `participation` focusArea 的 analytics 對應（`analyticsSnapshotRepository.ts:155`）

### ⚠️ 待實作

| 項目 | 負責 | 說明 |
|---|---|---|
| `POST /api/v1/assistant` route | backend | §2。目前 backend **完全沒有這個 route** |
| 四個細分 `focusArea` | ai-service | §6.1。`ANALYTICS_ARTIFACTS_BY_FOCUS_AREA` 加四個 key |
| `webSearch` 固定設定常數 | ai-service + backend | §2.3。兩邊必須引用同一個常數，否則永遠 miss |
| 四張 AI 卡的前端元件 | frontend | `PoliticsPage.tsx` 目前四個區塊**都沒有任何 AI 區塊** |
| 150 組預先算批次 | ai-service | §5.4。約 46 分鐘 + Bedrock 費用 |
| Lambda 授權 | infra + backend | `lambda.ts` 目前**無任何 authentication**。backend 代理是第一層防護，但 Lambda 本身仍需 IAM／API key |

### ❌ 本次不做

- `qa`（自由問答）在 `/politics`。聊天框維持只在 `/policy-support`，見 `api_contract.md` §8.2
- 前端的上網搜尋開關。理由見 §2.3
- miss 時的非同步排隊／輪詢。現階段 miss 直接回 `503`，見 §5.2

---

## 8. 已知風險

1. **snapshot 一更新，150 組預先算全部失效。** 指紋含 evidence 的 `value`，這是刻意的（見 §5.3），但代表 data-pipeline 每次重新發布都要重跑批次約 46 分鐘。Demo 前的發布時程要把這段算進去。
2. **`AI_PRECOMPUTE_WRITE_THROUGH=1` 不要在正式環境開。** 開了之後「第一個打進來的使用者」會決定所有人之後看到的卡片內容，包含模型那次剛好答得差的版本，而且沒有人會知道。
3. **`api_contract.md` §6.4 文字雲來源尚未定案**（見 §6.2 的紅字）。工作目錄版與 HEAD 版對「全期間累計 vs 單一年度 114」的說法相反，`participation_voice` 卡在定案前不應產生預先算結果。
4. **細分 `focusArea` 未實作前的靜默退化。** 送 `participation_voice` 給現在的 ai-service 不會報錯，它會讀取全部 analytics——能跑，但慢、貴、而且四張卡內容雷同。這種失敗不會有錯誤訊息，只會在 `knownLimitations` 留一條 note。
