# 青年參政：資料源與演算法對照

本文件以 **frontend 目前實際呈現的內容** 為準（`frontend/src/features/politics/` 與主頁
`ParticipationOverviewCard`），逐一列出每個畫面元件背後需要的資料源與計算式，作為
data-pipeline collector / transform / analytics 的開發依據。

> 現況：青年參政頁所有數字都是 **前端佔位資料**，data-pipeline 尚無任何對應 collector。
> 目前 pipeline 只有 `population` 與 `youth_budgets` 兩個資料集可部分支援本頁，其餘全部缺。
> 跨資料集 analytics 層（`src/analytics/`）尚未建立。

---

## 0. 現況總結

| 前端元件 | 呈現內容 | 目前資料來源 | 需要的真實資料源 | 狀態 |
|---|---|---|---|---|
| `ParticipationHotspotMap` / `ParticipationHotspotList` | 29 區青年參選率分層設色圖＋排名 | `fixtures/districts.csv` 的 `youthParticipationIndex` 欄（寫死） | 中選會候選人名單 + `population` | ❌ 無 collector |
| `ParticipationKpiGrid` → 服務涵蓋率 | 單一 KPI 卡 | `placeholderMetrics.ts` 種子亂數 | 青年局服務據點座標 + `population`（里級） | ❌ 無 collector |
| `ParticipationKpiGrid` → 青年里長占比 | 單一 KPI 卡 | 同上種子亂數 | 中選會里長選舉結果 + 村里數 | ❌ 無 collector |
| `ParticipationKpiGrid` → YRR | 單一 KPI 卡 | 同上種子亂數 | 中選會（席次 + 選舉人年齡結構） | ❌ 無 collector |
| `YouthActProgress`（重新定義） | 青年提案落實進度漏斗（5 階段件數） | 元件內寫死 `STAGES` | `youth_council_minutes` ＋ 青年局提案列管表 | ❌ 無 collector |
| `ResourceIoCharts` → 補助地區分布 | 長條圖 | 元件內寫死 `GRANT_BY_AREA` | 青年局對民間團體補（捐）助明細 | ❌ 無 collector |
| `ResourceIoCharts` → 補助金額年度趨勢 | 折線圖 | 元件內寫死 `GRANT_TREND` | 同上（依年度彙總） | ❌ 無 collector |
| `ResourceIoCharts` → 青年局預算執行率 | 環圈圖（92%） | 元件內寫死 `BUDGET_EXECUTION` | 青年局決算 / 預算執行報告 | ⚠️ `youth_budgets` 只有預算面 |
| `YouthTopicWordCloud` | 青年關注議題重要程度文字雲（分年） | 元件內寫死 `TOPIC_WORDS` | join.gov.tw 提點子 + 新北青年局會議記錄 PDF | ❌ 無 collector |
| 主頁 `ParticipationOverviewCard` | 青年參選熱度 12.8%、整體服務涵蓋率 68% | 元件內寫死字串 | 同「青年參選率」與「服務涵蓋率」 | ❌ 無 collector |

---

## 1. 青年參選率（地圖 + 區域排名）

### 前端

- 元件：`ParticipationHotspotMap.tsx`、`ParticipationHotspotList.tsx`
- 資料欄位：`DistrictSummary.youthParticipationIndex`（前端欄位名沿用，語意改為「青年參選率」），
  來自 `frontend/src/fixtures/districts.csv`，經 `fetchDistrictSummaries()` 讀入。
- 著色門檻（`lib/mapColors.ts` `participationFillColor`）目前是 `>=70 / >=62 / >=54 / >=46 / <46`
  五階，為舊的 0–100 指數級距；**改為參選率後需重訂門檻**（依實際單位，見下）。
- 排名：依該值由大到小排序。

### 定義

**青年參選率 = 該區 18–35 歲候選人數 ÷ 該區 18–35 歲人口。**

- 建議單位：`每十萬青年人`（分子 × 100,000），避免數值過小；也可用 `%`。
- 選舉範圍：以新北市 **直轄市議員** 為主，可另計 **里長**（分開呈現或合併，需與青年局確認）。
- 期間：以最近一屆各該選舉為準；保留歷屆以做趨勢。

### 計算式

```text
youth_candidacy_rate(區) = candidates_18_35(區) / P_18_35(區) × 100000
```

「候選人是否 18–35 歲」以投票日回推年齡足歲判定。

### 需要的資料

| 資料 | 欄位 | 資料源 | 粒度 | 現況 |
|---|---|---|---|---|
| 候選人名單（18–35） | 出生年次 / 出生日期、性別、參選職務、行政區 / 選區 | 中選會選舉及公投資料庫 | 區（里長可到里） | ❌ 無 collector |
| 青年人口 `P_18_35` | `youth_18_35_total` | `population`（戶政 ODRP014） | 區 | ✅ 已有 |

### 資料源細節

**中選會選舉及公投資料庫**
- 網站：<https://db.cec.gov.tw/>（提供 CSV / Excel 下載，非即時 REST API）
- 需要的檔案：候選人名單 / 得票明細（含出生年次、擬參選職務、行政區 / 選區）。
- 適用選舉：新北市直轄市議員、里長（村里長）。
- 期間策略：`all_available`（選舉為不定期事件，非月 / 年週期）；以「選舉屆別」為 key。
- 阻塞點：
  - 候選人年齡欄位各年度格式不一（常只有民國「出生年次」）→ 以投票日回推足歲。
  - 里長選舉資料須能對應到新北市 29 區 + 村里名稱。
  - 市議員為「選區」，需建立選區 → 行政區對應表；跨區選區的分子 / 分母需按比例分攤或標註。

**population（已存在）**
- 已輸出 `youth_18_35_total`（區級），可直接當分母，本指標不需額外擴充。
- （里級參選率若要做，需另加里級 `youth_18_35_total` transform 輸出。）

### 建議 analytics 輸出

`analytics/youth_candidacy_rate.py`：讀 `dataset_index.json` 指向的 `population` 與
（未來的）`elections` curated，輸出每區：

```json
{
  "district_id": "65000010",
  "metric_id": "youth_candidacy_rate",
  "value": 12.8,
  "unit": "per_100k_youth",
  "breakdown": {
    "city_councilor": 8.1,
    "borough_chief": 21.5
  },
  "election_term": "2022",
  "candidates_18_35": 14,
  "youth_population_18_35": 109200
}
```

---

## 2. 三大 KPI（`ParticipationKpiGrid`）

前端目前顯示：服務涵蓋率、青年里長占比、YRR，數值皆為 `placeholderMetrics.ts` 以行政區
id 為種子的亂數（`buildParticipationMetrics`）。以下為每項的真實計算方式。

### 2.1 服務涵蓋率

- 定義（PRD）：各服務據點 2–3 公里服務半徑內涵蓋之青年人口比例。
- 計算方式：**圓形 buffer（直線距離）＋ 面積比例分攤（areal / dasymetric interpolation）**，
  不做「整里進 / 整里出」的二元判定。

  1. 對每個服務據點以服務半徑 `r` 畫圓，取所有據點圓的**聯集** `B`（union，避免重複計）。
  2. 對每個里 `v`，計算里多邊形與 `B` 的交集面積比例
     `f_v = area(polygon_v ∩ B) / area(polygon_v)`，落在 `[0, 1]`。
  3. 該里「被涵蓋的青年人口」= `f_v × youth_18_35(v)`（假設里內青年在里的面積上均勻分布）。
  4. 匯總到區：

  ```text
  服務涵蓋率(區) = Σ_v [ f_v × youth_18_35(v) ]  ÷  Σ_v youth_18_35(v)
  ```

  分母是該區所有里的青年人口加總（= 該區青年人口）；比值落在 0–100%。

- 需要：
  | 資料 | 資料源 | 粒度 | 現況 |
  |---|---|---|---|
  | 青年服務據點座標 | 青年局內部（青年職涯發展中心、據點、青年住宅等清單 + 地址→geocode） | 點位 | ❌ 需青年局提供或自建 collector |
  | 里級青年人口 | 戶政 ODRP014（`population` collector 的 raw 已是村里粒度） | 里 | ⚠️ 需新增里級 transform 輸出 |
  | 里界多邊形 | 新北市村里界圖 GeoJSON（國土測繪中心 / 新北 open data） | 里 | ❌ 需新增（面積分攤必要） |
- 半徑參數：預設 2.5 km，設為可調。
- 座標系：面積與交集計算須先投影到等面積投影（如 TWD97 / EPSG:3826），不要在經緯度上算面積。
- 已知近似：里內青年「面積均勻分布」假設；圓形 buffer 用直線距離而非路網 / 通勤時間
  （此為刻意選擇，路網 isochrone 留待後續評估）。
- 阻塞點：據點清單是最大缺口（需 geocoding）；其次是里界多邊形資料。

### 2.2 青年里長占比

- 定義：18–35 歲里長當選人數 / 全區里長總席次。
- 計算式：`youth_borough_chief_ratio(區) = 里長當選人_18_35(區) / 里數(區)`
- 需要：中選會里長選舉當選名單（含出生年）、各區村里數。
- 資料源：中選會選舉資料庫（里長 / 村里長選舉）；村里數用戶政村里清單或
  `data-pipeline/config/districts.json` 擴充。
- 粒度：區。更新：每屆里長選舉後（約 4 年）。

### 2.3 YRR（Youth Representation Ratio）

- 定義：青年席次佔比 ÷ 青年選民佔比。
- 計算式：
  `YRR(區) = (青年當選人數 / 總當選席次) ÷ (青年選舉人數 / 總選舉人數)`
- 需要：當選人年齡、選舉人數按年齡（或以戶政青年 / 成年人口比替代並標 proxy）。
- 資料源：中選會（市議員 + 里長）。
- 粒度：區（市議員為選區，需選區→區對應表）。

---

## 3. 青年提案落實進度（`YouthActProgress` 重新定義）

> **改動說明**：原本前端寫死的 4 階段（`立法三讀 / 頒行公告 / 青年參政會報 / 青年政策白皮書`）
> 是 AI 佔位，且台灣目前並無已通過的《青年基本法》，追單一國家法案對市府儀表板不成立。
> 改為呈現**青年參與機制的提案處理漏斗**：制度上有意義、有真實數字，且與 §5 的
> `youth_council_minutes` 共用同一份資料。

### 前端

- 元件 `YouthActProgress.tsx`：目前是水平 stepper，`STAGES: { label, status }[]`，
  進度條寬度 = `currentIndex / (階段數 − 1)`。
- **需要的前端小改**：階段從「狀態」改為「件數」——`{ label, count }[]`，每關顯示數字，
  視覺仍是同一條 stepper / 漏斗；可保留一個「目前重點階段」高亮。

### 五個階段（固定 label）

| # | label | 定義 |
|---|---|---|
| 1 | 提案受理 | 進入青年局管道的青年提案總數（諮詢會提案、青年培力工作坊、線上徵集等） |
| 2 | 進入審議 | 排入會議「提案事項 / 討論題綱」實際討論的案 |
| 3 | 獲採納 | 會議「決議」為採納 / 原則同意 / 列管推動的案 |
| 4 | 執行中 | 已採納且已進入辦理（編列經費、跨局處分工、試辦） |
| 5 | 已完成 | 結案 / 政策或服務已上線 |

- 件數為「至少到達該階段」的累計 → 由左至右單調遞減，呈漏斗。
- `escalated`（決議提請市議會 / 納入正式施政計畫）的案，另計一個數字疊在漏斗上標記，
  與 §5 文字雲的高權重訊號一致。

### 資料源

| 資料 | 來源 | 現況 |
|---|---|---|
| 提案、討論、決議、處理層級 | `youth_council_minutes`（§5 新增的 PDF collector） | ❌ 待建 |
| 提案列管 / 追蹤清單（階段 4、5 的狀態、結案日） | 青年局內部列管表（Excel / 內部系統匯出） | ❌ 需青年局提供 |

- 若青年局沒有結構化列管表，階段 1–3 可先只用會議記錄跑，階段 4–5 標「資料待補」。

### 時間尺度

- 預設：**本屆青年諮詢會**（約 2 年一屆）累計；或近 3 個 ROC 年度，設為可切換。
- 期間策略：`all_available`（隨 `youth_council_minutes`），analytics 依屆次 / 年度彙總。
- 粒度：`organization`（新北市青年局），非 29 區。

### analytics 輸出範例

```json
{
  "metric_id": "youth_proposal_funnel",
  "scope": "青年諮詢會 第4屆",
  "period_start": "2024-01-01",
  "period_end": "2025-12-31",
  "stages": [
    { "label": "提案受理", "count": 48 },
    { "label": "進入審議", "count": 31 },
    { "label": "獲採納",   "count": 19 },
    { "label": "執行中",   "count": 12 },
    { "label": "已完成",   "count": 7 }
  ],
  "escalated_to_council": 3,
  "source_documents": ["curated/youth_council_minutes/all.json"]
}
```

### 阻塞點

- 「提案受理」的母體定義需與青年局對齊（只算諮詢會，還是含所有徵集管道）。
- 階段 4、5 幾乎一定要青年局的列管表；純靠會議記錄只能推到「獲採納」。
- 決議文字判定 `採納 / escalated` 的關鍵字表需人工校對（同 §5）。

---

## 4. 資源投入與產出（`ResourceIoCharts`）

三張圖：補助地區分布（長條）、補助金額年度趨勢（折線）、青年局預算執行率（環圈）。

### 4.1 補助地區分布 + 4.2 補助金額年度趨勢

- 前端：`GRANT_BY_AREA`（7 個寫死值）、`GRANT_TREND`（8 個寫死值）。
- 目標資料源：**青年局對民間團體補（捐）助明細**
  - 依《預算法》第 91 條，各機關補助民間團體須公開；新北市主計處 / 青年局預決算頁面
    通常有「對民間團體及個人補助」清單（PDF / Excel）。
  - 可能位置：新北市政府主計處預算書公開、青年局網站公告、政府支出決算開放資料。
- 需要欄位：受補助單位、補助 / 捐助金額、用途、年度、（受補助單位或計畫執行）行政區。
- 計算式：
  - 補助地區分布：`Σ 補助金額 group by 行政區`（同一年度）
  - 年度趨勢：`Σ 補助金額 group by 年度`
- 粒度：區（需能從受補助單位地址或計畫地點判定；判不到則 `district_id=null`）。
- 期間策略：`annual`。
- 阻塞點：來源多為 PDF、且「補助對象地址」不一定等於「服務對象所在區」，需標註口徑。

### 4.3 青年局預算執行率

- 前端：寫死 `BUDGET_EXECUTION = 92`。
- 計算式：`預算執行率 = 決算實現數 / 法定預算數 × 100%`（可分「歲出」總額或「青年發展業務」）。
- 現有資料：`youth_budgets`（`data/curated/youth_budgets/all.json`）
  - **只有預算面**：ROC 112–116 的「計畫及預算統計表」——法定 / 預算案的預算數與比率。
  - 欄位：`budget_year_roc`、`document_status`、`row_type`(total/detail)、`business_plan`、
    `value`（單位 `TWD_thousand`）、`budget_ratio_percent`。
  - `geo_level=organization`，**不可拆到 29 區**，`youth_eligibility=context_only`。
- 缺口：**決算 / 實現數**。需另接：
  - 新北市政府決算書（歲出政事別 / 機關別決算）— 主計處年度決算公開。
  - 或青年局年度施政績效報告中的預算執行率。
- 期間策略：`annual`；與 `youth_budgets` 同層級（organization）。
- 建議：新增 `youth_budget_execution` dataset 或擴充 `youth_budgets` 加入 `actual_value`。

---

## 5. 青年關注議題文字雲（`YouthTopicWordCloud`）

### 前端現況

- 元件 `YouthTopicWordCloud.tsx`：`TOPIC_WORDS`（22 個議題 + `weight` 1–5 寫死）。
- `FONT_SIZE` 依 weight 給字級（5→32px、4→25、3→20、2→16、1→13），`fontWeight` 於 weight≥4 為 800。
- 年份選擇：民國 114→110（5 年），切換目前無效果。
- 前端只吃 `{ label, weight }`，**weight 決定字體大小與粗細** → 權重越高視覺越突出。

### 資料來源（兩路合流）

**A. join.gov.tw 公共政策網路參與平台（國發會）— 由下而上的公民民意訊號**

- 主要用「提點子」（提議 / 附議）；「眾開講」（法規預告留言）為次要。
- 取得方式（擇一，需實測確認）：
  - **優先**：data.gov.tw 上的「公共政策網路參與平台」開放資料集（CSV，週期性更新），
    欄位含提案標題、內容、分類、附議數、成案狀態、提案／附議日期、權責機關。
  - 若開放資料集欄位不足：抓 join.gov.tw 提議列表頁的分頁清單，逐案取標題＋內文＋附議數＋狀態。
    無官方 REST API，比照 `youth_budget.py` 的「列表頁動態發現 ＋ 逐案抓取 ＋ 保存 raw 快照」模式。
- 篩「青年關注」：join 提案無年齡欄位，用下列規則推定並標 `proxy`：
  - 分類 / 權責機關屬教育部、勞動部、內政部（青年、就業、居住、教育、社福）；或
  - 標題／內文命中青年關鍵字表（居住正義、社宅、青創、學貸、低薪、實習…）。
- 地理：全國（join 無行政區欄位）。可另留「內文提及新北」的子集，但預設用全國青年民意。

**B. 新北市青年局會議記錄 PDF — 由上而下 / 代表制的議程訊號（新增）**

- 來源：青年局官網「資訊公開 / 會議紀錄」列表頁公開的 PDF（青年諮詢會、青年培力工作坊、
  青年提案審查、青年事務座談等）。**比照 `youth_budget.py`**：列表頁動態發現年度 PDF →
  下載 → `pypdf` 抽文字 → 保存 raw PDF ＋ metadata（會議名稱、日期、屆次、URL、SHA-256）。
- 從每份記錄抽取，並標處理層級：
  | 標記 | 判定 | 意義 |
  |---|---|---|
  | `discussed` | 出現在「提案事項 / 討論題綱」段落 | 僅列入討論 |
  | `resolved` | 出現在「決議 / 結論」段落 | 作成決議、列管追蹤 |
  | `escalated` | 決議文字含「提請市議會 / 函送議會 / 納入施政計畫 / 送局處辦理」 | 已上升為正式政策管道 |
- 層級：`organization`（新北市青年局）。
- 阻塞點：PDF 版面不一，段落標題需一組 regex；`escalated` 靠決議關鍵字表，需人工校對；
  部分會議可能只公開摘要。

### 時間尺度

- **分箱單位：ROC 年度**（對齊前端年份選擇器）。
- **保留範圍：至少前 5 個完整年度 ＋ 當年度**（對齊前端 110–114，也對齊 pipeline 既有 retention 政策）。
  join.gov.tw 自民國 104 年起、青年局自民國 108 年起，能回溯多久抓多久。
- join：以「提案日期」年份分箱（附議跨年仍歸提案年）。
- 會議記錄：以「會議日期」年份分箱。
- **期間策略：兩者都用 `all_available`**（各自輸出一份含年度欄位的完整資料），
  transform / analytics 再依年度彙總，避免每年重抓整包：
  - `join_proposals` → `curated/join_proposals/all.json`
  - `youth_council_minutes` → `curated/youth_council_minutes/all.json` ＋ raw PDF artifacts

### 權重計算（analytics）

對「(議題詞, 年度)」算 `raw_score` 再量化到前端的 1–5：

```text
raw_score(term, year) =
    w_join      × norm( Σ 命中該詞的提案數，附議數以 log(1+附議) 加權 )
  + w_minutes   × norm( 命中該詞的會議記錄提案次數 )
  + w_resolved  × [ 該年該詞出現在「決議事項」 ]
  + w_escalated × [ 該年該詞被標記 escalated ]
```

- 建議係數（可調，放 `config/`）：`w_join = 1.0`、`w_minutes = 1.8`、`w_resolved = 1.2`、
  `w_escalated = 2.5` —— **會議記錄訊號的單位權重高於 join 民意**，讓進入青年局議程 / 決議的
  議題在文字雲被明顯放大。
- 量化與上下限：
  - `weight = clamp(round(rescale(raw_score → 1..5)), 1, 5)`
  - **出現在任何會議記錄 → weight 下限 3**（保證看得見）。
  - **被標記 `escalated`（決議提請議會 / 納入施政）→ weight 強制 5**（最大字級）。
- 另輸出 `signal` 欄位（`join` / `minutes` / `escalated`），供前端日後加標籤
  （如「已進議程」「提請議會」）；目前前端只讀 weight，`escalated` 會自然呈現為最大的字。

### analytics 輸出範例

```json
{
  "metric_id": "youth_topic_weight",
  "year_roc": 114,
  "topics": [
    { "label": "居住正義", "weight": 5, "signal": "escalated",
      "join_mentions": 42, "minutes_mentions": 6, "escalated": true },
    { "label": "青年創業", "weight": 4, "signal": "minutes",
      "join_mentions": 18, "minutes_mentions": 3, "escalated": false },
    { "label": "數位權利", "weight": 1, "signal": "join",
      "join_mentions": 2, "minutes_mentions": 0, "escalated": false }
  ]
}
```

### 阻塞點小結

- join：無官方 API；提案無年齡欄位（青年關注為 proxy 推定）。
- 會議記錄：PDF 段落解析、`escalated` 關鍵字校對、公開程度。
- 中文斷詞需固定辭典（jieba 自訂詞表或 CKIP），並維護青年議題同義詞合併表
  （「社會住宅 / 社宅」「青創 / 青年創業」）。

---

## 6. 主頁「青年參政概況」卡（`ParticipationOverviewCard`）

- 前端：`青年參選熱度 12.8%`（+1.5% 趨勢）、`整體服務涵蓋率 68%`，皆寫死字串。
- 對應：
  - 青年參選熱度 = 全市層級的「青年參選率」（見 §1），趨勢 = 與上屆選舉比較。
  - 整體服務涵蓋率 = §2.1 服務涵蓋率的全市加權平均。
- 資料源同 §1、§2，無額外新增。

---

## 7. 需要新增的 collector（彙總）

| collector | 資料源 | 期間策略 | 支援的前端元件 | 優先序 |
|---|---|---|---|---|
| `elections`（候選人 / 當選人名單） | 中選會選舉及公投資料庫 | `all_available`（按屆別） | 青年參選率、里長占比、YRR、參選熱度 | 高 |
| `youth_service_points`（青年服務據點） | 青年局內部清單 + geocoding | `snapshot` | 服務涵蓋率、整體服務涵蓋率 | 高 |
| `village_boundaries`（村里界多邊形） | 國土測繪中心 / 新北 open data | `snapshot` | 服務涵蓋率（buffer × 里界面積分攤） | 高 |
| `youth_council_minutes`（青年局會議記錄 PDF） | 青年局官網「會議紀錄」列表頁 | `all_available`（PDF artifacts ＋ 年度） | 青年提案落實進度、青年關注議題文字雲（高權重訊號） | 中 |
| `youth_proposal_tracker`（青年提案列管表） | 青年局內部列管表匯出（Excel / 系統） | `snapshot` | 青年提案落實進度（階段 4、5） | 中 |
| `youth_grants`（對民間團體補助明細） | 新北市主計處 / 青年局預決算 | `annual` | 補助地區分布、補助金額趨勢 | 中 |
| `youth_budget_execution`（決算 / 執行率） | 新北市政府決算書 | `annual` | 預算執行率 | 中 |
| `join_proposals`（join.gov.tw 提點子 / 附議） | data.gov.tw 開放資料集 or join.gov.tw 列表頁 | `all_available`（含年度欄位） | 青年關注議題文字雲 | 低 |

同時需擴充：
- `transform/population.py`：加開**里級 `youth_18_35_total`** 輸出（服務涵蓋率的面積分攤以里為單位，
  必須有里級青年人口；區級參選率的分母沿用既有區級 `youth_18_35_total`，不需擴充）。
- 新增 `src/analytics/`：計算青年參選率、服務涵蓋率、`youth_proposal_funnel`、
  `youth_topic_weight` 等跨資料集指標。
  - 服務涵蓋率需要幾何運算依賴（如 `shapely`）做 buffer 聯集與里界交集面積。
  - `youth_proposal_funnel` 讀 `youth_council_minutes` ＋ `youth_proposal_tracker`，
    依關鍵字表判定各案階段。
  - `youth_topic_weight` 需要中文斷詞依賴（jieba / CKIP）＋ 青年議題同義詞表，並讀取
    `join_proposals` 與 `youth_council_minutes` 兩個 curated 輸出合流計算。

---

## 8. 附錄：目前 pipeline 可直接用於本頁的資料

| dataset | 用途 | 限制 |
|---|---|---|
| `population` | 各區青年人口（青年參選率、服務涵蓋率等的分母）；raw 為村里粒度可支援里級 | transform 目前只輸出區級 18–35 合計與總人口 |
| `youth_budgets` | 青年局年度預算數、青年發展業務占比 | organization 層級、無執行率、不可拆 29 區、ROC 112–116 |

其餘 17 個 dataset（就業、居住、交通、教育、生育等）與青年參政頁無直接關係。
