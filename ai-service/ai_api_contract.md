# AI API Contract — 青年參政頁（`/politics`）↔ Backend ↔ ai-service

本文件定義**青年參政頁面的 AI 語言模型回答**在三個模組之間的介面：前端送什麼、backend 組什麼、ai-service 回什麼、前端該怎麼渲染。

`api_contract.md` 負責的是 Read API（統計數字）；AI 回答不在那份契約裡（見該檔 §8.2）。這份就是補上那個洞。

> **契約狀態（2026-09-13）：** 公開同步查詢已改為既有 Python API Lambda 的
> `POST /api/v1/ai/query`；API 只接受 `action`、`question`、`focusDistrict`、
> `focusArea`、`period`、`webSearch`，不接受 `context`、`evidence` 或 `webFindings`。
> AI Service 線上自行從 DynamoDB 讀 evidence，帶 `context` 的形狀只供本機與測試。
> 本文件以下的 `/api/v1/assistant` 與 backend 組 `context` 內容是舊版頁面整合草稿，
> 不可作為目前公開 endpoint 的實作依據；目前契約請以 `shared/src/aiContract.ts`、
> `backend/backend.md` 與 `ai-service/DEPLOYMENT.md` §1.5 為準。

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
| `focusDistrict` | `string \| null` | ✅ | 新北市 29 區中文名（對照表見 `api_contract.md` 附錄 A）。`null` 代表全市，語意與 `ParticipationKpiGrid` 未選取行政區時一致。⚠️ **全市目前一定拿不到預先算結果**（批次腳本不支援，見 §5.4），也就是說「使用者剛進頁面、還沒點行政區」這個預設狀態會直接得到 `503 AI_RESULT_NOT_READY`。前端要嘛接受那個狀態的空卡片，要嘛在 `runBatch` 支援全市之前不要在未選取時發請求。 |

**前端不得傳的欄位**（傳了一律 `400`）：

- `evidence` / `webFindings` / `knownLimitations` — 這些是 backend 從 snapshot 組的。前端能塞 evidence 就等於能餵模型任意數字，來源可追溯性直接歸零。
- `question` — `explain` 與 `policyCopilot` 沒有使用者問題，`context.question` 固定 `null`。
- `webSearch` — 見 §2.3。

### 2.3 為什麼前端不能控制 `webSearch`

預先算的快取鍵是**輸入指紋**（`src/precompute/fingerprint.ts`），而 `webSearch.enabled` 與 `webSearch.scope` **都在雜湊裡**。前端每切一次開關就換一個指紋，等於保證 miss——而 miss 在這兩個 action 上代表逾時（見 §5）。

所以：`explain` / `policyCopilot` 的 `webSearch` 由 **backend 固定帶入，且必須與批次預先算時使用的設定完全相同**。前端這兩張卡不提供上網搜尋開關。

> ⚠️ **兩層的預設值是相反的，這是最容易踩的坑。**
>
> - `AiRequestContextSchema.webSearch` 的 default 是 `{ enabled: false, contextSize: 'low' }`（`scope` 由 `WebSearchSettingsSchema` 補 `'all'`）——**backend 不傳 `webSearch` 給 lambda，就是關閉。**
> - `buildAiContext()` 的 `webSearch` default 是 `{ enabled: true, contextSize: 'low', scope: defaultWebSearchScope() }`——**批次腳本不傳，就是開啟。**
>
> 所以「兩邊都不傳」不是安全做法，而是保證 `webSearchEnabled` 一個 true 一個 false → 指紋永遠不同 → 永遠 miss。
>
> 另外 `scope` 的預設還會被伺服器端的 `WEB_SEARCH_SCOPE` 環境變數影響（`trusted` / 其他值都當 `all`），所以跑批次的機器與跑 backend 的機器**環境變數也必須一致**。
>
> 結論：把 `{ enabled, contextSize, scope }` 寫成單一常數，backend 與 `npm run precompute` 兩邊都明確帶入、都引用它，不要依賴任何一層的預設。

### 2.4 Response（成功）

沿用 Read API 的 `{ data, meta }` envelope（`api_contract.md` §1.2），`data` 就是 ai-service 的 `AiSuccessResponse` 原樣：

```jsonc
{
  "data": {
    "action": "explain",
    "generatedBy": "bedrock(apac.anthropic.claude-sonnet-4-6, ap-northeast-1, auth=bearer)",
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
| `generatedBy` | `string` | `BedrockClient.description`。實際格式是 `bedrock({modelId}, {region}, auth={sigv4\|bearer})`，mock 是 `mock(no network)`（`src/bedrock/client.ts`）。**Mock client 時這裡會寫明是 mock**——demo 當天忘了設環境變數，靠這個欄位才看得出畫面上是假分析。前端**只當它是一段給人看的字串**，不要剖析模型 id 或 region（格式沒有契約保證）|
| `cache` | `"hit" \| "miss" \| "disabled" \| "bypass"` | 見 §5 |
| `precomputedAt` | `string \| null` | ISO 時間。**這是這份結果當初產生的時間，不是現在。** `cache != "hit"` 時為 `null` |
| `output` | `StructuredOutput` | §4 |
| `sources` | `SourceAttribution[]` | §4.3。**每個回應一定有這個欄位**；沒引用任何資料時是 `[]`。⚠️ **`[]` 不代表資料不足**——「四塊全空 + `dataSufficiency: "partial"` + `limitations` 非空」也是合法輸出（schema 只要求「有結論才要有引用」），那時 `sources` 同樣是 `[]`。要不要畫「資料不足」一律看 `dataSufficiency`，見 §4.2 |

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

### 4.1 十一個欄位

| 欄位 | 型別 | `/politics` 怎麼渲染 |
|---|---|---|
| `evidenceReview` | `{ availableMetrics[], youthSpecificMetrics[], contextOnlyMetrics[], missingForQuestion[] }` | **預設收起**，放在「查看依據」展開區。前三個陣列由**程式**盤點（模型碰不到），`missingForQuestion` 是模型判斷的 |
| `dataSufficiency` | `"sufficient" \| "partial" \| "insufficient"` | 決定整張卡的呈現模式，見 §4.2。**不要自己去讀 `limitations` 的中文猜有沒有資料** |
| `answer` | `string \| null` | 這兩個 action **約定為 `null`**，前端不渲染。⚠️ 這是約定不是 schema 保證：六塊 schema 的 `answer` 只有 `.nullable().default(null)`，沒有任何 refine 擋住 explain / policyCopilot 回非 null。前端遇到非 null 時忽略即可，不要當成錯誤 |
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

**現在真的跑得起來的只有既有的 `participation` 主題**（§6.1 的四個細分值還沒實作）：

```bash
# ai-service/
npm run precompute -- --dry --all --areas=participation --actions=explain,policyCopilot
npm run precompute -- --all --areas=participation --actions=explain,policyCopilot --concurrency=3
```

`src/precompute/runBatch.ts` 有兩個限制會直接影響上面的指令怎麼寫：

1. **未實作的 `focusArea` 會被硬性擋掉，`--dry` 也一樣。** areas 驗證排在 dry-run 分支**之前**，所以送 `participation_hotspot` 之類的值會印「主題 … 沒有對應的 analytics 範圍設定」然後 `exit 1`——連「先用 `--dry` 估組數」都做不到。
   這跟 lambda 路徑**行為不同**：lambda 收到未知 `focusArea` 會落到 `selectArtifacts()` 的寬鬆分支（讀全部 analytics ＋ 留一條 note，見 §6.1），批次腳本則是直接拒絕。
2. **不支援全市（`focusDistrict: null`）。** job 展開是 `for district of districts` 的三層迴圈，`focusDistrict` 永遠是字串；`--districts=` 傳空值會被 `parseList()` 當成「沒給」，於是落到「要指定 `--districts=…` 或 `--all`」而 `exit 1`。
   也就是說**全市層級的卡片目前無法預先算**，正式路徑上它只會是 `miss` → `503 AI_RESULT_NOT_READY`（§5.1）。要支援得先在 `runBatch` 加一個全市模式。

組數（假設四個細分 `focusArea` 已加入、全市仍不支援）：`explain` 29 區 × 4 個區塊 ＝ **116 組**，加 `policyCopilot` 29 組，共 **145 組**。以每組約 55 秒、`--concurrency=3` 估約 **45 分鐘**，並產生對應的 Bedrock 費用。**先用 `--dry` 確認組數再跑。**

> ⚠️ 現階段先跑 `participation_hotspot` / `participation_kpi` / `participation_resource` 三個（87 組，約 27 分鐘）。`participation_voice` 兩個理由都還不能跑：`api_contract.md` §6.4 的文字雲期間語意未定案，而且 `weight` 的單位標註目前是錯的，見 §6.2。

---

## 6. 青年參政頁的四張 AI 解讀卡

`/politics`（`frontend/src/features/politics/PoliticsPage.tsx`）目前是 3 個 `Section`、5 個資料元件：`ParticipationHotspotMap` ＋ `ParticipationHotspotList` ＋ `ParticipationKpiGrid`（同一個 Section）、`ResourceIoCharts`、`YouthTopicWordCloud`。下表把它們歸成**四個解讀單位**，各配一張 `explain` 卡，頁面另有一張 `policyCopilot`。

### 6.1 `focusArea` 合法值與 analytics 範圍

| 卡片 | 對應區塊 | `focusArea` | 讀哪些 analytics artifact |
|---|---|---|---|
| 參政熱點解讀 | `ParticipationHotspotMap` + `ParticipationHotspotList` | `participation_hotspot` | `dashboard_overview`, `participation` |
| 三大 KPI 解讀 | `ParticipationKpiGrid` | `participation_kpi` | `dashboard_overview`, `participation` |
| 資源投入產出解讀 | `ResourceIoCharts` | `participation_resource` | `dashboard_overview`, `participation`, `policy_support` |
| 青年聲音解讀 | `YouthTopicWordCloud` | `participation_voice` | `keyword_frequency`, `topic_weight` |
| 頁面級政策建議 | 整頁 | `participation`（既有值，不動） | `dashboard_overview`, `participation`, `topic_weight`, `keyword_frequency` |

**為什麼要細分而不是全頁共用一張 `explain`**：預先算的鍵是 `(action, focusDistrict, focusArea)` 的指紋，**沒有「區塊」這個維度**。不細分的話四張卡會拿到同一份文字。而且文字雲那張卡的解讀不該去讀預算數字——`participation_voice` 只讀 `keyword_frequency`，模型就不可能拿預算執行率去解釋青年關注議題。

> ⚠️ **未實作（ai-service 待辦）**：`ANALYTICS_ARTIFACTS_BY_FOCUS_AREA`（`src/context/analyticsSnapshotRepository.ts:145`）現在有 11 個 key（`employment` / `jobs` / `talent` / `housing` / `transport` / `population` / `retention` / `fertility` / `resources` / `participation` / `policy`），但**參政系列只有 `participation` 一個**，上表的四個細分值尚未加入。
>
> 加入之前，兩條路徑的行為**不一樣**，不要混用：
> - **經 lambda**：落到 `selectArtifacts()` 的「沒有對應設定」分支——讀取**全部** analytics 並在 `knownLimitations` 留一條 note。能跑，但很慢很貴，而且四張卡看的資料一樣。
> - **經批次腳本**：`runBatch.ts` 直接 `exit 1`，見 §5.4。
>
> 加 key 時順便注意：現有的 `resources` 與 `participation` 的 artifact 清單**完全相同**（`dashboard_overview` / `participation` / `topic_weight` / `keyword_frequency`），細分之後要決定 `resources` 跟著改還是維持原樣。

### 6.2 各卡的資料語意提醒

這些是 `api_contract.md` §6 已經寫明、但模型只看得到 evidence 的數字，所以必須由 ai-service 主動傳達的語意。

**先講清楚傳達管道，因為這件事很容易指錯地方：`knownLimitations` 不負責這個。** `buildAiContext()` 產生的 `knownLimitations` 只有四類內容——repository 的 notes（取樣截斷、缺 artifact、快照 warnings）、跨區比較 note、指標收斂 note、以及「本次沒有任何 evidence」。**沒有任何路徑會產生「某個指標的口徑是什麼」這種說明。**

真正傳達指標語意的是三個地方：

| 管道 | 內容 | 在哪 |
|---|---|---|
| evidence 的 `unit` / `youthEligibility` / `ageScope` | 單位與青年適用性。analytics 快照**沒有**這三個欄位（實測 8 個 artifact 全部沒有），所以那張手寫表是唯一來源 | `ANALYTICS_METRIC_META`（`src/context/analyticsRecord.ts:423`）；查不到時走 `inferMeta()` 的名稱猜測 |
| prompt 的「指標算法」段 | 複合指標的公式、正規化、口徑陷阱（`caveat`） | `METRIC_DEFINITIONS`（`src/context/metricDefinitions.ts`），只印這批 evidence 真的用到的指標 |
| evidence 的 `computation` | 這個數字來自哪個 analytics 路徑、哪個快照、哪些上游 dataset | `analyticsRecord.ts` 的 computation 組裝 |

所以要讓下表的語意真的到得了模型，該補的是 `ANALYTICS_METRIC_META` 與 `METRIC_DEFINITIONS`。

| 卡片 | 必須讓模型知道的事 | 實作現況 |
|---|---|---|
| 參政熱點 | `youthCandidacyRatePer100k` 是**青年里長候選人數 ÷ 青年人口 × 100,000**，單位 `per_100k_youth`，**不是 0–100 指數**，也不是市議員參選率；只有 111 年一屆為 `observed`，實際值域 0–64.68、中位數 6.27 | ❌ **沒傳到。** 這個 metricId 不在 `ANALYTICS_METRIC_META`，`inferMeta()` 只因名字含 `youth` 標成 `{ unit: null, youthEligibility: 'eligible' }`——**單位是 `null`**。也不在 `METRIC_DEFINITIONS`。更麻煩的是 deprecated alias `youthParticipationIndex`（同值、名字帶 Index）**同時**進 context 且同樣沒有單位，模型很容易把它讀成指數 |
| 三大 KPI | `youthBoroughChiefRatioPercent`（席次占比）、`yrr`（代表性比值，`proxy: true`）、`youthCandidacyRatePer100k`（參選密度）**三者語意不同，不可互相代換**；服務涵蓋率是 `partial`，29 區中位數為 0，來自只有 9 個據點的 `youth_service_points` | ❌ 部分沒傳到。`youthBoroughChiefRatioPercent` 不在 meta 表（unit `null`，應為 `%`）；`yrr` 也不在 meta 表，因名字不含 `youth` 被 `inferMeta()` 保守標成 `context_only`（一個青年代表性指標被標成「不可當青年數據解讀」）——但 `METRIC_DEFINITIONS.yrr` 有公式與 caveat，這半邊是通的。`proxy` / `denominator_type` 有沒有進 evidence 沒有保證。`serviceCoverageRate` 的 meta（`%`、`eligible`）與 formula 都有，但「只有 9 個據點、29 區中位數 0」屬資料品質事實，只能靠快照 warnings 進 notes，實作沒有保證會出現 |
| 資源投入產出 | `budget_by_department` 是**民國 116 年預算案**；執行率取最新可得年度並標示年份；`budgetTrend` 只有 112–114 有值 | ⚠️ 年度只靠 evidence 的 `period` 與 `computation` 表達，沒有額外標註。年度是 data-pipeline 決定的，ai-service 只照抄 |
| 青年聲音 | `weight` 是標準化後的字級（1–5），**不是原始頻次**，不可拿來比較絕對熱度；資料涵蓋期間必須讓模型知道，否則它會把累計值講成「今年的熱度」 | 🔴 **實作標錯，比沒標更糟。** `ANALYTICS_METRIC_META.weight` 是 `{ unit: '權重(0-1)' }`（`analyticsRecord.ts:598`），而現行快照 `dev-full-youth-keyword-20260913` 的 `keyword_frequency.keywords[].weight` 與 `topic_weight` 的 `topics[].weight` 實際值都是 **1–5 的整數**。模型會拿到「weight=5，單位 權重(0-1)」。另外 meta 表的 key 是**葉欄位名**，兩個 artifact 共用 `weight`，現在無法分別標註 |

> 🔴 **青年聲音這張卡目前無法定案**：`api_contract.md` §6.4 的文字雲來源在本次對話進行中被改動過，工作目錄版本與 HEAD 版本互相矛盾——
> - HEAD 版：canonical 是 `youth-keyword-frequency`，`period_scope: "all_available"`（全期間累計），欄位是 `keywords[].term`
> - 目前工作目錄版：用 `youth_topic_weight`（22 個固定議題詞），backend 固定取 `year_roc = 114`（單一年度），欄位是 `topics[].label`
>
> 兩者的**期間語意完全相反**（全期間累計 vs 單一年度）。在 §6.4 定案之前，這張卡要餵給模型的期間語意無法確定該怎麼寫（不論是寫進 `ANALYTICS_METRIC_META` 的單位、`METRIC_DEFINITIONS` 的 caveat，還是靠 artifact 自己的 `period_scope`），**所以不要先跑它的預先算批次**——寫錯期間語意的解讀會比沒有解讀更糟。另外三張卡不受影響。
>
> 一個線索：現行快照的 `keyword_frequency` 帶的是 `period_scope: "all_available"`，也就是 HEAD 那個版本的語意。

> 這些語意由 `ANALYTICS_METRIC_META`、`METRIC_DEFINITIONS` 與 evidence 的 `computation` 傳達（見上面的管道表）。**backend 不得在 prompt 層另外手寫**——手寫的說明不會跟著資料更新走，而且 backend 只送 context，本來就碰不到 prompt。
>
> 稽核方式：`npm run dev:metric-audit` 會比對 `ANALYTICS_METRIC_META` 對現行快照的覆蓋率。上表那幾個 ❌ 正是這支腳本要抓的東西——那張表是手寫的，快照一長出新指標它就會默默過期。

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
| `POST /api/v1/assistant` route | backend | §2。目前 backend **完全沒有這個 route**（`backend/` 下沒有任何 `assistant` 字樣）|
| 四個細分 `focusArea` | ai-service | §6.1。`ANALYTICS_ARTIFACTS_BY_FOCUS_AREA` 加四個 key，並決定 `resources` 要不要跟著調整 |
| `weight` 的單位修正 | ai-service | §6.2。`ANALYTICS_METRIC_META.weight` 現在標 `權重(0-1)`，實際值是 1–5。**這條擋住 `participation_voice` 卡，而且與 §6.4 的期間爭議無關，可以先修** |
| 參政指標補進 `ANALYTICS_METRIC_META` | ai-service | §6.2。`youthCandidacyRatePer100k`、`youthBoroughChiefRatioPercent`、`yrr` 三個都缺，單位全是 `null` |
| deprecated alias `youthParticipationIndex` | ai-service | §6.2。與 `youthCandidacyRatePer100k` 同值卻名字帶 Index，建議在 flatten 層擋掉，否則模型會把參選密度讀成指數 |
| `webSearch` 固定設定常數 | ai-service + backend | §2.3。兩層預設相反（request schema 關、context builder 開），兩邊必須引用同一個常數並對齊 `WEB_SEARCH_SCOPE`，否則永遠 miss |
| 四張 AI 卡的前端元件 | frontend | `PoliticsPage.tsx` 目前 3 個 Section／5 個資料元件，**沒有任何 AI 區塊** |
| `runBatch` 的全市模式 | ai-service | §5.4。目前無法產生 `focusDistrict: null` 的預先算結果，全市卡片一定 `miss` |
| 145 組預先算批次 | ai-service | §5.4。約 45 分鐘 + Bedrock 費用（不含全市） |
| Lambda 授權 | infra + backend | `lambda.ts` 目前**無任何 authentication**。backend 代理是第一層防護，但 Lambda 本身仍需 IAM／API key |
| `generatedBy` 的 auth 模式遮蔽 | backend | §2.4。實際值含 `auth=bearer`，原樣轉發等於把認證模式吐到瀏覽器 |

### ❌ 本次不做

- `qa`（自由問答）在 `/politics`。聊天框維持只在 `/policy-support`，見 `api_contract.md` §8.2
- 前端的上網搜尋開關。理由見 §2.3
- miss 時的非同步排隊／輪詢。現階段 miss 直接回 `503`，見 §5.2

---

## 8. 已知風險

1. **snapshot 一更新，145 組預先算全部失效。** 指紋含 evidence 的 `value`，這是刻意的（見 §5.3），但代表 data-pipeline 每次重新發布都要重跑批次約 45 分鐘。Demo 前的發布時程要把這段算進去。
   **這件事已經發生過了**：`ai-service/.precomputed` 現有的 4 筆是 `dev-full-20260912-farmland-weights` 產生的（`focusArea: employment`），而現行 published 是 `dev-full-youth-keyword-20260913`——那 4 筆已經是死的。
2. **`AI_PRECOMPUTE_WRITE_THROUGH=1` 不要在正式環境開。** 開了之後「第一個打進來的使用者」會決定所有人之後看到的卡片內容，包含模型那次剛好答得差的版本，而且沒有人會知道。
3. **`api_contract.md` §6.4 文字雲來源尚未定案**（見 §6.2 的紅字）。工作目錄版與 HEAD 版對「全期間累計 vs 單一年度 114」的說法相反，`participation_voice` 卡在定案前不應產生預先算結果。順帶一提，現行快照的 `keyword_frequency` 帶的是 `period_scope: "all_available"`，也就是 HEAD 那個版本的語意。
4. **細分 `focusArea` 未實作前的靜默退化，只發生在 lambda 路徑。** 送 `participation_voice` 給現在的 lambda 不會報錯，它會讀取全部 analytics——能跑，但慢、貴、而且四張卡內容雷同，這種失敗沒有錯誤訊息，只在 `knownLimitations` 留一條 note。批次腳本相反，是硬性 `exit 1`（§5.4）。**兩條路徑對同一個未知值的反應不一致**，除錯時要先確認自己走的是哪一條。
5. **指標語意的唯一來源是一張手寫表。** `ANALYTICS_METRIC_META` 決定模型看到的單位與青年適用性，而快照本身沒有這些欄位（§6.2）。表沒跟上快照時的失敗方式是「模型拿著錯的單位講得很有信心」——`weight` 就是現行的實例。每次 data-pipeline 加指標都要跑 `npm run dev:metric-audit`。
