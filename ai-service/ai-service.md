# AI Service

## Purpose

AI Service 專門處理 Amazon Bedrock 與 AI 回覆，將已整理的統計資料、證據與政策文件轉換成可理解的分析內容。

## Responsibilities

使用 TypeScript、Node.js、AWS Lambda 與 Amazon Bedrock，提供：

- **Dashboard Data Explanation**：解釋人口、機會、留才、人才、資源、居住與交通資料。
- **AI Policy Copilot**：整理問題辨識、發展優勢、資源缺口、政策方向、判斷依據與資料限制。
- **AI Data Q&A**：回答使用者對 29 區資料的查詢，並**解釋數字為什麼長這樣**。
  這是唯一有使用者問題的功能，**輸出格式跟另外兩個不同**（見「兩種輸出格式」），
  重心是數據解釋而不是政策建議（見「Q&A 的定位：數據解釋」）。

（RAG 尚未實作。）

## 公開查詢入口

正式入口由既有 Python API Lambda 提供，AI Service Lambda 不直接暴露 HTTP endpoint：

```http
POST /api/v1/ai/query
Content-Type: application/json
```

Request 只接受公開查詢欄位：

```json
{
  "action": "qa",
  "question": "板橋區有多少青年？",
  "focusDistrict": "板橋區",
  "focusArea": "population",
  "period": "114",
  "webSearch": {"enabled": true, "scope": "all", "contextSize": "low"}
}
```

`action` 僅允許 `explain`、`policyCopilot`、`qa`；`question` 最多 400 字，`qa` 必填。
`period` 可為三碼 ROC 年或五碼 ROC 月，request 欄位優先，否則解析問題中的三碼
ROC 年；沒有指定時，各 analytics dataset 使用最新可用年度，snapshot evidence 保留。
`webSearch` 預設為 `enabled=true`、`scope=all`、`contextSize=low`；`trusted` 只搜
`gov.tw` 與 `edu.tw`。

公開 request 不接受 `context`、`evidence` 或 `webFindings`。AI Service 內部仍可注入
`context`，但只供本機與測試。成功回應包含 `action`、`generatedBy`、`cache`、`output`
與 `sources`；API 邊界將 request validation、AI runtime error、timeout、server
configuration missing 映射為 400、502、504、503。

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

公開 request 的 `webSearch` 對應 `context.webSearch`；網路搜尋現在是**預設開啟**的
（`buildAiContext` 的 `webSearch.enabled` 預設 `true`），預設範圍為全網 `all`，
上下文量為 `low`。

原本預設關閉，理由是「犧牲可追溯性的行為必須由使用者明確開啟」。那個顧慮沒有消失，
但它是由別的機制處理的，而不是靠「預設不要用」：`webReferences` 與 `basis` 分開、
引用網路來源時 `limitations` 一定有說明且 `dataSufficiency` 不可能是 `sufficient`、
`findUnknownFindingIds()` 擋掉憑記憶編的網址。

開啟的理由是 Q&A 的定位是**數據解釋**。「為何八里薪資排這麼前面」這種問題，
資料管線能給的是「哪些指標方向一致」，給不出「八里有台北港物流與工業區職缺」
這種產業背景 —— 而那正是解釋數字的關鍵。預設關閉等於預設放棄解釋能力。

關掉的方法：呼叫端傳 `webSearch: { enabled: false }`，或伺服器端設
`WEB_SEARCH_PROVIDER=off`。

> 兩個營運上的注意事項：
> 1. **每個請求都會打 Tavily。** keyless 模式有 rate limit，demo 當天如果多人同時
>    操作可能被限流。搜尋失敗不會讓請求失敗（會寫進 limitations），但回答會少掉背景。
>    有 `TAVILY_API_KEY` 就設上去。
> 2. **來源品質需要收斂。** 見下面「搜尋 query 要帶地理脈絡」。

### 搜尋 query 要帶地理脈絡

`buildSearchQuery()` 會把「新北市」與行政區名補到使用者問題後面（已經出現在問句裡
就不重複加）。

這不是預防性設計，是實測踩到的：「為何八里薪資第六高？」直接拿去搜，Tavily 回來的是
**雲林與台中**薪資比較的 Threads 討論 —— 那句話裡沒有任何地理脈絡。
補上「新北市」之後，同一個問題搜到的是 518 熊班的八里區職缺頁
（台北港物流理貨、中央廚房包裝，月薪 42,000–47,000）與三立新聞提到的八里工業區，
那才是真的能解釋薪資中位數的背景。

對照組：「為何坪林薪資是全新北最高？」因為問句自帶「全新北」，一開始就搜到
水利署的坪林專題報導。差別只在 query 有沒有地理脈絡。

### 搜尋範圍開關：全網 vs 只接受信任來源

`webSearch.scope` 有兩個值，**預設 `all`**：

| | `all` | `trusted` |
|---|---|---|
| 搜尋範圍 | 全網 | 只有 `TRUSTED_SOURCE_DOMAINS`（`gov.tw`、`edu.tw`）|
| 來源品質 | 混雜（社群平台也會進來）| 乾淨，發布者有官方問責 |
| 找得到東西的機率 | 高 | **低** |

預設 `all` 的理由是 Q&A 的定位：解釋一個數字為什麼長這樣，需要的產業與地理背景
大多不在政府網站上。實測「為何八里薪資高」最有解釋力的來源是 518 熊班的八里職缺頁
（台北港物流理貨、月薪 42,000–47,000）—— 那種資訊 gov.tw 不會有。
預設 `trusted` 會讓多數「為什麼」問題搜不到東西。

`TRUSTED_SOURCE_DOMAINS` 刻意**不含新聞網域**：新聞有編輯品質但沒有官方問責，
而且一旦開始列就會變成「哪家算可信」的爭論。需要新聞時用 `all`，
並依賴 `webReferences` 與 `basis` 分離 ＋「未經驗證」標註來管理可信度。

#### ⚠️ 不要相信 Tavily 的 `include_domains`

實測（真 API key、`include_domains: ['gov.tw','edu.tw']`）回來的五筆是
`blog.salary.tw`、`news.ttv.com.tw`、`bo6s.com.tw`… —— **全部不在白名單內**。
所以那個參數至少對「裸網域後綴」不是硬過濾。

「只接受可信來源」是使用者的政策選擇，不能外包給外部 API 的行為細節，
所以 `filterByDomains()` 會自己再比對一次 hostname 後綴。兩個實作細節：

- 比對 **hostname** 而不是整個 URL —— `url.includes('gov.tw')` 會被
  `https://evil.com/?ref=gov.tw` 騙過去。
- 後綴要對齊到點的邊界，否則 `notgov.tw` 會通過。

#### 限定網域時會多抓再過濾

只要 5 筆再自己濾，實測結果是 **0 筆**。而同一個查詢不限制時，第 4 名就是
`www.bali.ntpc.gov.tw` 的八里區社會救助分析 —— 官方來源找得到，只是被擠掉了。

所以有網域限制時會向 Tavily 要 4 倍的結果，濾完再取需要的筆數。
成本很小（實測 748ms → 1,050ms），而 `trusted` 模式從 0 筆變成有結果。

濾掉的筆數會寫進 `limitations`：「搜尋結果中有 19 筆因為不在允許的網域內而被排除」。
這句話是必要的 ——「網路上沒有」與「找到了但你選擇不採用」對使用者是不同的意思，
後者才會讓他考慮切換成全網。

#### 兩層限制的關係

- `webSearch.scope`：**使用者**的選擇（前端開關）
- `WEB_SEARCH_INCLUDE_DOMAINS`：**營運者**的硬限制

同時存在時取**交集**（以較嚴格的為準）—— 使用者不該能用「全網」把營運政策繞掉。
交集為空時以營運者的為準，不會退回「不限制」。

### 實作：Tavily（預設 keyless，不需要設定）

`TavilyWebSearchProvider`（`src/websearch/tavily.ts`）＋
`createWebSearchProviderFromEnv()`（`src/websearch/factory.ts`）。

預設走 Tavily 的 keyless 模式，所以**不需要申請帳號或設環境變數，前端那顆開關
打開就真的會搜到東西**（回應格式與付費版一致，只有 rate limit 不同）。
設了 `TAVILY_API_KEY` 就改用 API key（額度較高）。

| 環境變數 | 作用 |
|---|---|
| `WEB_SEARCH_PROVIDER=off` | 伺服器端整個停用。**現在搜尋預設開啟，所以這是唯一的全域關閉手段** |
| `TAVILY_API_KEY` | 有設就用 key，沒設就 keyless |
| `TAVILY_TIMEOUT_MS` | 逾時，預設 8000 |
| `WEB_SEARCH_INCLUDE_DOMAINS` | 網域白名單。**營運者的硬限制**，使用者選「全網」也繞不過 |
| `WEB_SEARCH_SCOPE=trusted` | 把伺服器端的**預設**範圍改成只搜可信來源（仍可逐請求覆寫） |

要不要搜尋是**每個請求**由 `context.webSearch.enabled` 決定（**預設 true**）；
環境變數只決定伺服器端有沒有這個能力。

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

公開入口是既有 Python API Lambda 的 `POST /api/v1/ai/query`，request 只含
`{ action, question?, focusDistrict?, focusArea?, period?, webSearch? }`。
AI Service 的 `AiRequestSchema` 另外保留 `{ action, context }` 形狀，僅供本機與測試
注入 evidence；`action` 是 `explain` / `policyCopilot` / `qa`。

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

- `output`：structured output，加 `dataSufficiency`
  （`sufficient` / `partial` / `insufficient`）。獨立成欄位是為了讓前端能可靠判斷
  要不要改變呈現方式，而不是去解析 `limitations` 裡的中文。
  **兩種功能的填法不同**，見下面「兩種輸出格式」。
- `sources`：資料來源，**一定存在**（沒有引用任何資料時是空陣列）。見上一節。
- `generatedBy`：例如 `bedrock(<model>, <region>, auth=sigv4)` 或 `mock(no network)`。
  用途是避免 demo 時忘記設環境變數卻沒人發現。

共用型別提案在 `shared/src/aiContract.ts`，frontend / backend 可以直接引用。

### 兩種輸出格式

同一個 `StructuredOutput` 型別，但 Dashboard 與聊天框的填法不同：

| | `explain` / `policy`（Dashboard 卡片） | `qa`（聊天框） |
|---|---|---|
| `answer` | 一律 `null` | **一定有內容** |
| 四塊分析 | 有內容，這是主要產出 | 通常空陣列，**只有明確問政策時才有** |
| 重心 | 全面分析 | 數據解釋（為什麼、排第幾、是多少） |
| 跨區資料 | 只有焦點行政區 | 依問題自動撈全 29 區的相關指標 |
| Bedrock JSON Schema | `youth_policy_structured_output` | `youth_policy_qa_answer` |
| zod | `StructuredOutputSchema` | `QaOutputSchema` |

前端接 Q&A 時**顯示 `answer` 就好**，四塊非空再額外展開。

#### 為什麼 Q&A 不共用六塊

六塊是 README 為 **AI Policy Copilot** 定的格式（「整理問題、優勢、缺口與可能政策方向」），
Q&A 的輸出格式規格裡沒有規定。原本三個功能共用一份 schema，實測踩到三個問題：

1. **沒有地方放「回答」。** 使用者問「租金中位數是多少」，那個數字只能夾在
   `issues[0]` 的句子中間出現 —— 而 `issues` 的語意是「問題辨識」，不是回答。
2. **逼出填充內容。** 查值問題沒有「發展優勢」可寫，模型就寫了
   「資料管線已提供…三項彙總指標，可直接回答使用者問題」——
   那是關於資料本身的敘述，不是板橋區的優勢。
3. **同一件事講四次。** issues 說租薪比 0.57 負擔重、resourceGaps 說 0.57 有缺口、
   policyDirections 說要補貼，全是同一個事實換句話說。

#### Q&A 的定位：數據解釋，不是政策顧問

使用者在 dashboard 上看到一個數字覺得奇怪（「為何八里薪資排這麼前面？」），
他要的是**理解那個數字**，不是一份政策建議書。政策方向由 AI Policy Copilot 負責。

所以 Q&A 的 prompt 要求三件事，每一件都對應一個實測會犯的錯：

**1. 先驗證使用者的前提。** 問題常內含一個事實斷言，而它**可能是錯的** ——
實測「八里薪資第六高」其實是第五高。照抄錯誤前提然後在錯的基礎上解釋，
比答不出來更糟：使用者會帶著一個被 AI 確認過的錯誤認知離開。
斷言錯誤時 `answer` 第一句就要更正。

**2. 區分相關與因果。** 資料能顯示八里的高薪職缺比例排第 2，那是**相關**；
說「因為高薪職缺多所以薪資高」已經是因果推論，而資料無法證明。
只能用「方向一致」「可能與…有關」。

**3. 提醒樣本數陷阱。** 職缺薪資中位數的母體是求才職缺，職缺少的行政區
少數幾筆高薪職缺就會把中位數拉高。這是這份資料真實存在的坑 ——
實測坪林、烏來排在最前面，而坪林的 `high_salary_ratio` 是 0%。

跨區比較需要的資料由 `comparisonMetrics` 提供，見下一節。

#### 依主題收斂：`focusMetricIds`

同一套關鍵字也用來**收斂焦點行政區的指標**。「為何八里薪資高」不需要生育率、
服務涵蓋率、議題關鍵詞 —— 焦點行政區的 analytics 有 121 筆，大多數跟問題無關。

命中主題時：焦點行政區只取該主題的指標 ＋ `CORE_CONTEXT_METRIC_IDS`，
每個 dataset 的取樣上限降到 `FOCUSED_LIMIT_PER_DATASET`（30，預設是 200）。
實測 evidence 從 250 筆降到 95–130 筆。

三層安全保護，因為關鍵字判斷有可能錯：

1. **主題對不上就完全不收斂**，維持原本什麼都給的行為
2. **`CORE_CONTEXT_METRIC_IDS` 永遠保留**（青年人口、機會指數、留才風險、總人口）——
   就算主題判斷錯，基本背景還在
3. **收斂內容一定寫進 `limitations`**，不會靜默縮小範圍

`focusMetricIds` 裡刻意包含 curated 的欄位名（`salary_lower`、`position_count`…）。
那些是彙總中位數的**母體**，模型看得到它們才能判斷「中位數是不是被少數幾筆拉高的」——
實測坪林那題就是靠逐筆職缺上的 `query_district_mismatch_filtered` 旗標發現資料有問題的。

呼叫端自己傳 `metricIds` 時不套用收斂，也不套用跨區推導：
明確指定代表要完全接管取用範圍。

#### 跨區比較：`comparisonMetrics`

`focusDistrict` 會把 evidence 篩成一區，否則 29 區全撈會爆掉。但那個預設讓
**一整類問題答不出來** —— 要確認「第六高」對不對，就必須有全 29 區的 `salary_median`。

所以 `buildAiContext` 多了 `comparisonMetrics`：這些 metricId **不受行政區篩選限制**，
會額外撈全 29 區的值。有 `question` 時會用 `inferComparisonMetrics()` 從問題自動推導
（關鍵字 → metricId 的確定性對應，不額外呼叫模型），所以 backend 不需要知道這件事；
`explain` / `policy` 因為 `question` 是 null，自然不受影響。

兩個實作細節值得記住：

- **比較資料排在 evidence 陣列最前面。** `prioritizeEvidenceForContext()` 超過上限時是
  「每組取前 N 筆」，所以順序就是優先權。排在焦點區的 121 筆後面的話，
  配額用完就被截掉，「答不出排名」的問題又回來了。
- **關鍵字對應刻意寧可多抓。** 多給幾個指標只是多幾十筆 evidence；
  漏掉的後果是模型無法驗證前提。而且每條規則都多帶同面向的相關指標 ——
  解釋「為何薪資高」需要的往往是 `high_salary_ratio`，不只是 `salary_median` 本身。

#### 換格式沒有放掉任何保證

`applySharedInvariants()` 是兩種格式**共用的同一個函式**，所以不可能只改到一邊。
其中一條特別重要：

> 「有結論就要有依據」的判定加入了 `answer`。

不加的話會開一個大洞 —— Q&A 的四塊是空的，所以原本以「四塊非空」為條件的規則
根本不會觸發，模型可以回一句零引用的答案。現在
`answer` 非空且 `dataSufficiency !== 'insufficient'` 就算主張，必須有 `basis`
或 `webReferences`。

反過來，`insufficient` 那條規則刻意**只看四塊**：資料不足時 `answer` 應該是
「目前沒有這個資料，無法回答」，那是必要的說明而不是實質結論。把它算進去會逼模型
在該說不知道的時候回空字串，對使用者更糟。

## 資料範圍

evidence 來源抽在 `EvidenceRepository` 介面後面（`src/context/evidenceRepository.ts`），
目前依執行環境選擇 evidence source：本機可以讀 analytics snapshot／curated，
正式 Lambda 使用 DynamoDB；必要時才用 `composite` 同時讀兩者：

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

`AI_EVIDENCE_SOURCE` 有四種值：`analytics`（本機預設，讀本機快照檔）、
**`dynamo`（正式路徑，讀 DynamoDB）**、`curated`、`composite`。

### DynamoDB（正式 Lambda request 路徑）

線上路徑是 `API Gateway → Python API Lambda → AI Service Lambda`。AI Service
在沒有 `context` 時依 `AI_EVIDENCE_SOURCE=dynamo` 自己查表；公開 API 不接受
`context`、`evidence` 或 `webFindings`。`context` injection 只供本機與測試。

`Deterministic Analytics → DynamoDB / AI Context → AI Service`。
`DynamoEvidenceRepository`（`src/context/dynamoRepository.ts`）用一次
`BatchGetItem` 讀 manifest、dashboard 與六類 `ANALYSIS#*` projection item，並
重用 `flattenAnalyticsArtifact()`，讓本機 snapshot 與 Dynamo reader 的 metricId、
evidenceId、dedupe 與 limitation 規則一致。

**兩種來源產出完全相同的 metricId 與 evidenceId。** 作法是把 DynamoDB 的 item
**包回快照的巢狀形狀**再餵給同一個 `flattenAnalyticsArtifact`：

```
{ pk:'DASHBOARD', sk:'POPULATION_TREND', years:[...] }
  → { annual: { population: { years: [...] } } }
```

`wrap` 不是裝飾。不包回去的話 metricId 會變成 `years.people_total` 而不是
`annual.population.people_total`，於是 `ANALYTICS_METRIC_META`、關鍵字表、
預先算的 fingerprint 全部對不上 —— 而症狀是「本機驗過但線上不一樣」。
這個假設有對照過真正的寫入端（`modules/analytics_lambda/lambda/dynamodb_projection.py`），
不只是 seed 腳本。

驗證用 `npm run dev:dynamo-check`，它會把兩種來源的 metricId 逐一比對。

目前六類 `ANALYSIS#*` projection 已接入 reader；缺少 `META/MANIFEST` 或單一 item
時仍會寫入 limitation，不會用零值填補。projection writer 的資料形狀與 reader wrapper
由 `infrastructure/modules/analytics_lambda/lambda/dynamodb_projection.py` 與
`src/context/dynamoRepository.ts` 的測試共同驗證。

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
npm test                 # 336 個測試，含真實 curated 與 analytics 格式的 integration test
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

見 `ai-service/DEPLOYMENT.md`。摘要：一個 Lambda + Bedrock 權限，由既有
Python API Lambda 透過 `POST /api/v1/ai/query` 同步呼叫；正式 evidence 由 AI
Service 自行從 DynamoDB 讀取，因此**不需要**打包 curated 資料。

三個最容易踩到的：Lambda timeout 預設 3 秒但實測需要 10–41 秒（取決於模型）；
跨區 inference profile 的 IAM 要同時給 profile 與背後 foundation model 的權限；
API Gateway 的 integration timeout：現在 infra 用的 HTTP API 是 **30 秒且不能調**；
Regional REST API 可以透過 Service Quotas 申請調高到 300 秒；Lambda Function URL
沒有這個限制。詳見 `DEPLOYMENT.md` 的選項比較。

## 預先算（explain / Policy Copilot）

`explain` 與 `policyCopilot` 沒有使用者問題，輸出是（行政區, 主題, 那批 evidence）
的純函數，而且是給 dashboard 卡片用的。實測各要 50 與 58 秒，超過 API Gateway
HTTP API 固定的 30 秒上限。所以離線批次算好、線上讀現成的（命中 3–5 ms）。

`qa` **不快取**，而且不是「還沒做」：它的輸出取決於使用者當下打的問題，
問法有無限多種，預先算不可能涵蓋，硬要快取只是白繞一圈。

### 怎麼用

```powershell
$env:AI_PRECOMPUTE_DIR=".precomputed"

npm run precompute -- --dry --all              # 先看要跑幾組、估多久
npm run precompute -- --districts=板橋區,八里區  # 指定行政區
npm run precompute -- --all --concurrency=3    # 29 區
npm run dev:precompute-check                   # 驗證線上請求會命中
```

沒有 `--districts` 也沒有 `--all` 會直接停下來。**不給預設值是刻意的** ——
每組要 50 秒以上並產生 Bedrock 費用，不該有「不小心跑了全部 29 區」這種預設行為。

`AI_PRECOMPUTE_DIR` 沒設時快取是**關閉**的，行為完全等於沒有這個功能
（一律即時算）。位置是部署時的決定，這個模組不猜。

### 快取鍵是「輸入內容的指紋」，不是 `行政區:主題:快照id`

本機與測試可以注入 context；正式查詢則是 AI Service 自己讀 DynamoDB。請求可以由
快照 evidence 產生 fingerprint，但不能把公開 request 的 evidence 當成可接受的輸入。
若要用快照 id 當鍵，仍須確認 request 期間、選取的 evidence 與預先算結果一致，否則
快取必須 miss，避免回傳用不同資料產生的答案。

指紋 = sha256(`action` ＋ `focusDistrict` ＋ `focusArea` ＋ 排序後的
`evidence{evidenceId, value, unit}` ＋ 排序後的 `knownLimitations` ＋
`webSearch.enabled/scope`)。

**`value` 一定要進去。** evidenceId 的格式是 `{dataset}:{period}:{scope}:{metricId}`，
**不含數值** —— 只雜湊 id 的話，資料管線重算同一期的指標（值變了、id 沒變）會命中
舊答案，那是這個設計最容易出、而且錯得最安靜的一種。

刻意**不**進指紋的：`question`（explain / policyCopilot 沒有使用者問題）、
`webFindings`（搜尋結果每次都不一樣，納入等於永遠 miss；快取條目裡已經記著當初
實際用到的網路來源，追溯性不會掉）。

代價：**命中率取決於呼叫端有沒有用同樣的方式組 context。** 沒命中就退回即時計算
（正確但慢），不會回錯答案 —— **寧可 miss，不要回錯的。**
所以 `npm run dev:precompute-check` 是必要的一步，它用一個「被呼叫就丟錯」的
假 client，一 miss 就立刻炸出來（用 Mock client 不行：miss 時它會安靜地回一份
假分析，看起來就像成功）。

### 回應會說清楚這是預先算的

`AiSuccessResponse` 有 `cache`（`hit` / `miss` / `disabled` / `bypass`）與
`precomputedAt`。**這兩個欄位不能省** —— 少了它們，demo 當天看到一份內容不對的
卡片時，沒辦法分辨是「模型這次答得不好」還是「回了上一個快照的舊答案」，
而這兩件事的處理方向完全不同。

前端請把 `precomputedAt` 顯示出來（例如「分析產生於 X」）：使用者看到的卡片可能是
幾小時前算的，不講就等於暗示它是剛剛算的。

### write-through 預設關閉

miss 之後**不會**自動把結果寫回快取。看起來寫回去是好事，但那會讓「第一個打進來的
使用者」決定所有人之後看到的卡片內容 —— 包含模型那次剛好答得比較差的版本，
而且沒有人會知道。批次腳本產生的結果至少可以重跑、可以檢查。
要開就設 `AI_PRECOMPUTE_WRITE_THROUGH=1`。

### 快照換了怎麼辦

重跑 `npm run precompute`。舊的條目不會被讀到（指紋不同），但也不會自動被刪 ——
目錄會越積越多。這是已知的取捨：清理需要知道「哪些指紋還有效」，
而那要先把所有組合的 context 重算一遍，成本跟直接重跑差不多。
demo 規模不成問題，長期要處理的話應該由部署流程整批換目錄。

## ⚠️ 延遲

**結論先講（2026-09-13 更新，模型：Sonnet 4-6）：**

| 功能 | 現在 | 手段 |
|---|---|---|
| AI Data Q&A | **13.9–26.9 秒**，全部進 30 秒 | `answer` 字數上限 400 字 |
| Data Explanation | **5 ms**（命中預先算） | 批次預先算，不即時呼叫模型 |
| AI Policy Copilot | **3 ms**（命中預先算） | 同上 |

⚠️ **下面幾節保留了完整的探索過程，包含後來被推翻的結論**，因為那些過程說明了
「為什麼最後是這兩個手段」。讀的時候注意順序：早期的小節說「只有換模型有效」，
那個結論**是錯的** —— 真正有效的是「不該即時算的東西就不要即時算」。

用真實 curated 資料實測（`npm run dev:latency`，板橋區，n=1，未含網路搜尋）：

| evidence | prompt | Opus 4.6 | Sonnet 4.6 | **Haiku 4.5** |
|---|---|---|---|---|
| 3 筆 | 5,114 tok | 33,395 ms | 17,696 ms | **11,046 ms** |
| 44 筆 | 10,548 tok | 40,578 ms | 27,533 ms | **11,531 ms** |
| 83 筆（一區全量） | 14,967 tok | 39,498 ms | 34,130 ms | **10,354 ms** |

**關鍵發現：延遲跟 evidence 筆數幾乎無關。** Opus 從 3 筆到 83 筆（27 倍 evidence、
prompt 5K→15K token）只慢了 18%；Haiku 幾乎是平的。瓶頸在模型生成輸出的時間，
不是 input 大小。

**所以「限制 evidence 筆數」不能解決超時問題。**

> 🔴 **這一節原本的結論是「只有換模型可以」，那是錯的。**
> 當時漏掉一個問題：`explain` 與 `policyCopilot` **根本不需要即時算**
> —— 它們沒有使用者問題，是 dashboard 卡片。後來改成預先算之後，
> 它們的線上延遲變成 3–5 ms，跟模型完全無關。
> 而 Q&A 靠限制 `answer` 字數就進了 30 秒，也沒有換模型。
> 詳見本節最後的「最終方案」。

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

### 但「問題大小」的影響比想像中大

上面那些數字都是**最壞情況**：`explain` / `policy` 沒有使用者問題，所以模型會把
整份 context 全面分析一遍。真實的 Q&A 不是這樣 —— 使用者問一個具體問題。

實測（Opus，Q&A，改用 `answer` 格式之後）：

| 情境 | evidence | 六塊格式 | `answer` 格式 |
|---|---|---|---|
| 「租金中位數是多少？負擔重嗎？」＋ 完整 context | 250 筆 | 34,572 ms | **21,928 ms** |
| 同問題，只給居住相關指標 | 6 筆 | 25,789 ms | **14,083 ms** |
| 「租金中位數是多少？」（純查值） | 3 筆 | 12,847 ms | **8,930 ms** |
| 「居住負擔這麼重，可以怎麼改善？」（政策類） | 6 筆 | — | 32,488 ms |

三件事值得記住：

1. **一個具體問題配完整 context 是 21.9 秒 —— 進得了 30 秒，而且還是 Opus。**
   原本以為非換模型不可，其實是因為都在量最壞情況。
2. **`answer` 格式讓每一種情境再快 30–45%。** 四塊在查值問題時是空的，
   模型不再把同一個事實講四次。
3. **政策類問題四塊會回來，所以還是 32.5 秒。** 那類問題本來就需要完整分析，
   要進 30 秒仍然得換模型。

### 加上網路搜尋與跨區比較之後（「為什麼」類問題）

網路搜尋預設開啟、跨區比較資料自動納入之後重測（Opus）：

| 問題 | 耗時 | basis | webReferences | 四塊 |
|---|---|---|---|---|
| 「為何八里薪資第六高？」 | 33.3 / 42.9 s | 8 / 9 | 1 / 2 | 0 |
| 「為何坪林薪資是全新北最高？」 | 36.3 s | 9 | 2 | 0 |
| 「板橋區的青年居住負擔可以怎麼改善？」 | 55.1 s | 12 | 3 | 12 |

（八里那題跑了兩次：33.3 秒是補地理脈絡前，42.9 秒是補之後 —— 搜到的內容更多。）

比純查值的 8.9 秒明顯慢，原因是三件事疊加：網路搜尋本身的往返、跨區 29 筆
evidence、以及「為什麼」的答案本來就比「是多少」長。**「為什麼」類問題目前落在
33–43 秒，超過 30 秒上限。**

（後來實測搜尋本身只花 748–1,050 ms，所以它不是主因。）

### 依主題收斂 evidence 的效果：有限

接著試了「用問題主題收斂 evidence」（見上面的 `focusMetricIds`）。
evidence 從 250 筆降到 95–130 筆，evidence 區塊從約 125,000 字元降到 52,800–68,500：

| 問題 | 收斂前 | 收斂後 | evidence |
|---|---|---|---|
| 為何八里薪資第六高？ | 42,926 ms | **31,844 ms** | 250 → 130 |
| 為何坪林薪資是全新北最高？ | 36,296 ms | **35,252 ms** | 250 → 130 |
| 板橋區的青年居住負擔可以怎麼改善？ | 55,077 ms | **47,780 ms** | 250 → 95 |

**⚠️ 誠實的結論：這個手段基本上用完了。**

input token 砍掉將近一半，延遲只降 3–26%（而且 n=1，坪林那筆的 3% 在雜訊範圍內）。
「為什麼」類問題還是 32–35 秒，仍然超過 HTTP API 的 30 秒。

這再次確認同一件事：**瓶頸是輸出生成，不是 input 大小。** 前面「砍輸出」拿到 22–37%，
這次「砍 input」只拿到 3–26%，兩個都做完仍然差一截。剩下的差距只能靠：

- **換模型**（Haiku 推估 15 秒上下，效果與前面兩項相乘）
- **改架構**（Function URL buffered 或非同步輪詢，把死線移掉）
- **串流**（把 `basis` 排到 `answer` 前面，就能在串流前驗證完引用；
  感受延遲降到首個 token 的 2–4 秒。工作量最大但體驗最好）

**品質沒有因為收斂而下降，反而變好。** 板橋那題現在會做跨區比較
（租金所得比 0.57 vs 蘆洲 0.68、土城 0.67、三峽 0.43），並引用到新北市實際的
社宅育兒加籤與青年租金補貼金額。八里那題除了更正排名，還列出排在後面的行政區。

但輸出品質值得記錄 —— 坪林那題模型自己做到了：
- 更正「唯一最高」（實際與烏來並列第 1）
- 注意到坪林的逐筆職缺帶 `query_district_mismatch_filtered` 品質旗標
- 發現內部矛盾：薪資中位數第 1，但 `high_salary_ratio` 是 **0%**，
  推論「如果真有大量高薪工作，高薪職缺比例不可能是零」
- 結論是小樣本統計偏差，而非該區薪資真的高

那是資料分析師會想知道的事，而它是從 evidence 自己看出來的。

順帶修正一個舊結論：文件原本寫「延遲跟 evidence 筆數幾乎無關」。那是在 3→83 筆
之間量的，在那個區間成立；但 250→6 筆（prompt 從 125K 降到 4.8K 字元）是 −36%，
**在這個量級上不能說無關**。

### 換 Sonnet 4-6 之後重測（含網路搜尋，等同線上路徑）

`npm run dev:qa-latency`，Sonnet 4-6，n=1：

| 情境 | evidence | prompt | 耗時 | 30 秒 |
|---|---|---|---|---|
| 純查值（單一指標） | 2 筆 | 8.9k tok | 11,081 ms | ✅ |
| 單區小問題 | 128 筆 | 34.2k tok | 31,502 ms | ❌ |
| 為何八里薪資第六高 | 130 筆 | 33.8k tok | 26,759 ms | ✅ |
| 為何坪林薪資最高 | 130 筆 | 33.8k tok | 25,831 ms | ✅ |
| 政策類問題 | 73 筆 | 24.1k tok | 31,877 ms | ❌ |
| Data Explanation | 250 筆 | 49.5k tok | 50,247 ms | ❌ |
| Policy Copilot | 250 筆 | 49.8k tok | 58,434 ms | ❌ |

同一組情境關掉搜尋的對照（Sonnet）：純查值 7,451 / 小問題 25,890 /
八里 21,795 / 坪林 23,870 / 政策 25,362 / explain 41,228 / policyCopilot 58,921。
**搜尋的成本是 +2 到 +6 秒** —— 不只是那 2.5 秒的網路往返，找到來源之後輸出也變長。

跟 Opus 的公平對照（兩邊都關搜尋）：八里 31,844 → 21,795（−32%）、
坪林 35,252 → 23,870（−32%）、政策 47,780 → 25,362（−47%）。

> ⚠️ **量測踩到的坑，值得記下來。** 第一版量測腳本印著「網路搜尋：開啟」，
> 量到的卻是**沒有搜尋**的延遲 —— 因為 handler 的 provider 參數是選填，
> 沒傳就退回 `DisabledWebSearchProvider`。唯一的線索藏在 limitations 的
> 「已開啟上網搜尋，但沒有找到相關的網路資料」。
> `runAnalyticsDemo.ts` 當時也有同一個缺陷，所以更早的那些數字也都是沒搜尋的。
> 兩支都已修好（明確建 provider 再傳進 handler）。量測腳本要跟正式路徑
> （`handlers/lambda.ts`）走同一條路，否則量的不是同一件事。

### 最終方案一：explain / Policy Copilot 改成預先算

這兩個功能**沒有使用者問題**。輸出是（行政區, 主題, 那批 evidence）的純函數，
而且是給 dashboard 卡片用的 —— 使用者打開頁面就要看到，不是在等一個對話回覆。
50 秒與 58 秒不是「要優化的延遲」，是「架構放錯位置」。

改成離線批次算好、線上讀現成的：

| | 即時算 | 預先算命中 |
|---|---|---|
| Data Explanation | 50,247 ms | **5 ms** |
| AI Policy Copilot | 58,434 ms | **3 ms** |

命中是用一個「被呼叫就丟錯」的假 client 驗的（`npm run dev:precompute-check`），
所以確定沒有碰模型。批次實測每組 46.8–56.1 秒，29 區 × 1 主題 × 2 功能 = 58 組，
併發 2 約 26 分鐘。

機制見下面的「預先算」章節。

### 最終方案二：Q&A 的 `answer` 字數上限

剩下超時的兩個 Q&A 情境（單區小問題 31.5 秒、政策題 31.9 秒）比「為什麼」類還慢，
原因不是問題難，是**問題模糊時模型會把每個面向都講一遍**：

| 情境 | answer 長度 | 耗時 |
|---|---|---|
| 為何坪林 | 479 字 | 25,831 ms |
| 為何八里 | 581 字 | 26,759 ms |
| 單區小問題 | 773 字 | 31,502 ms |

延遲幾乎完全由輸出長度決定，所以加上 `QA_ANSWER_MAX_CHARS = 400`（見
`prompts/dataQa.ts`）。加上之後：

| 情境 | 加上限前 | 加上限後 |
|---|---|---|
| 純查值 | 11,081 ms | 13,993 ms |
| 單區小問題 | 31,502 ms ❌ | **25,378 ms** ✅ |
| 為何八里 | 26,759 ms | **25,808 ms** ✅ |
| 為何坪林 | 25,831 ms | **20,960 ms** ✅ |
| 政策題 | 31,877 ms ❌ | **26,906 ms** ✅ |

**用 prompt 指示而不是 schema 的 `maxLength`。** zod 的 `.max()` 會變成
「寫太長 → 驗證失敗 → 重試」，而重試是再花一次完整生成時間，本來為了省時間的
機制反而讓最壞情況翻倍。Bedrock structured output 的 `maxLength` 理論上會在解碼
階段就限制住，但支援度不確定，踩到就是 400（跟四塊留在 `required` 是同一個理由）。

代價：**上限不會被嚴格遵守**，實測超出約 3.5%（404、414 字對上限 400）。
最壞 25.8 秒離 30 秒還有 4 秒餘裕，所以不值得為此加驗證。

#### ⚠️ 字數上限踩到的坑：模型砍掉了解釋，不是鋪陳

加上上限的第一版，「為何坪林薪資最高」變成這樣（343 字，**沒有超過上限**）：

> 坪林區的職缺薪資中位數在這批 29 區資料中並非最高，而是與烏來區並列第一
> （同為 38,000 元/月），林口區則以 37,500 元/月排第三。這個前提需要先更正。

它**只更正前提就停筆**，完全沒有回答「為什麼」。prompt 當時已經寫了
「前提更正、樣本數警告、相關不是因果不可為了字數省略」，但漏了最基本的一條：
**更正前提不算回答完畢**。模型把「指出你問錯了」當成了完整的回答。

補上那條規則之後（414 字，20,960 ms）：

> 坪林區的職缺薪資中位數…與烏來區並列最高…
> 就同一份資料能看到的部分，坪林區的高薪職缺比例為 0（即 0%），這個指標與薪資
> 中位數的方向**並不一致**…坪林區是偏遠山區，登錄的職缺數量極少，少數幾筆薪資
> 較高的職缺就足以把中位數拉高…
> 根據網路資料，坪林區大林里的綜合所得中位數在全台村里中排名偏低（2023 年第
> 6040 名，百分位約 21.7%），這與求才職缺薪資中位數偏高的現象方向相反，
> 進一步支持「職缺樣本數少、中位數不穩定」的解讀（未經驗證）。

這是目前品質最高的一份輸出：更正前提、指出兩個指標互相矛盾、用網路找到的里級
所得資料**反向佐證**自己的解釋、最後聲明相關不是因果。

教訓：**要求變簡短時，一定要同時說「什麼不可以被砍」，而且要把「回答問題本身」
明確列進去。** 否則模型會砍掉最花字數的部分，那恰好就是解釋。

### 沒有採用的選項

- **換 Haiku 4.5** —— 前面兩個手段做完之後不需要了。Sonnet 的品質明顯更好
  （會主動更正前提、發現指標互相矛盾），這種自我對抗式的檢查是小模型最容易掉的
  能力，而它正是這個服務不出錯的核心。留著當餘裕來源。
- **串流** —— 感受延遲能降到 2–4 秒，但要動 backend 與 frontend。
  前面兩個手段已經讓所有情境進 30 秒，不需要付這個工。
  （真要做的話：把 `basis` 排到 `answer` **前面**，就能在開始串流前驗完 evidenceId，
  保住「不可捏造」的保證。）
- **Function URL / 非同步輪詢** —— 同上，不需要了。

## ⚠️ 尚未處理

- **公開 API 路徑尚未配置 authentication / rate limit。** AI Service Lambda 本身沒有
  公開 URL，只接受 API Lambda role 的 `lambda:InvokeFunction`；若把
  `POST /api/v1/ai/query` 對外提供，仍應在 API Gateway／API Lambda 補 API key、IAM
  或 Cognito 授權，避免任何人消耗 Bedrock 預算。
- **預先算的命中率取決於 backend 怎麼組 context。** 目前只驗過「ai-service 自己用
  `buildAiContext` 組」的情況會命中。backend 若用不同的 evidence 筆數上限或不同的
  `focusArea`，指紋就不同 → 每次 miss → 即時算 50 秒 → 被 API Gateway 切斷。
  **這是接線時最需要一起確認的一件事**，方法是跑 `npm run dev:precompute-check`。
- **預先算的舊條目不會被清掉。** 快照換了之後重跑 `precompute`，舊指紋讀不到但檔案
  還在，目錄會越積越多。demo 規模不成問題，長期應該由部署流程整批換目錄。
- **`answer` 字數上限不會被嚴格遵守**（實測超出約 3.5%）。用 prompt 指示而非 schema
  驗證是刻意的取捨，理由見延遲章節。最壞 25.8 秒離 30 秒還有 4 秒餘裕。
- **Q&A 的「為什麼」類問題仍然是最接近上限的路徑**（25.8 秒）。加上 Lambda 冷啟動
  就可能吃掉餘裕。要更多餘裕的話，下一步是串流或換 Haiku（兩者都還沒做）。
- **`ANALYTICS_METRIC_META` 是人工維護的單位／青年適用性對照表。** 查不到的指標會
  fallback 成名稱規則，再不行就保守標 `context_only`（不可當青年專屬數據解讀）。
  pipeline 新增指標時，指標會自動被納入 evidence，但**單位會是 null** ——
  這不會壞掉，只是模型少了單位資訊。要精確就得補這張表。
- **`yoiComponents.*` 五個子分數只對焦點行政區取。** 所以問「這區的就業子分數排第幾」
  時模型會誠實說無法確認 —— 那是刻意的取捨（5 個 × 29 區 = 145 筆 evidence），
  不是 bug。真的需要就把它們移進 `metricIds` 並重量延遲。
- RAG。
- `shared/` 的型別已同步公開 `AiQueryRequest` 與內部 context 形狀；若新增 evidence
  欄位，仍需同步 `shared/src/aiContract.ts` 與 AI Service 的 zod schema。
- **搜尋 query 在問句已經提到城市時不會補行政區錨點。** `buildSearchQuery()` 為了避免
  關鍵字被稀釋，會跳過問句裡已出現的詞。實測「為何八里的薪資中位數在**新北市**排第
  六高？」因此完全沒補脈絡，搜回來的是講雲林與台中的社群貼文；同一句話手動補上
  「新北市 八里區」就拿到八里區公所的 PDF。這是準確度問題不是延遲問題，還沒修。
- **網路來源的媒體名稱可能跟網址對不上。** 實測模型寫「來源：新頭殼新聞」，
  但 `webReferences` 的網址是 `tw.news.yahoo.com`（轉載）。不算捏造，
  但畫面上顯示的媒體名跟可點的網址不一致，追溯時會卡住。
