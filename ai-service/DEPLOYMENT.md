# AI Service 部署說明

給之後要部署這個服務的人看的。

⚠️ **`infrastructure/` 現在的實際 IaC 工具是 Terraform，不是 CDK**——frontend（S3 + CloudFront）、
api（Python Lambda + API Gateway）、analytics_table（DynamoDB）、raw_data／transformed_data（S3）
都已經用 Terraform 建立並部署，見 `infrastructure/main.tf` 與 `infrastructure/infrastructure.md`。
`cdk.json`、`bin/`、`lib/` 是尚未清除的舊 placeholder，並未被使用，之後也不會用來部署任何東西。
下面第 2 節示範的 CDK `NodejsFunction` 寫法僅供說明「ESM 打包／依賴打包」這個問題本身，
實際部署這個 Lambda 時請改用 Terraform（例如 `archive_file` + esbuild 打包後的 zip，
或另一個對應的 `modules/ai/` module），不要真的引入 CDK stack。

## TL;DR

一個 Lambda + Bedrock 權限。**不需要**掛任何儲存體、不需要 VPC、不需要把
`data-pipeline/data/` 的 450 MB 資料包進去。

| 項目 | 值 |
|---|---|
| Handler | `dist/handlers/lambda.handler` |
| Runtime | Node.js 22（或 20），**ESM** |
| Timeout | **120 秒**（Q&A 實測 14–27 秒，但預先算 miss 時會即時算 50–58 秒；預設 3 秒一定失敗） |
| Memory | 512 MB 起（純 I/O 等待，加記憶體不會變快） |
| IAM | `bedrock:InvokeModel`（跨區推論要多加，見下方） |
| 必要環境變數 | `BEDROCK_MODEL_ID`、`AI_PRECOMPUTE_DIR` |
| 對外介面 | 尚未決定，**目前沒有 auth** |

**模型：Sonnet 4-6**（`us.anthropic.claude-sonnet-4-6`）。不需要換 Haiku ——
`explain` / `policyCopilot` 走預先算（線上 3–5 ms），Q&A 靠 `answer` 字數上限
進到 14–27 秒。詳見下方「延遲」。

`AI_PRECOMPUTE_DIR` 列為必要不是筆誤：沒設的話 `explain` / `policyCopilot`
會即時算 50–58 秒，而 HTTP API 是 30 秒且不可調 —— 那兩個功能會**一定失敗**。

> ⚠️ **不要沿用 `infrastructure/modules/api`。** 那個 module 是 backend 的
> 資料讀取 API：`runtime = "python3.12"`、`handler = "handler.handler"`、
> `timeout = 10`，而且 CORS 只允許 `GET` / `OPTIONS`。
> AI Service 是 Node.js、需要 `POST`、需要 120 秒 timeout ——
> 三個條件都對不上，要另外開一個 Lambda。

---

## 1. 這個 Lambda 不讀檔案

先講清楚，因為最容易誤會：

`src/handlers/lambda.ts` 的 evidence **全部從 request body 進來**，
它不會去讀 `data-pipeline/data/`。所以：

- 不用把 curated 資料打包進 deployment package
- 不用掛 EFS、不用 S3 讀取權限
- 不用設 `AI_DATA_DIR`

`CuratedFileEvidenceRepository`（會讀本機檔案的那個）只在本機開發腳本
（`npm run dev:explain`）用到，**不在 Lambda 的執行路徑上**。

至於 evidence 是誰查出來的：架構圖上是 Backend API 從 DynamoDB 撈出來、
組成 request 打給 AI Service。那部分還沒接（DynamoDB repository 尚未實作）。

---

## 2. 建置與打包

```bash
cd ai-service
npm ci
npm run build      # tsc → dist/
```

三件容易踩到的事：

**（1）ESM。** `package.json` 有 `"type": "module"`，`tsc` 產出的 `dist/*.js`
是 ESM 語法。deployment package 裡**必須有一份含 `"type": "module"` 的 package.json**，
否則 Lambda 會用 CJS 載入然後報 `Cannot use import statement outside a module`。

**（2）依賴要自己打包。** 需要 `@aws-sdk/client-bedrock-runtime` 與 `zod`。
Lambda 的 Node runtime 只保證附帶一小部分 AWS SDK v3 client，
**不要假設 `client-bedrock-runtime` 在裡面**。

最省事的做法是用 CDK 的 `NodejsFunction`，它會用 esbuild 打包並自動處理上面兩件事：

```ts
new NodejsFunction(this, 'AiServiceFn', {
  entry: 'ai-service/src/handlers/lambda.ts',
  handler: 'handler',
  runtime: Runtime.NODEJS_22_X,
  timeout: Duration.seconds(60),
  memorySize: 512,
  bundling: {
    format: OutputFormat.ESM,
    // 不要 externalise aws-sdk，讓它一起打包進去
  },
  environment: { BEDROCK_MODEL_ID: 'us.anthropic.claude-…' },
});
```

**（3）不要把 `.env` 打包進去。** repo 根目錄的 `.env` 裡有 `ASIA` 開頭的 STS 臨時憑證
和一組 Bedrock API key。Lambda 要用 **execution role**，不要用長期/臨時金鑰。
`.env` 已經在 gitignore，但打包時也要確認沒有被 esbuild 或 asset copy 帶進去。

---

## 3. IAM 權限

最小權限是 `bedrock:InvokeModel`。但**跨區推論的 inference profile 有個陷阱**：

我們用的是 `us.anthropic.claude-sonnet-4-6` —— `us.` 前綴代表這是
**cross-Region inference profile**，不是單一 region 的 foundation model。
這種情況下權限要同時給：

1. inference profile 本身的 ARN
2. profile 背後**每一個目標 region** 的 foundation model ARN

只給第一個會得到 `AccessDeniedException`，而錯誤訊息不會告訴你少了第二個。

Terraform 已經這樣寫了（`infrastructure/modules/ai_service/main.tf` 的
`aws_iam_role_policy.bedrock_invoke`）：

```hcl
Action = ["bedrock:InvokeModel"]
Resource = [
  # 1. inference profile
  "arn:aws:bedrock:${region}:${account}:inference-profile/${var.bedrock_model_id}",
  # 2. profile 會路由到的每個 region 的 foundation model。
  #    範圍收在 anthropic.* —— 夠寬鬆到換 Anthropic 模型不用改 IAM，
  #    又不是整個 Bedrock 的空白授權。
  "arn:aws:bedrock:*::foundation-model/anthropic.*",
]
```

另外**要先在 Bedrock 主控台的 Model access 開通該模型**。
這是帳號層級的設定，IAM 給對了但沒開通一樣會被拒絕。

---

## 4. 環境變數

| 變數 | 必要 | 說明 |
|---|---|---|
| `BEDROCK_MODEL_ID` | ✅ | 模型或 inference profile ID |
| `BEDROCK_REGION` | 視情況 | 只在「模型不在 Lambda 所屬 region」時需要 |
| `BEDROCK_MAX_TOKENS` | ✖ | 預設 16384。**不要調低到 8192 以下** —— Policy Copilot 的六塊輸出在 8192 之下會時好時壞（JSON 被截斷）|
| `BEDROCK_TEMPERATURE` | ✖ | 預設 0 |
| `BEDROCK_MAX_ATTEMPTS` | ✖ | 預設 2 |
| `BEDROCK_STRUCTURED_OUTPUT` | ✖ | 設 `off` 可關掉原生 structured outputs（逃生門） |
| `TAVILY_API_KEY` | ⚠️ 建議 | 網路搜尋現在**預設開啟**，每個請求都會打 Tavily。沒設就用 keyless（有 rate limit） |
| `WEB_SEARCH_INCLUDE_DOMAINS` | ✖ | 網域白名單（營運者硬限制）。使用者的 `scope` 選擇繞不過它 |
| `WEB_SEARCH_SCOPE` | ✖ | `trusted` 把預設改成只搜 `gov.tw` / `edu.tw`；預設 `all` |
| `WEB_SEARCH_PROVIDER=off` | ✖ | 全域關閉網路搜尋（預設開啟，這是唯一的全域關法） |
| `TAVILY_TIMEOUT_MS` | ✖ | 預設 8000，算進 Lambda timeout |
| `AI_PRECOMPUTE_DIR` | ⚠️ 強烈建議 | 預先算結果的位置。**沒設就是關閉** → `explain` / `policyCopilot` 會即時算 50–58 秒 → 被 HTTP API 的 30 秒切斷 |
| `AI_PRECOMPUTE_WRITE_THROUGH` | ✖ | 設 `1` 讓 miss 之後把結果寫回快取。預設關閉（理由見下） |
| `AI_DATA_DIR` | ✖ | 批次腳本讀 data-pipeline 資料的位置。**Lambda 不需要**（evidence 從 request body 進來） |
| `AI_DISTRICTS_FILE` | ✖ | 批次腳本的行政區清單位置，預設從 `AI_DATA_DIR` 推出 `../config/districts.json` |

### ⚠️ `AI_PRECOMPUTE_DIR` 沒設的後果

`explain` 與 `policyCopilot` 實測 **50 與 58 秒**，而 HTTP API 是 30 秒且不可調 ——
沒有預先算，這兩個功能在正式路徑上**一定失敗**。

Lambda 的本機磁碟（`/tmp`）不是好選擇：每個執行環境各自一份，而且會被回收，
等於幾乎每次都 miss。應該指向一個共享位置（S3 掛載、EFS，或改實作成 S3／DynamoDB
—— `PrecomputedStore` 介面就是為了讓這個換掉時不用動呼叫端）。

產生方式（在有 data-pipeline 資料的機器上跑，不是在 Lambda 裡）：

```powershell
$env:AI_PRECOMPUTE_DIR="…"
npm run precompute -- --dry --all      # 先估時間：29 區 × 2 功能 ≈ 26 分鐘（併發 2）
npm run precompute -- --all
npm run dev:precompute-check           # 驗證線上請求真的會命中
```

**`dev:precompute-check` 不能跳過。** 快取鍵是「輸入內容的指紋」，
命中率取決於呼叫端（backend）有不有用同樣的方式組 context。對不上的症狀很安靜：
回應照樣正確，只是每次都花 50 秒然後被切斷。這支腳本用「被呼叫就丟錯」的假 client，
一 miss 就立刻炸出來。

**write-through 預設關閉**是刻意的：開了會讓第一個打進來的使用者決定所有人之後看到
的卡片內容，包含模型那次剛好答得差的版本，而且沒有人會知道。

### ⚠️ 網路搜尋預設開啟（行為變更）

原本是前端那顆開關控制、預設關閉；現在 `buildAiContext` 的預設是 `enabled: true`。
營運上有三個影響：

1. **每個請求都會打 Tavily。** keyless 有 rate limit，多人同時 demo 可能被限流。
   搜尋失敗不會讓請求失敗（會誠實寫進 `limitations`），但回答會少掉背景說明。
   **建議設 `TAVILY_API_KEY`。**
2. **延遲增加。** 「為什麼」類問題實測 33–43 秒（純查值 8.9 秒）。
   `TAVILY_TIMEOUT_MS`（預設 8 秒）要算進 Lambda timeout。
3. **來源品質可以由使用者切換。** `webSearch.scope` 有 `all`（全網，預設）與
   `trusted`（只搜 `gov.tw` / `edu.tw`）。前端可以做成一顆開關。
   伺服器端的預設用 `WEB_SEARCH_SCOPE=trusted` 改，硬限制用
   `WEB_SEARCH_INCLUDE_DOMAINS`（兩者同時存在時取交集，使用者繞不過營運政策）。

   ⚠️ **`trusted` 模式常常找不到東西**，這是預期行為 —— 很多產業背景不在政府網站上。
   被濾掉的筆數會寫進 `limitations`，前端可以據此提示使用者切換成全網。

搜尋本身很快：實測 `all` 748ms、`trusted` 1,050ms（後者會多抓 4 倍再過濾）。
所以 `TAVILY_TIMEOUT_MS` 預設 8 秒有很大餘裕，搜尋不是延遲的主因。

**不要設** `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`
（用 execution role）。也不要設 `AWS_REGION` —— 那是 Lambda 的保留變數，
會被自動填成 function 所在 region。

> 補充：因為 Lambda 一定會自動設 `AWS_REGION`，region 的讀取順序刻意是
> `BEDROCK_REGION` → `AWS_REGION` → `AWS_DEFAULT_REGION`，讓
> `BEDROCK_REGION` 能覆寫 Lambda 自動填的值。

沒有設 `BEDROCK_MODEL_ID` 時，服務**不會報錯**，而是自動退回 `MockBedrockClient`
回傳標了 `[mock]` 的假資料。回應的 `generatedBy` 欄位會是 `mock(no network)` ——
部署後第一件事就是確認這個欄位不是 mock。

---

## 5. 延遲：這是最需要注意的地方

**現況（2026-09-13，Sonnet 4-6，含網路搜尋）：**

| 功能 | 線上延遲 | 靠什麼 |
|---|---|---|
| `qa` | **13.9–26.9 秒** | `answer` 字數上限 400 字 |
| `explain` | **5 ms** | 預先算命中（即時算是 50.2 秒） |
| `policyCopilot` | **3 ms** | 預先算命中（即時算是 58.4 秒） |

所以部署時真正要盯的是兩件事：

1. **`AI_PRECOMPUTE_DIR` 一定要設，而且要跑過 `dev:precompute-check`。**
   沒設的話 `explain` / `policyCopilot` 會即時算 50–58 秒，必定被 30 秒切斷。
2. **Lambda timeout 設 120 秒**（不是因為 Q&A 需要，是因為預先算 miss 時會即時算，
   以及批次產生本身）。

⚠️ 下面保留完整的探索過程，包含**後來被推翻的結論**（早期寫「只有換模型有效」）。
真正有效的是「不該即時算的東西就不要即時算」。

用真實 curated 資料實測（`npm run dev:latency`，板橋區，n=1，未含網路搜尋）：

| evidence | prompt | Opus 4.6 | Sonnet 4.6 | **Haiku 4.5** |
|---|---|---|---|---|
| 3 筆 | 5,114 tok | 33,395 ms | 17,696 ms | **11,046 ms** |
| 44 筆 | 10,548 tok | 40,578 ms | 27,533 ms | **11,531 ms** |
| 83 筆（一區全量） | 14,967 tok | 39,498 ms | 34,130 ms | **10,354 ms** |

**兩個結論：**

1. **只有 Haiku 4.5 進得了 API Gateway 的 29/30 秒。** Opus 即使只餵 3 筆
   evidence 也要 33 秒。
2. **延遲跟 evidence 筆數幾乎無關** —— Opus 從 3 筆到 83 筆（27 倍）只慢 18%，
   Haiku 幾乎是平的。瓶頸在**輸出生成**，不是 input 大小。

開啟網路搜尋會再更久（Opus 實測 41.8 秒）。

### 接上 analytics 之後重測，以及削減輸出的效果

上面那張表是只有 curated 的年代量的。接上 analytics 的彙總指標之後 context 變成
一區 250 筆 evidence（約 40K token），而**彙總指標讓模型有東西可寫**，所以它寫得更多，
延遲跟著上去。

第 2 個結論（瓶頸在輸出）因此有一個直接的用法：**砍掉沒有價值的輸出**。
實測一次 Data Explanation 的輸出組成，發現 89% 是簿記、只有 11% 是分析：

| 欄位 | 字元 | 佔比 |
|---|---|---|
| `evidenceReview` 的三份指標清單 | 4,842 | 35% |
| `basis` | 3,812 | 27% |
| `limitations`（其中約 31 條是既知限制的回抄） | 3,469 | 25% |
| **四塊分析結論** | 1,510 | **11%** |

那 35% 與 25% 都是**程式已經知道的東西**，所以改成由程式產生：
指標盤點交給 `handlers/evidenceInventory.ts`，既知限制交給
`runFeature()` 的 `withKnownLimitations()`。模型只寫真正需要判斷的部分。

| 功能 | 削減前 | 削減後 | 降幅 |
|---|---|---|---|
| Data Explanation | 73,354 ms | **54,049 ms** | −26% |
| AI Data Q&A | 89,058 ms | **56,489 ms** | −37% |
| AI Policy Copilot | 94,203 ms | **73,880 ms** | −22% |

分析內容沒有變少 —— Policy Copilot 的結論條數反而從 6/6/3/4 變成 6/7/4/5。

**但要注意降幅不成比例。** 模型輸出砍了約一半，延遲只降 22–37%。代表有相當大的
固定成本（40K token 的 input 處理 ＋ 模型本身的基礎延遲），所以**繼續砍輸出的
邊際效益會遞減** —— 不要期待再砍一輪就能進 30 秒。

這直接影響兩個設定：

**Lambda timeout：** 預設 **3 秒**，一定失敗。用 Opus 要設 **120 秒**
（單次實測已達 74 秒，而 `BEDROCK_MAX_ATTEMPTS` 預設 2 —— 語意驗證失敗時會再打一次）。
搜尋還有自己的逾時（`TAVILY_TIMEOUT_MS`，預設 8 秒），也要算進去。
換成 Haiku 之後可以降到 60 秒。

> ⚠️ 只有被 `maxTokens` 截斷這種情況**不會**重試（會立刻失敗並說明原因），
> 所以最壞情況是「語意驗證失敗 → 重試一次」，不是無上限地累加。

**API Gateway integration timeout：** 這是真正的天花板。

| 介面 | 上限 |
|---|---|
| HTTP API（API Gateway v2） | 30 秒，**不能調** |
| REST API（Regional / private） | 預設 29 秒，可透過 Service Quotas 調高（最高 300 秒） |
| REST API（edge-optimized） | 29 秒，**不能調** |
| Lambda Function URL | 沒有 29 秒那個限制 |

選項，依「多快能做完」排序：

1. **換 Haiku 4.5。** 改 `BEDROCK_MODEL_ID` 就好，程式不用動，而且效果跟上面的
   輸出削減是**相乘**的：削減後 Opus 是 54 秒，而舊測 Haiku 比 Opus 快約 3.8 倍
   （83 筆 evidence：39.5 秒 vs 10.4 秒），推估會落在 15 秒上下。
   ⚠️ 改完務必跑 `npm run dev:reasoning-check` 與 `npm run dev:websearch-check` ——
   之前那些檢查是在**小 context** 下驗的，40K token 下 Haiku 還守不守規矩沒有驗過。
2. **用 Lambda Function URL** 避開 29 秒天花板（`AuthType: AWS_IAM`，只給 backend 呼叫）。
   若要保留 Opus 級的分析深度，這是最省事的一條。
   注意：**buffered 模式**上限 15 分鐘就夠了，不需要 response streaming ——
   而且不該用 streaming，因為 `runFeature()` 必須拿到完整 JSON 才能驗 schema
   與擋掉捏造的 evidenceId，串流等於在驗證通過前就把內容送給前端。
3. **改成 Regional REST API ＋ 申請 Service Quotas 調高**（最高 300 秒）。
   要等審核，而且讓使用者同步等 60 秒的 UX 本來就不好。
4. **改非同步**（先回 202 + job id，前端輪詢）。UX 最好也最穩，但要動 backend
   與 frontend，還要一個放 job 狀態的地方。

⚠️ **不要指望「少送一點 evidence」能解決。** 減少 evidence 只會間接讓模型少寫一點，
直接效果實測是無效的（Opus 3 筆 → 83 筆只慢 18%）。

### 實際採用的方案（推翻上面的「只有換模型」）

上面那份選項清單漏了一個問題：**`explain` 與 `policyCopilot` 根本不需要即時算。**
它們沒有使用者問題，輸出是（行政區, 主題, 那批 evidence）的純函數，
而且是給 dashboard 卡片用的 —— 使用者打開頁面就要看到，不是在等一個對話回覆。
50 秒與 58 秒不是「要優化的延遲」，是「架構放錯位置」。

改成離線批次算好、線上讀現成的之後：

| 功能 | 即時算 | 預先算命中 |
|---|---|---|
| Data Explanation | 50,247 ms | **5 ms** |
| AI Policy Copilot | 58,434 ms | **3 ms** |

剩下的 Q&A 靠限制 `answer` 字數（400 字）進 30 秒：單區小問題
31,502 → 25,378 ms、政策題 31,877 → 26,906 ms、為何八里 26,759 → 25,808 ms。

**所以模型沒有換，Sonnet 4-6 就夠了。** Haiku 留著當餘裕來源 ——
Sonnet 會主動更正使用者說錯的前提、會發現兩個指標互相矛盾，
那種自我對抗式的檢查是小模型最容易掉的能力，而它正是這個服務不出錯的核心。

機制與取捨見 `ai-service.md` 的「預先算」章節。

---

## 6. ⚠️ 目前沒有 auth

`src/handlers/lambda.ts` **沒有任何 authentication / authorization**。

如果直接掛成公開的 Function URL 或 API Gateway endpoint，等於把 Bedrock 帳單
開放給任何人呼叫 —— 每個請求都會送出完整 prompt（含 few-shot 與 evidence），
而且是 Opus 級的價格。

部署前要選一個：

- **只給 Backend 呼叫**（推薦）：不要開公開 endpoint，用 IAM 授權讓 Backend Lambda
  直接 `lambda:InvokeFunction`，或 Function URL 設 `AuthType: AWS_IAM`。
  這樣 AI Service 完全不對外，最省事也最安全。
- API Gateway + API key / Usage plan（有 rate limit，但 API key 算不上真的認證）
- Cognito authorizer（如果前端本來就有登入）

這件事要跟 backend 一起決定，我不會單方面加。

---

## 7. 部署後怎麼驗

```bash
aws lambda invoke --function-name <name> \
  --cli-binary-format raw-in-base64-out \
  --payload '{"body":"{\"action\":\"explain\",\"context\":{\"question\":null,\"focusDistrict\":\"板橋區\",\"focusArea\":\"population\",\"evidence\":[],\"knownLimitations\":[]}}"}' \
  out.json && cat out.json
```

用**空 evidence** 當第一個測試是刻意的：這條路徑不會呼叫 Bedrock，
所以能單獨驗證「部署、ESM 載入、依賴打包、handler 路由」都對，
不會跟 Bedrock 權限問題混在一起。預期會拿到 HTTP 200 加

```json
{ "output": { "dataSufficiency": "insufficient", ... }, "sources": [] }
```

這一步過了再放一筆真的 evidence 進去驗 Bedrock 權限。
`ai-service/src/dev/runRealBedrockSmokeTest.ts` 裡有一筆可以直接複製的 evidence。

檢查清單：

- [ ] `generatedBy` 不是 `mock(no network)`
- [ ] `sources` 有內容，且 `url` 指得到真實頁面
- [ ] 冷啟動下的總時間仍在 API Gateway timeout 內
- [ ] **`explain` / `policyCopilot` 的 `cache` 是 `hit`。**
      是 `disabled` 代表沒設 `AI_PRECOMPUTE_DIR`；是 `miss` 代表指紋對不上
      （backend 組 context 的方式跟預先算當時不同）。兩種都會即時算 50–58 秒
      而被 30 秒切斷 —— 這是部署後最容易漏掉、而且症狀最不明顯的一項
- [ ] `qa` 的 `cache` 是 `bypass`（Q&A 不快取，這是預期值）

## 8. 回應格式

`{ action, generatedBy, cache, precomputedAt, output, sources }`。型別在
`shared/src/aiContract.ts`，frontend / backend 直接引用那份。

`cache` 與 `precomputedAt` 說明這份結果是預先算的還是即時算的：

| `cache` | 意思 |
|---|---|
| `hit` | 回的是批次預先算好的結果，`precomputedAt` 是它**當初**產生的時間 |
| `miss` | 快取開著但沒有這一筆，已即時計算（`explain` / `policyCopilot` 會是 50–58 秒，很可能超時） |
| `disabled` | 沒設 `AI_PRECOMPUTE_DIR` |
| `bypass` | 這個 action 不快取（`qa` 永遠是這個） |

**前端請把 `precomputedAt` 顯示出來**（例如「分析產生於 X」）：使用者看到的卡片可能
是幾小時前算的，不講就等於暗示它是剛剛算的。

`cache` 也是排查的第一個線索：看到內容不對的卡片時，`hit` 代表可能是舊快照的答案
（重跑 `npm run precompute`），`bypass` / `miss` 代表是模型這次的輸出。

⚠️ **`output` 有兩種填法，前端要分開處理：**

| | `action: 'explain'` / `'policy'` | `action: 'qa'` |
|---|---|---|
| `output.answer` | 一律 `null` | **一定有內容**（聊天框顯示這個） |
| 四塊分析 | 有內容 | 通常是空陣列，只有政策類問題才有 |

所以聊天框的實作是「顯示 `output.answer`」，不是「把四塊拼起來」。
四塊非空時可以在回答下面另外展開成分析區塊。

Q&A 的重心是**數據解釋**：使用者問「是多少」「為什麼」「排第幾」時四塊會是空的，
只有明確問「該怎麼做」才會有內容。所以聊天框不需要為四塊預留固定版位。

> `answer` 可能會**更正使用者的前提**（「排第 5 高，不是第 6 高」）——
> 這是刻意的行為，不是錯誤。

`answer` 的保證：`action: 'qa'` 時一定非空。即使資料不足也會是
「目前沒有這個資料，無法回答」這類明確說明，而不是空字串 —— 所以前端不需要
為 null 準備 fallback 文案。

HTTP 狀態碼：

- `200` 成功，**包含「資料不足」** —— 那是正常結果不是錯誤
- `400` request 不符合 schema，`issues` 會列出逐欄位問題
- `502` 格式對但執行失敗（Bedrock 不可用、模型輸出反覆不合 schema、
  引用了不存在的 evidenceId）。可重試
