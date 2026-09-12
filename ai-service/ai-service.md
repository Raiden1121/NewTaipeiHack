# AI Service

## Purpose

AI Service 專門處理 Amazon Bedrock 與 AI 回覆，將已整理的統計資料、證據與政策文件轉換成可理解的分析內容。

## Responsibilities

使用 TypeScript、Node.js、AWS Lambda 與 Amazon Bedrock，提供：

- **Dashboard Data Explanation**：解釋人口、機會、留才、人才、資源、居住與交通資料。
- **AI Policy Copilot**：整理問題辨識、發展優勢、資源缺口、政策方向、判斷依據與資料限制。
- **AI Data Q&A**：回答使用者對 29 區資料的比較與查詢。

（RAG 尚未實作。）

## Boundaries

LLM 不負責計算 YoY、Opportunity Index、Resource Gap 或 Retention Risk。重要數字應來自
evidence/context，不可自行捏造；資料不足時必須標示限制。AI 建議只是政策輔助資訊，
不代表官方政策決定。

這些邊界在程式裡有對應的實作，不只是文件約定：

| 邊界 | 怎麼強制 |
|---|---|
| 不可捏造數字 | `AiEvidence.value` 型別限制成 `number \| string \| null`；prompt 只放 evidence 允許的欄位 |
| 複合指標要能追溯 | `analytics_metric` 的每一筆都帶 `computation`（算出它的 artifact 路徑、快照 id、calculation_version） |
| 同一個數字不可被當成多個來源 | analytics 各分析之間的重複值會被收合（見下方「資料範圍」） |
| 每個論點都要有依據 | `StructuredOutputSchema` 的 superRefine：四塊只要有內容，`basis` 就不可為空 |
| 不可引用不存在的 evidence | `runFeature()` 用 `findUnknownEvidenceIds()` 比對，發現就拒絕回傳 |
| 資料不足要誠實 | 沒有 evidence 時**完全不呼叫模型**，直接回 `dataSufficiency='insufficient'` |
| 不自行計算複合指標 | 逐筆交易明細的 dataset 預設排除，見下方「資料範圍」 |

## 資料來源標註（最重要的要求）

每個回應都必須附資料來源。做法：

**`sources` 是程式算出來的，不是模型產生的。** 這是刻意的設計 —— 網址與機關名稱是
最容易被 LLM 編得像真的東西（一個看起來合理但不存在的 data.gov.tw 連結，人看不出來）。
所以模型只負責寫分析，來源一律由 `collectSourceAttributions()` 從**實際被 `basis`
引用的 evidence** 推導。模型碰不到這個欄位，因此不可能出現捏造的來源。

三個保證：

1. `explainData` / `policyCopilot` / `dataQa` 的回傳值是 `{ output, sources }`，
   兩者綁在一起 —— 拿得到分析就一定拿得到來源，不可能忘記。
2. 只列出**被引用到的**來源。context 裡可能有 60 筆 evidence 但模型只用了 5 筆；
   把沒用到的來源也列出來，會讓使用者以為某機關的資料支持了某結論。
3. 模型引用不存在的 evidenceId 時整個請求會被拒絕（`runFeature` 驗證），
   因為 ID 對不上就無法追溯來源。

`SourceAttribution` 帶：中文機關名稱、中文資料集名稱、官方查證頁面、逐筆網址
（例如青年局預算書 PDF、職缺頁面）、canonical dataset、被引用的 evidenceId、
可回溯的檔案路徑、最新抓取時間。

來源對照表在 `src/types/sourceAttribution.ts` 的 `SOURCE_REGISTRY`，
涵蓋實測到的 8 個 `source` 值（有測試驗證涵蓋度）。查不到穩定官方頁面的 `url` 放 null —— 
寧可沒有連結，也不要放一個可能失效或錯誤的；此時仍會標出機關名稱與檔案路徑。

逐筆網址的取得方式有一個**刻意的窄例外**：這些連結只存在 `raw_record` 裡，
而 `raw_record` 原則上是黑名單。所以 `curatedRecord.ts` 只從一份具名欄位白名單
（`source_document_url`、`source_pdf_url`、`URL_QUERY（職缺資料URL）`）取值，
且只接受 `http(s)` 開頭的字串。不是把 `raw_record` 打開來隨便找。

## 上網搜尋（可開關）

前端有一顆「開啟上網搜尋」按鈕，對應 `context.webSearch.enabled`，**預設關閉**。
關閉是預設值而不是選項，因為上網會犧牲可追溯性與可重現性，必須由使用者明確開啟。

### 實作：Tavily（預設 keyless，不需要設定）

`TavilyWebSearchProvider`（`src/websearch/tavily.ts`）＋
`createWebSearchProviderFromEnv()`（`src/websearch/factory.ts`）。

預設走 Tavily 的 keyless 模式，所以**不需要申請帳號或設環境變數，前端那顆開關
打開就真的會搜到東西**（回應格式與付費版一致，只有 rate limit 不同）。
設了 `TAVILY_API_KEY` 就改用 API key（額度較高）。

| 環境變數 | 作用 |
|---|---|
| `WEB_SEARCH_PROVIDER=off` | 伺服器端整個停用；即使前端送 `enabled: true` 也只會拿到「沒有找到相關的網路資料」 |
| `TAVILY_API_KEY` | 有設就用 key，沒設就 keyless |
| `TAVILY_TIMEOUT_MS` | 逾時，預設 8000 |
| `WEB_SEARCH_INCLUDE_DOMAINS` | 網域白名單（例如 `gov.tw`），把來源收斂成只信官方網站 |

要不要搜尋是**每個請求**由 `context.webSearch.enabled` 決定；環境變數只決定
伺服器端有沒有這個能力。

**為什麼不用 Bedrock 原生 Web Search**：它只支援 OpenAI GPT 模型，而且必須走
`bedrock-mantle` 端點的 Responses API；本專案用 Claude + `bedrock-runtime` 的
Converse API，兩條路完全不同。

**為什麼不用 agent 框架讓模型自己決定何時搜**：那是多次 LLM 往返，而單次已經
15–26 秒、API Gateway 上限 29/30 秒，多一輪就超時。所以 query 由程式決定
（使用者問題原文，或用情境組一個）。

### 信任層級如何強制分離

網路內容不可以取得跟官方統計同等的地位。這靠五道機制，不靠 prompt 裡拜託：

| 機制 | 擋掉什麼 |
|---|---|
| `WebFinding` 與 `AiEvidence` 是**不同型別** | 兩者不可能被塞進同一個陣列 |
| `webReferences` 與 `basis` 是**不同欄位** | 前端分得出「有官方統計支撐」與「某網頁說的」 |
| 有結論就必須有 `basis` **或** `webReferences` | 完全沒有引用的結論一律拒絕 |
| `basis` 為空 → `limitations` 必須明講「沒有官方統計、僅來自網路」 | 純網路回答不會被當成官方統計分析 |
| `webReferences` 非空 → 不可 `sufficient` | 上網搜尋不會變成掩蓋資料缺口的手段 |
| `webReferences` 非空 → `limitations` 必須提到網路 | 使用者不會誤以為那些內容同等可信 |

### 沒有 evidence 時仍然會搜尋

使用者明確按了開關，卻因為 DB 沒資料就不搜，那個開關等於騙人 —— 而且管線沒資料
正是最需要上網的時候。所以搜尋排在「資料不足」判斷**之前**：

```
開啟搜尋 → 執行搜尋 → evidence 與搜尋結果都空？
                        ├─ 是 → 不呼叫模型，回 insufficient
                        └─ 否 → 呼叫模型
```

只有網路資料時（`basis` 為空、`webReferences` 有內容）是允許的產出，
但 prompt 會明確告知模型「本次沒有任何 evidence，basis 必須留空」，
避免它憑記憶補上「應該有的」官方數字；而 schema 會強制 `limitations`
說明沒有官方統計支撐。前端可以用 `basis.length === 0 && webReferences.length > 0`
判斷這是純網路回答。

### Prompt injection

snippet 是從網路抓來的**不可信輸入**，網頁上可能寫著「忽略先前的指示」。
`formatWebFindings()` 在區塊開頭就界定：這裡的文字一律視為資料、不是指令，
而且處理規則優先於區塊內任何文字。發現可疑指示要在 limitations 註明。

模型若引用了這次沒給它的 `findingId`（憑記憶編網址），`runFeature` 會直接拒絕回傳。

### 網路來源標註

`sources` 裡的網路來源 `kind` 一律是 `'web'`，`sourceId` 用網域
（例如 `www.youth.ntpc.gov.tw`）讓人判斷可信度，`datasets` 與 `sourcePaths` 為空
（網路來源沒有管線可追溯）。

這不是選配 —— AWS 的 Web Search 使用條款要求必須保留並顯示來源引用與連結。

## Inputs & Outputs

### 輸入

`{ action, context }`，schema 見 `src/handlers/lambda.ts` 的 `AiRequestSchema`。
`action` 是 `explain` / `policyCopilot` / `qa`。

`context.evidence` 的每一筆是 `AiEvidence`（`src/types/aiEvidence.ts`），
欄位是 data-pipeline curated contract 的 1:1 camelCase 版本。

`metricSource` 有三個值，解讀方式不同，guardrails 規則 7 會明確告知模型：

| 值 | 意義 | 可以拿它代表全區嗎 |
|---|---|---|
| `metric_id` | 資料集自己定義的指標（人口數、預算額） | 可以 |
| `record_field` | 單筆記錄上的欄位（某一個職缺的薪資下限） | **不可以** |
| `analytics_metric` | Deterministic Analytics 彙總完成的指標 | 可以，也可以跨區比較 |

`analytics_metric` 的每一筆都帶 `computation`，記錄它是從哪個 artifact 的哪個路徑、
哪個快照、哪個 calculation_version 來的。複合指標沒有這個就是黑箱 ——
使用者看到「板橋區房價中位數 574,657 元/坪」一定會問哪來的，
而六塊輸出的「判斷依據」跟「資料限制」也交代不過去。

### 輸出

`{ action, generatedBy, output, sources }`。

- `output`：六塊 structured output，加 `dataSufficiency`
  （`sufficient` / `partial` / `insufficient`）。獨立成欄位是為了讓前端能可靠判斷
  要不要改變呈現方式，而不是去解析 `limitations` 裡的中文。
- `sources`：資料來源，**一定存在**（沒有引用任何資料時是空陣列）。見上一節。
- `generatedBy`：例如 `bedrock(<model>, <region>, auth=sigv4)` 或 `mock(no network)`。
  用途是避免 demo 時忘記設環境變數卻沒人發現。

共用型別提案在 `shared/src/aiContract.ts`，frontend / backend 可以直接引用。

## 資料範圍

evidence 來源抽在 `EvidenceRepository` 介面後面（`src/context/evidenceRepository.ts`），
目前有兩個實作，**預設兩個都讀**（`CompositeEvidenceRepository`）：

| | `CuratedFileEvidenceRepository` | `AnalyticsSnapshotEvidenceRepository` |
|---|---|---|
| 讀什麼 | 清理後的**原始**資料點 | Deterministic Analytics **彙總計算後**的指標 |
| index | `quality/dataset_index.json` | `analytics/published/current.json` |
| 形狀 | 平的 record 陣列 | 給 dashboard 用的巢狀結構 |
| `metricSource` | `metric_id` / `record_field` | `analytics_metric` |
| 代表性 | 單筆不代表全區 | 就是全區水準，可跨區比較 |
| 逐筆網址 | 有（預算書 PDF、職缺頁面） | 沒有（彙總指標沒有單一來源頁面） |

兩者缺一都會讓分析瘸腿：只有 curated，模型看得到 3,896 筆職缺明細卻沒有「每萬青年
職缺數」，於是要嘛不敢下判斷、要嘛偷偷自己算；只有 analytics，模型看得到「機會指數
45.3 分」卻拿不到任何可以點進去查證的來源網址。

`AI_EVIDENCE_SOURCE=curated|analytics` 可以只用其中一個。
DynamoDB 實作仍待補 —— 架構上正式路徑是
`Deterministic Analytics → DynamoDB / AI Context → AI Service`，
但 `AiEvidence` 不變，所以換來源時 handler / prompt / Bedrock 那幾層不用改。

### analytics published snapshot 怎麼讀

```text
data-pipeline/data/analytics/published/
├── current.json                    ← {"snapshot_id": "dev-full-20260912"}
└── dev-full-20260912/
    ├── manifest.json               ← artifacts 清單、上游期間、warnings
    ├── dashboard_overview.json     ← 29 區指標 + 全市 KPI + 年度趨勢
    ├── district_details.json       ← 與 dashboard_overview 重複，刻意不讀
    └── analyses/{employment,fertility,participation,policy_support,
                  topic_weight,keyword_frequency}.json
```

**一律經 `current.json` 決定讀哪個快照，不掃目錄。** `published/` 底下同時有
`dev-employment-20260911`、`dev-fertility-20260912` 等只跑單一分析時產生的部分快照；
用「檔名排序取最後」會抽到殘缺快照，而 AI 會拿著殘缺資料卻毫不知情。

轉換是**通用遞迴走訪**（`src/context/analyticsRecord.ts`），不是逐路徑手寫對照表。
理由不是工作量，是**沉默失效**：analytics 有上百條巢狀路徑，pipeline 加一個新指標時
手寫對照表不會報錯，那個指標就只是永遠不出現在 AI 的 context 裡，而沒有人會發現。
通用走訪反過來 —— 新指標自動被納入，要排除才需要明確寫規則。

通用走訪的風險是「什麼都吃進來」，所以有四道限制：

| 機制 | 擋掉什麼 |
|---|---|
| `BLOCKED_KEYS` | `villages`（1,032 筆村里明細）、`normalizedInputs`（除錯用的標準化值，會被誤讀成實際量綱）、`points`（散佈圖是既有指標重繪，只留 `regression`） |
| `METADATA_KEYS` | 結構描述與圖表標籤（`metric_id`、`title`、`x_label`…），這些不是可引用的數值 |
| `NOTE_KEYS` | `status`、`blocking_reasons`、`proxy_usage`、`availability` 轉成 limitations，不變成可引用的 evidence |
| `ANALYTICS_ARTIFACT_RULES` | 各 artifact 的去重、欄位白名單、列數上限 |

**去重是這裡最重要的一件事。** 6 個 analysis 本來就會互相引用彼此的指標
（employment 要 house_price 才能算居住分數、fertility 要 opportunityIndex 才能畫散佈圖），
所以同一個數字出現在多個 artifact 是常態 —— 實測 `opportunityIndex` 出現 3 次。
不收掉的話，模型會把「兩個不同 evidenceId 有同樣的數字」當成兩個獨立來源互相佐證，
那是憑空生出來的可信度。處理方式是逐條列舉的 dedupe 規則 ＋
`dedupeAnalyticsEvidence()` 這道後備網（同區同期同值同指標名只留一筆）。

### 為什麼 house_prices 與 rentals 的逐筆明細仍然不進 LLM

`house_prices`（50,065 筆）與 `rentals`（44,852 筆）是**逐筆交易明細**。
要解讀它們必須先彙總成各區中位數這類指標，而彙總屬於 data-pipeline 的
Deterministic Analytics，不是 AI Service 的責任。

除了越界問題，還有兩個實際原因：

1. **量級**：把 `raw_record` 拔掉、攤平成最精簡 CSV 之後實測約 838K 與 670K tokens，
   合計佔全部資料的 93%，遠超一般模型的 context window。
2. **取樣不能解決問題**：給模型看 200 筆房價明細，結構上就是在誘導它自己算平均，
   那同時違反「不可自行推算」與「不可捏造數字」。

**但居住負擔面向已經不再缺漏。** analytics 現在提供 `house_price_median`、
`rent_median`、`rent_wage_ratio`，所以合併兩個來源之後，curated 那句
「居住負擔面向在此次回應中缺漏」會被 `reconcileNotes()` 換成正確的版本。
這一步是必要的：不換的話，輸出會一邊引用「房價中位數 574,657 元/坪」、
一邊在限制裡宣告「本次沒有居住負擔資料」—— 自我矛盾的輸出比沒有資料更糟，
因為使用者無法判斷哪一句是真的。

### context 筆數上限

`buildAiContext()` 有 `DEFAULT_MAX_CONTEXT_EVIDENCE = 250`。

⚠️ 這跟延遲無關（下面那節已經實測過「限制筆數不能改善延遲」）。這裡要解決的是
**context window 溢出**：實測一個行政區（curated ＋ 全部 7 個 analytics 分析）是
1,392 筆 evidence、約 216K token，而 Claude 在 Bedrock 上是 200K window ——
不設上限的話請求會直接被拒絕。`limitPerDataset` 擋不住，因為它是每個 dataset 200 筆，
而現在有 11 個 curated dataset ＋ 7 個 analytics artifact。

超過上限時用**配額**分配，不是單純照代表性排序：
`analytics_metric` 50% / `metric_id` 30% / `record_field` 20%，用不完的還回去。
第一版做的是純排序（彙總指標優先），實測直接把 curated 全部擠掉 ——
而逐筆的來源網址只存在 curated evidence 上，那會打壞這個服務最重要的需求。

另一個減量手段是 `focusArea`：它會決定要讀哪幾個 analysis
（`ANALYTICS_ARTIFACTS_BY_FOCUS_AREA`）。使用者在「就業」頁面問問題時，
青年議題關鍵詞文字雲的 74 筆權重不會讓答案更好，只會讓它更慢更貴。
這是依主題取用而不是截斷資料，而且會在 limitations 說明本次沒讀哪些分析。

## Local Development

### Mock 模式（不需要 AWS）

```bash
cd ai-service
npm install
npm test                 # 307 個測試，含真實 curated 與 analytics 格式的 integration test
npm run typecheck
npm run dev:explain      # curated（原始資料點）跑完整條路徑
npm run dev:analytics    # analytics 彙總指標跑完整條路徑
```

`dev:analytics` 的用法：

```bash
npm run dev:analytics                                # 板橋區 / employment，跑三個功能
npm run dev:analytics -- 三重區 fertility             # 指定行政區與主題
npm run dev:analytics -- 板橋區 employment --dry      # 只看 context 與 prompt 成本，不呼叫模型
npm run dev:analytics -- 板橋區 employment --mock     # 強制用 Mock
npm run dev:analytics -- 板橋區 employment --feature=explain   # 只跑其中一個功能
```

`--dry` 是最常用的：它印出 evidence 筆數、彙總指標與原始資料點各佔多少、
prompt 的 token 估算、七個關鍵複合指標有沒有讀到、以及會進到輸出 limitations
的全部既知限制 —— 不花任何 Bedrock 費用就能看出資料流對不對。

兩支腳本都需要先產生本機資料：

```bash
cd data-pipeline
python src/run_pipeline.py --period 11507 --output-dir data   # curated
# analytics 另外需要發布快照，檢查 data/analytics/published/current.json 是否存在
```

沒設 `AWS_REGION` / `BEDROCK_MODEL_ID` 時，`createBedrockClientFromEnv()` 會自動用
`MockBedrockClient`（不打網路，回傳標了 `[mock]` 的內容）。

### 接真的 Bedrock

環境變數讀取順序是 `<repo>/.env` → `ai-service/.env`（後者覆寫前者），
所以隊上共用的憑證放 repo 根目錄那一份就好。

變數名有相容別名（`MODEL_NAMME`、`CLAUDE_KEY` 等都認得），
解析邏輯集中在 `src/bedrock/env.ts`，實際採用了哪個變數會印在 smoke test 的輸出裡。

```bash
npm run dev:bedrock-smoke   # 只驗連線，不碰資料
```

這支腳本刻意不經過 context builder，所以失敗時可以確定問題在權限／region／
model access，跟資料格式無關。常見錯誤的對照表寫在
`src/dev/runRealBedrockSmokeTest.ts` 的檔頭註解。

認證支援兩種：AWS 憑證（sigv4，預設）與 Bedrock API key（bearer，值以 `ABSK` 開頭）。
兩者都設定時預設 sigv4，用 `BEDROCK_AUTH=bearer` 可以切換 —— 這條退路是為了
STS 臨時憑證（`ASIA` 開頭）過期時不用停下來重新取得憑證。

## Structured Output 怎麼保證

用 Converse API ＋ Bedrock 原生 structured outputs（`outputConfig.textFormat`），
而不是在 prompt 裡要求 JSON 再自己剖析 —— 後者最常見的失敗是模型多包一層
markdown code fence 或多寫一句開場白。

驗證分兩道，各有分工：

1. **Bedrock structured outputs 保證形狀**：欄位齊全、型別正確、沒有多餘欄位。
   送出的 JSON Schema 在 `src/types/structuredOutputJsonSchema.ts`，是手寫的，
   因為 Bedrock 只吃 Draft 2020-12 的子集（`minLength`、數值範圍、`if/then/else`
   都不支援，用了會直接回 400）。有測試擋住不支援的關鍵字。
2. **`StructuredOutputSchema` 保證語意**：disclaimer 含固定字樣、有結論必須有依據、
   標示資料不足就不可同時給結論。這些條件式規則沒辦法用 Bedrock 的 schema 子集表達。

第 2 道失敗時會把 zod 的錯誤訊息回饋給模型要它修正，重試用盡才丟錯 ——
不會把不符合 schema 的內容交給前端。

## 部署

見 `ai-service/DEPLOYMENT.md`。摘要：一個 Lambda + Bedrock 權限，
**不需要**打包 curated 資料（evidence 從 request body 進來）。

三個最容易踩到的：Lambda timeout 預設 3 秒但實測需要 10–41 秒（取決於模型）；
跨區 inference profile 的 IAM 要同時給 profile 與背後 foundation model 的權限；
API Gateway 的 integration timeout：現在 infra 用的 HTTP API 是 **30 秒且不能調**；
Regional REST API 可以透過 Service Quotas 申請調高到 300 秒；Lambda Function URL
沒有這個限制。詳見 `DEPLOYMENT.md` 的選項比較。

## ⚠️ 延遲：模型選擇是唯一有效的手段

用真實 curated 資料實測（`npm run dev:latency`，板橋區，n=1，未含網路搜尋）：

| evidence | prompt | Opus 4.6 | Sonnet 4.6 | **Haiku 4.5** |
|---|---|---|---|---|
| 3 筆 | 5,114 tok | 33,395 ms | 17,696 ms | **11,046 ms** |
| 44 筆 | 10,548 tok | 40,578 ms | 27,533 ms | **11,531 ms** |
| 83 筆（一區全量） | 14,967 tok | 39,498 ms | 34,130 ms | **10,354 ms** |

**關鍵發現：延遲跟 evidence 筆數幾乎無關。** Opus 從 3 筆到 83 筆（27 倍 evidence、
prompt 5K→15K token）只慢了 18%；Haiku 幾乎是平的。瓶頸在模型生成輸出的時間，
不是 input 大小。

**所以「限制 evidence 筆數」不能解決超時問題，只有換模型可以。**

只有 Haiku 4.5 穩定在 API Gateway 上限內。而且它守規矩的程度沒有退步 ——
`npm run dev:reasoning-check` 全部通過（正確拒答、沒有混用單位，還自己抓到
人口資料期間 2026-07 與預算期間 2027 不對應的問題）。

代價：Haiku 的分析較淺（同一個請求給 2–3 條結論，Opus / Sonnet 給 8–11 條），
而且比較容易判成 `sufficient`。取捨是「會跑完」優先於「分析深」——
一個 504 的回應沒有分析深度可言。

開啟網路搜尋會再更久（Opus 實測 41.8 秒）。

### 接上 analytics 之後重新實測（Opus，板橋區，employment 主題）

| | evidence | prompt | 耗時 |
|---|---|---|---|
| Data Explanation，只有 curated（舊測） | 83 筆 | 14,967 tok | 39,498 ms |
| Data Explanation，curated ＋ analytics | 250 筆 | 約 40,300 tok | **73,354 ms** |
| AI Data Q&A，curated ＋ analytics | 250 筆 | 約 40,300 tok | **89,058 ms** |
| AI Policy Copilot，curated ＋ analytics | 250 筆 | 約 40,300 tok | **94,203 ms** |

**這不推翻「延遲跟 evidence 筆數幾乎無關」那個結論，但要補充一句。**
原本的結論是對的 —— 瓶頸在輸出生成而不是 input 大小。而這次變慢的原因正好是輸出：
彙總指標讓模型**有東西可寫**，所以它寫得更多（basis 從個位數變成 25 條引用、
四塊各 3–4 條結論）。變慢的是產出的份量，不是讀 input 的時間。

順帶抓到一個真的 bug：輸出變長之後撞到 `maxTokens` 的預設值，JSON 被截斷，
而當時的程式會拿截斷的 JSON 去 parse、失敗、再用**同樣的上限**重試一次
（Opus 兩次各兩分鐘，白等四分鐘），最後丟出
`Expected ',' or ']' after array element in JSON at position 8045` ——
完全看不出真正原因。

預設值因此調過兩次：4096 → 8192 →（Policy Copilot 在 8192 之下時好時壞）→ **16384**。
Policy Copilot 是三個功能裡輸出最長的，而中文的 token 密度比英文高。
同時讓 `stopReason === 'max_tokens'` 立刻失敗、不重試，並在訊息裡說明可以調
`BEDROCK_MAX_TOKENS` 或減少 evidence —— 同樣的上限重試必然同樣被截斷。

### 用「砍輸出」把延遲降下來

既然瓶頸是輸出量，那就要問**輸出裡有多少是有價值的**。實測一次 Data Explanation
（13,864 字元）的組成，答案是 11%：

| 欄位 | 字元 | 佔比 |
|---|---|---|
| `evidenceReview` 的三份指標清單 | 4,842 | 35% |
| `basis` | 3,812 | 27% |
| `limitations`（其中約 31 條是既知限制的回抄） | 3,469 | 25% |
| **四塊分析結論** | 1,510 | **11%** |

那 35% 與 25% 都是**程式已經知道的東西**：指標清單完全來自 `context.evidence` 的
`metricId` / `youthEligibility` / `period`，既知限制本來就是程式產生再放進 prompt 的。
模型花了六成的輸出在把它們重打一遍。

所以改成由程式產生（`handlers/evidenceInventory.ts` ＋ `withKnownLimitations()`），
模型只寫真正需要判斷的部分（`missingForQuestion`、四塊結論、`basis`、新增的限制）：

| 功能 | 削減前 | 削減後 | 降幅 |
|---|---|---|---|
| Data Explanation | 73,354 ms | **54,049 ms** | −26% |
| AI Data Q&A | 89,058 ms | **56,489 ms** | −37% |
| AI Policy Copilot | 94,203 ms | **73,880 ms** | −22% |

**分析內容沒有變少** —— Policy Copilot 的結論條數反而從 6/6/3/4 變成 6/7/4/5。
程式盤點的指標清單也比模型寫的更完整（189 項 vs 模型當時只列了 44 項）。

⚠️ **降幅不成比例，這點很重要。** 模型輸出砍了約一半，延遲只降 22–37%。
代表有相當大的固定成本（40K token 的 input 處理 ＋ 模型基礎延遲），
所以**繼續砍輸出的邊際效益會遞減**，不要期待再砍一輪就能進 30 秒。
剩下的差距要靠換模型或改架構（見 `DEPLOYMENT.md`）。

## ⚠️ 尚未處理

- **`src/handlers/lambda.ts` 沒有任何 authentication / authorization。**
  黑客松內部呼叫可以接受，但掛成公開的 Function URL 或 API Gateway endpoint
  等於把 Bedrock 帳單開放給任何人（每次請求都會送出完整 prompt）。
  上線前必須加 API key、IAM 或 Cognito 授權，要跟 backend 一起決定。
- **模型仍然是 Opus，延遲仍然超過 API Gateway 上限。** 削減輸出之後三個功能是
  **54 / 56 / 74 秒**（削減前 73 / 89 / 94，只有 curated 的年代是 39.5 秒）。
  現在 infra 用的 HTTP API 是 30 秒且不能調，所以還是不夠 ——
  剩下的差距要靠換模型（Haiku 推估落在 15 秒上下）或改架構
  （Function URL / 非同步）。選項比較見 `DEPLOYMENT.md`。
- **`ANALYTICS_METRIC_META` 是人工維護的單位／青年適用性對照表。** 查不到的指標會
  fallback 成名稱規則，再不行就保守標 `context_only`（不可當青年專屬數據解讀）。
  pipeline 新增指標時，指標會自動被納入 evidence，但**單位會是 null** ——
  這不會壞掉，只是模型少了單位資訊。要精確就得補這張表。
- DynamoDB evidence repository。架構上正式路徑仍然是 DynamoDB，目前是直接讀
  analytics 發布出來的快照檔案。
- RAG。
- `shared/` 的型別提案還沒同步 `computation` 與 `analytics_metric` 這兩個新增內容。
