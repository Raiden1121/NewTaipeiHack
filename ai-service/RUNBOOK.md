# AI Service 本機執行指令

跑推論要用的指令都在這裡。設計說明看 `ai-service.md`，部署看 `DEPLOYMENT.md`。

## 前置

**1. `.env`（在 repo 根目錄 `c:\NewTaipeiHack\.env`，不是 ai-service 底下）**

```
MODEL_NAMME=us.anthropic.claude-sonnet-4-6
AWS_DEFAULT_REGION=us-west-2
CLAUDE_KEY=ABSK...          # Amazon Bedrock API key（ABSK 開頭）
TAVILY_API_KEY=tvly-...     # 網路搜尋，預設開啟
```

**2. 每個 PowerShell 視窗先設這一行**

```powershell
$env:BEDROCK_AUTH="bearer"
```

`.env` 裡的 `AWS_ACCESS_KEY_ID` 是 `ASIA` 開頭的臨時憑證，幾小時就過期，
過期的症狀是 `The security token included in the request is expired`。
`bearer` 改用 `CLAUDE_KEY`，活得久一些。

**3. 資料**

evidence 來自 data-pipeline 發布的 analytics 快照，預設位置
`data-pipeline/data/analytics/published/`，由 `current.json` 指向要用哪一份。

沒有的話先跑 pipeline：

```powershell
cd ..\data-pipeline
python src\run_pipeline.py --period 11507 --output-dir data
python src\run_analytics.py          # 產生並發布快照
```

---

## 常用指令

### 問一個問題，看回答與耗時

```powershell
cd ai-service
$env:BEDROCK_AUTH="bearer"

npm run dev:qa-latency                    # 7 個情境全跑（約 4 分鐘）
npm run dev:qa-latency -- --only=why      # 只跑「為什麼」類（2 題，約 45 秒）
npm run dev:qa-latency -- --only=lookup   # 只跑純查值（約 11 秒）
npm run dev:qa-latency -- --no-search     # 關掉網路搜尋，隔離搜尋的成本
```

`--only=` 可用：`lookup`（純查值）、`small`（單區小問題）、`why`（為什麼類）、
`policy`（政策類）、`explain`、`policyCopilot`。

要改問題內容就改 `src/dev/runQaLatency.ts` 的 `scenarios` 陣列。

**正常的耗時**（Sonnet 4-6，只讀 analytics，含搜尋，n=1）：

| 情境 | 耗時 |
|---|---|
| 純查值 | 10.6 秒 |
| 單區小問題 | 25.0 秒 |
| 為什麼類 | 22.5 / 22.6 秒 |
| 政策類 | 29.9 秒 ⚠️ 幾乎貼著 30 秒上限 |
| Data Explanation | 44.5 秒（線上走預先算，不即時算）|
| Policy Copilot | 61.9 秒（同上）|

### 預先算 dashboard 卡片

`explain` 與 `policyCopilot` 沒有使用者問題，即時算要 45–80 秒，超過
API Gateway 的 30 秒上限，所以離線算好、線上讀現成的。

```powershell
$env:AI_PRECOMPUTE_DIR=".precomputed"

npm run precompute -- --dry --all              # 先看要跑幾組、估多久（不花錢）
npm run precompute -- --districts=板橋區,八里區  # 指定行政區
npm run precompute -- --all                    # 29 區（約 26 分鐘）
npm run precompute -- --all --concurrency=3    # 加快，注意 Bedrock 限流

npm run dev:precompute-check                   # 驗證請求真的會命中快取
```

`dev:precompute-check` **不要跳過**。它用一個「被呼叫就丟錯」的假 client，
命中的話模型不會被呼叫；一旦 miss 就立刻炸出來。命中時應該看到：

```
✅ explain
   耗時        : 5 ms（沒有呼叫模型）
✅ policyCopilot
   耗時        : 2 ms（沒有呼叫模型）
全部命中
```

**快照換了、或改了 evidence 的組法之後要重跑 `precompute`。** 快取鍵是輸入內容
的指紋，evidence 一變指紋就變，舊的條目讀不到（不會回錯答案，但每次都會 miss）。

### 不花錢的指令（不呼叫模型）

```powershell
npm test                      # 424 個測試
npm run typecheck
npm run build

npm run dev:dump-prompt       # 印出實際送給模型的 prompt
npm run dev:dump-prompt 三重區

npm run dev:metric-audit      # 稽核指標的單位與青年適用性有沒有缺
npm run dev:metric-audit -- employment
npm run dev:metric-audit -- --strict   # 有指標不在對照表就 exit 1（可放進 CI）
```

`dev:metric-audit` 是給 pipeline 新增指標時用的。analytics 快照**沒有**
`unit` / `youth_eligibility` / `age_scope` 欄位，這三件事靠
`src/context/analyticsRecord.ts` 的 `ANALYTICS_METRIC_META` 手寫對照表。
新指標不在表裡不會有錯誤，只會少了單位 —— 這支腳本就是用來抓那個。

目前 `missingFromMeta=0`、`noUnit=18`。那 18 個是**本來就沒有單位**的
（`retentionRiskLevel=low` 這類分級字串、Shannon 指數、迴歸的 r²），
所以 `--strict` 只看 `missingFromMeta`，不看 `noUnit`。

### 讀 DynamoDB（正式路徑）

```powershell
# DynamoDB 只認 SigV4，BEDROCK_AUTH=bearer 對它沒有用
$env:AWS_ACCESS_KEY_ID="..."
$env:AWS_SECRET_ACCESS_KEY="..."
$env:AWS_SESSION_TOKEN="..."
$env:ANALYTICS_TABLE_NAME="newtaipei-youth-analytics"

npm run dev:dynamo-check                    # 驗連線 + 比對 metricId
npm run dev:dynamo-check -- 板橋區 fertility  # 換主題看落差

$env:AI_EVIDENCE_SOURCE="dynamo"
npm run dev:ask -- "為什麼樹林區的青年機會指數這麼高？" 樹林區 employment
```

`dev:dynamo-check` 的重點是**跟本機快照比對 metricId**。兩邊不一致代表切換來源會
讓預先算的 fingerprint 失效、prompt 內容改變、關鍵字表對不上指標。

實測（板橋區 / employment）：一次 `BatchGetItem` 1,167 ms、83 筆 evidence。

**憑證是兩套,不要混淆**：Bedrock 用 `BEDROCK_AUTH=bearer`（`CLAUDE_KEY`），
DynamoDB 只能用 SigV4。臨時憑證（`ASIA` 開頭）過期的症狀是
`The security token included in the request is expired`。

### 驗證模型有沒有守規矩

```powershell
npm run dev:reasoning-check    # 問資料回答不了的問題，看它會不會硬掰
npm run dev:websearch-check    # 網路搜尋與來源標註
npm run dev:bedrock-smoke      # 最小的一次真實呼叫，確認憑證與模型可用
```

**換模型之後這三支一定要跑。** 尤其 `dev:reasoning-check` ——
它驗的是「只給人口資料卻問薪資時會不會誠實說不知道」，那是這個服務最重要
也最容易退步的行為。

---

## 環境變數

| 變數 | 預設 | 用途 |
|---|---|---|
| `BEDROCK_AUTH` | 自動 | 設 `bearer` 用 `CLAUDE_KEY`；臨時憑證過期時用 |
| `AI_PRECOMPUTE_DIR` | 未設＝關閉 | 預先算結果的位置 |
| `AI_EVIDENCE_SOURCE` | `analytics` | `dynamo` / `curated` / `composite` 可切換 |
| `ANALYTICS_TABLE_NAME` | — | `AI_EVIDENCE_SOURCE=dynamo` 時必要 |
| `AI_ANALYTICS_SNAPSHOT_ID` | `current.json` 指定的 | 指定讀哪個快照 |
| `AI_DATA_DIR` | `../data-pipeline/data` | 資料目錄 |
| `WEB_SEARCH_SCOPE` | `all` | 設 `trusted` 只搜 `gov.tw` / `edu.tw` |
| `WEB_SEARCH_PROVIDER` | tavily | 設 `off` 全域關閉搜尋 |
| `BEDROCK_MAX_TOKENS` | 16384 | 不要低於 8192，Policy Copilot 會被截斷 |

`AI_EVIDENCE_SOURCE` 預設只讀 analytics，因為**進 DynamoDB 的只有 analytics
算完的結果**，curated 是 pipeline 的中間產物留在 S3。預設跟線上一致，
才不會出現「本機答得完整、線上答得殘缺」而且很難發現的落差。

---

## 常見狀況

**`The security token included in the request is expired`**
→ `$env:BEDROCK_AUTH="bearer"`

**回應的 `generatedBy` 是 `mock(no network)`**
→ 沒讀到 `.env`。確認 `c:\NewTaipeiHack\.env` 存在，並從 `ai-service/` 目錄執行
（npm script 用 `--env-file-if-exists=../.env`）。

**PowerShell 把輸出導向檔案後中文變亂碼、數字消失**
→ 先設編碼再導向，並用 `Out-File`：

```powershell
[Console]::OutputEncoding=[Text.Encoding]::UTF8
npm run dev:qa-latency 2>&1 | Out-File out.md -Encoding utf8
```

實測過「耗時：67245 ms」用 `>` 導向後變成 `??嚗?7245 ms`，最前面的數字直接不見。
腳本裡的 `SUMMARY` 行刻意是純 ASCII，就是為了這個。

**`dev:qa-latency` 印「網路搜尋：開啟」但 `webRefs` 都是 0**
→ 先看 limitations 有沒有「已開啟上網搜尋，但沒有找到相關的網路資料」。
有的話代表搜尋跑了但沒結果；沒有那句話代表 provider 沒傳進 handler
（handler 的第三個參數是選填，沒傳就是 `DisabledWebSearchProvider`）。

**`precompute` 說沒設 `AI_PRECOMPUTE_DIR`**
→ 就是沒設。不給預設值是刻意的：每組要 45 秒以上並產生 Bedrock 費用，
不該有「不小心跑了全部 29 區」這種預設行為。

**`dev:precompute-check` 說快取沒命中**
→ evidence 的組法跟 `precompute` 當時不一樣。常見原因：換了快照
（重跑 `precompute`）、改了 `AI_EVIDENCE_SOURCE`、或呼叫端用不同的
`focusArea` / evidence 筆數上限。

**evidence 是 0 筆，回答變成「資料不足」**
→ 檢查有沒有用 curated 的 dataset 名稱去篩。`EvidenceQuery.datasets` 傳
`['population', 'movement', ...]` 時，analytics repository 的規則是
「呼叫端只指名 curated dataset，代表這次不想要 analytics」→ 回空集合。

只讀 analytics 的模式下要用 **`focusArea`** 限制範圍，不要用 dataset 名稱。
（`dev:dump-prompt` 本來就踩過這個坑，已修。）
