# 青年參政：資料源與演算法對照

本文件以 **frontend 目前實際呈現的內容** 為準（`frontend/src/features/politics/` 與主頁
`ParticipationOverviewCard`），逐一列出每個畫面元件背後需要的資料源與計算式，作為
data-pipeline collector / transform / analytics 的開發依據。

> 現況：data-pipeline 已產生青年參政 analytics 與開發用 published snapshot；本文件描述資料契約與計算口徑。前端仍未在本次範圍內改接，因此畫面可能仍使用舊的 fixture／placeholder。
> `elections`、`youth_service_points`、`village_boundaries`、`population_villages`、`youth_budgets` 與 `youth_grants` 均已有 raw／curated 輸出；跨資料集結果位於 `data/analytics/youth_participation/all.json`。

---

## 0. 現況總結

### 0.1 已確認的選舉資料範圍：方案 B

本專案採用方案 B：`elections` 只保存 2014／2018／2022 新北市直轄市議員 `T1` 與村里長 `V1`。

- `V1` 是目前 29 區主要青年參與指標來源，使用來源行政區與村里欄位；可作青年里長占比、YRR 與青年參選率。
- `T1` 分開保存，保留選區代碼與名稱；因選區可能跨越多個行政區，不把 `district_id` 硬套成單一新北 29 區，僅提供選舉區粒度結果。
- 總統、立法委員、市長與其他選舉類型不進入 29 區指標的 `elections` 輸出。
- 候選人年齡篩選仍由 analytics 以投票日與出生日期／年次處理；collector／transform 只保存來源年齡與日期欄位。

| 前端元件 | 呈現內容 | 目前資料來源 | 需要的真實資料源 | 狀態 |
|---|---|---|---|---|
| `ParticipationHotspotMap` / `ParticipationHotspotList` | 29 區青年參選率分層設色圖＋排名 | `fixtures/districts.csv` 的 `youthParticipationIndex` 欄（舊前端） | V1 中選會候選人名單 + `population` | ✅ pipeline 已輸出 29 區 V1 |
| `ParticipationKpiGrid` → 服務涵蓋率 | 單一 KPI 卡 | `placeholderMetrics.ts` 種子亂數 | 青年局服務據點座標 + `population_villages` + `village_boundaries` | ✅ 已計算；目前依里級人口 join 狀況標 `partial` |
| `ParticipationKpiGrid` → 青年里長占比 | 單一 KPI 卡 | 同上種子亂數 | 中選會 V1 里長選舉結果 + 同年人口 | ✅ pipeline 已輸出 |
| `ParticipationKpiGrid` → YRR | 單一 KPI 卡 | 同上種子亂數 | V1 當選席次 + `population` 青年人口比例 proxy | ✅ 已輸出並標 `denominator_type=population_proxy` |
| `YouthActProgress`（重新定義） | 青年提案落實進度漏斗（5 階段件數） | 元件內寫死 `STAGES` | `youth_council_minutes`；列管表缺少時第 4–5 階為 `null` | ✅ analytics 已建立，狀態 `partial` |
| `ResourceIoCharts` → 補助地區分布 | 長條圖 | 元件內寫死 `GRANT_BY_AREA` | 青年局對民間團體補（捐）助明細 | ⚠️ collector／analytics 已有；官方 PDF 沒有計畫地或地址，行政區目前 unresolved |
| `ResourceIoCharts` → 補助金額年度趨勢 | 折線圖 | 元件內寫死 `GRANT_TREND` | 同上（依年度彙總） | ✅ 已輸出 ROC 110–114，實際來源目前 111–115 |
| `ResourceIoCharts` → 青年局預算執行率 | 環圈圖（92%） | 元件內寫死 `BUDGET_EXECUTION` | 青年局決算 / 預算執行報告 | ⚠️ analytics 已接；目前只有 ROC 113 可算，其他年度保留 `null` |
| `YouthTopicWordCloud` | 青年關注議題重要程度文字雲（分年） | 元件內寫死 `TOPIC_WORDS` | join.gov.tw 提點子 + 新北青年局會議記錄 PDF | ✅ standalone analytics 保留，並嵌入 `participation.json` |
| 主頁 `ParticipationOverviewCard` | 青年參選熱度 12.8%、整體服務涵蓋率 68% | 元件內寫死字串 | `participation.json` 的 V1 與 service coverage | ✅ pipeline 已有；前端尚未接線 |

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
- 選舉範圍：2014／2018／2022 新北市 **村里長 V1** 為 29 區主要指標；**直轄市區域議員 T1** 分開保存為選舉區結果，不放入 29 區指標。
- 期間：固定保留三屆，使用 `all_available` 以做趨勢。

### 計算式

```text
youth_candidacy_rate(區) = candidates_18_35(區) / P_18_35(區) × 100000
```

「候選人是否 18–35 歲」以投票日回推年齡足歲判定。

### 需要的資料

| 資料 | 欄位 | 資料源 | 粒度 | 現況 |
|---|---|---|---|---|
| 候選人名單（18–35） | 出生年次／出生日期、來源年齡、性別、參選職務、行政區／選區 | 中選會 `elections` | T1 選區、V1 區／里 | ✅ collector／transform／analytics |
| 青年人口 `P_18_35` | `youth_18_35_total` | `population`（戶政 ODRP014） | 區 | ✅ 已有 |

### 資料源細節

**中選會選舉及公投資料庫**
- 網站：<https://data.cec.gov.tw/選舉資料庫/votedata.zip>（官方 ZIP 候選人與區域檔）
- 已接 collector：只抓 2014／2018／2022、新北市代碼 `65`、`T1`／`V1`；analytics 以 V1 作 29 區主指標。
- 需要的欄位：候選人名單中的出生日期／年次、來源年齡、職務、政黨、行政區／選區與村里代碼。
- 期間策略：`all_available`（選舉為不定期事件，非月／年週期）；以選舉屆別與 `source_code` 保存。
- 阻塞點：
  - 候選人年齡欄位各年度格式不一（常只有民國「出生年次」）→ 以投票日回推足歲。
  - 里長選舉資料需對應到新北市 29 區 + 村里名稱；目前 V1 已做來源行政區的精確 mapping。
  - 市議員為「選區」，目前刻意保留選區粒度，不做跨區分子／分母硬分攤；T1 結果不放入 29 區 `districts`。

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
  | 青年服務據點座標 | `youth_service_points`（青年局青創基地地址與官方門牌座標） | 點位 | ✅ 9 筆均有可驗證座標 |
  | 里級青年人口 | `population_villages`（戶政 ODRP014 transform） | 里 | ✅ 已有 ROC 114 月資料 |
  | 里界多邊形 | `village_boundaries`（國土測繪中心） | 里 | ✅ 已有 1,039 筆；1,032 筆與人口 join |
- 半徑參數：預設 2.5 km，設為可調。
- 座標系：面積與交集計算須先投影到等面積投影（如 TWD97 / EPSG:3826），不要在經緯度上算面積。
- 已知近似：里內青年「面積均勻分布」假設；圓形 buffer 用直線距離而非路網 / 通勤時間
  （此為刻意選擇，路網 isochrone 留待後續評估）。
- 目前結果：全市 `49.2266230851%`，狀態 `partial`；9 個據點通過座標驗證、0 個據點排除，里級人口 join 不完整是 partial 原因。沒有座標的據點會保留但排除，不當成 0 覆蓋。

### 2.2 青年里長占比

- 定義：18–35 歲村里長當選人數 / 該區 V1 當選席次。
- 計算式：`youth_borough_chief_ratio(區) = 18–35 歲當選村里長人數 / 該區 V1 當選席次`。
- 需要：中選會里長選舉當選名單（含出生年）、各區村里數。
- 資料源：中選會選舉資料庫（里長 / 村里長選舉）；村里數用戶政村里清單或
  `data-pipeline/config/districts.json` 擴充。
- 粒度：區。更新：每屆里長選舉後（約 4 年）。

### 2.3 YRR（Youth Representation Ratio）

- 定義：青年當選席次佔比 ÷ 青年人口佔比。
- 計算式：
  `YRR(區) = (18–35 歲青年當選席次 / V1 當選席次) ÷ (18–35 歲人口 / 全人口)`
- 需要：當選人年齡與選舉人數按年齡；目前沒有年齡別選舉人資料，因此使用同年 `population` 的青年人口比例，輸出 `denominator_type=population_proxy`、`proxy=true`。
- 資料源：中選會 V1 + 戶政 `population`。
- 粒度：區；T1 不轉換成行政區。

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
| 提案、討論、決議、處理層級 | `youth_council_minutes` PDF collector | ✅ 55 筆解析列；以去重後議題計算 |
| 提案列管 / 追蹤清單（階段 4、5 的狀態、結案日） | 青年局內部列管表（Excel / 內部系統匯出） | ❌ 需青年局提供 |

- 目前近 3 個可用 ROC 年度（110、112、114）去重後輸出第 1–3 階為 50、50、5；第 4–5 階為 `null`，`status=partial`，原因為沒有列管表。`escalated` 另計。

### 時間尺度

- 預設：近 3 個可用 ROC 年度；目前 `term` 欄位為空，因此不假設本屆屆次。
- 期間策略：`all_available`（隨 `youth_council_minutes`），analytics 依屆次 / 年度彙總。
- 粒度：`organization`（新北市青年局），非 29 區。

### analytics 輸出範例

```json
{
  "metric_id": "youth_proposal_funnel",
  "coverage_scope": "meeting_records",
  "source_period": ["110", "112", "114"],
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

- 「提案受理」目前明確定義為公開會議紀錄中可辨識且去重後的議題母體，不宣稱涵蓋所有青年局管道。
- 階段 4、5 幾乎一定要青年局的列管表；純靠會議記錄只能推到「獲採納」。
- 決議文字判定 `採納 / escalated` 的關鍵字表需人工校對（同 §5）。

---

## 4. 資源投入與產出（`ResourceIoCharts`）

三張圖：補助地區分布（長條）、補助金額年度趨勢（折線）、青年局預算執行率（環圈）。

### 4.1 補助地區分布 + 4.2 補助金額年度趨勢

- 前端：`GRANT_BY_AREA`（7 個寫死值）、`GRANT_TREND`（8 個寫死值）。
- 實際資料源：**青年局對民間團體補（捐）助明細**
  - 依《預算法》第 91 條，各機關補助民間團體須公開；新北市主計處 / 青年局預決算頁面
    通常有「對民間團體及個人補助」清單（PDF / Excel）。
  - 已接官方青年局年度公告列表：<https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?id=112&module=youth0008>，逐年下載 PDF 並保存 artifact。
- 需要欄位：受補助單位、補助 / 捐助金額、用途、年度、（受補助單位或計畫執行）行政區。
- 計算式：
  - 補助地區分布：`Σ 補助金額 group by 行政區`（同一年度）
  - 年度趨勢：`Σ 補助金額 group by 年度`
- 粒度：區（需能從受補助單位地址或計畫地點判定；判不到則 `district_id=null`）。
- 期間策略：`all_available`（PDF 內含年度欄位）。目前 live 解析 111–115 共 110 筆，ROC 110 沒有來源列；官方 PDF 未提供計畫地或受補助單位地址，因此來源全量 110 筆均為 `district_id=null`、`geo_basis=unresolved`。在 ROC 110–114 的參政年度序列中，納入 111–114 的 83 筆，年度趨勢仍可算，地區分布為 unavailable／partial。

### 4.3 青年局預算執行率

- 前端：寫死 `BUDGET_EXECUTION = 92`。
- 計算式：`預算執行率 = 決算實現數 / 法定預算數 × 100%`（可分「歲出」總額或「青年發展業務」）。
- 現有資料：`youth_budgets`（`data/curated/youth_budgets/all.json`）
  - 已接預算與決算：ROC 112–116 的「計畫及預算統計表」，以及目前可解析的 ROC 113「歲出機關別決算表」；111／112 決算 PDF 已保存但為影像型待 OCR。
  - 預算欄位：`budget_year_roc`、`document_status`、`row_type`(total/detail)、`business_plan`、
    `value`（單位 `TWD_thousand`）、`budget_ratio_percent`。
  - 決算欄位：`budget_amount`、`realized_amount`、`payable_amount`、`reserved_amount`、`settlement_amount`、`surplus_amount`。
  - `geo_level=organization`，**不可拆到 29 區**，`youth_eligibility=context_only`。
- 狀態：analytics 已依 `realized_amount / legal_budget_amount × 100` 計算；目前 ROC 113 可得執行率，110、111、112、114 保留 `null`，111／112 影像型 PDF 原始 artifact 與解析失敗紀錄仍保留。
- 期間策略：`annual`；與 `youth_budgets` 同層級（organization）。
- 不新增另一個 dataset；執行率保留在 `participation.json` 與首頁 analytics 的 annual budget execution 結果。

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
| `youth_service_points`（青年服務據點） | 青年局清單 + 官方門牌座標／固定地址參照 | `snapshot` | 服務涵蓋率、整體服務涵蓋率 | ✅ 已完成 |
| `village_boundaries`（村里界多邊形） | 國土測繪中心 / 新北 open data | `snapshot` | 服務涵蓋率（buffer × 里界面積分攤） | ✅ 已完成 |
| `youth_council_minutes`（青年局會議記錄 PDF） | 青年局官網「會議紀錄」列表頁 | `all_available`（PDF artifacts ＋ 年度） | 青年提案落實進度、青年關注議題文字雲（高權重訊號） | ✅ 已完成 |
| `youth_proposal_tracker`（青年提案列管表） | 青年局內部列管表匯出（Excel / 系統） | `snapshot` | 青年提案落實進度（階段 4、5） | 中 |
| `youth_grants`（對民間團體補助明細） | 青年局年度公告 PDF | `all_available` | 補助地區分布、補助金額趨勢 | ✅ 已完成；地區欄位待官方地址 |
| `youth_budget_execution`（決算 / 執行率） | 新北市政府決算書 | `annual` | 預算執行率 | ✅ 沿用 `youth_budgets` analytics |
| `join_proposals`（join.gov.tw 提點子 / 附議） | data.gov.tw 開放資料集 or join.gov.tw 列表頁 | `all_available`（含年度欄位） | 青年關注議題文字雲 | 低 |

目前已完成：
- `population_villages` 提供里級 `youth_18_35_total`，服務涵蓋率以里界面積比例分攤。
- `src/analytics/youth_participation.py` 整合青年參選率、V1 比例／YRR、服務涵蓋率、提案漏斗、補助趨勢、預算執行率與文字雲。
  - 服務涵蓋率需要幾何運算依賴（如 `shapely`）做 buffer 聯集與里界交集面積。
  - `youth_proposal_funnel` 讀 `youth_council_minutes` ＋ `youth_proposal_tracker`，
    依關鍵字表判定各案階段。
  - `youth_topic_weight` 需要中文斷詞依賴（jieba / CKIP）＋ 青年議題同義詞表，並讀取
    `join_proposals` 與 `youth_council_minutes` 兩個 curated 輸出合流計算。

---

## 8. 附錄：目前 pipeline 可直接用於本頁的資料

| dataset | 用途 | 限制 |
|---|---|---|
| `population` | 各區青年人口（青年參選率、YRR 分母） | 2014／2018 歷史人口缺少時，該屆結果為 `null` |
| `elections` | 2014／2018／2022 新北 T1＋V1 候選人原始資料 | V1 產生 29 區結果；T1 保留選區、不硬套行政區 |
| `youth_service_points` | 青年局青創基地名稱、地址與座標 | 9 筆均有驗證座標；服務結果因 1,032／1,039 里人口 join 標 `partial` |
| `youth_budgets` | 青年局年度預算、可解析的 113 年決算欄位 | organization 層級、執行率仍由 analytics、不可拆 29 區；111／112 決算待 OCR |
| `youth_grants` | 青年局對民間團體補助 PDF | 111–115 共 110 筆；PDF 沒有地址，行政區分布 unresolved |

### 8.1 已完成 analytics 與 snapshot

執行 `run_analytics.py --metric youth_participation` 會輸出：

- `data/analytics/youth_participation/all.json`
- `data/quality/analytics_youth_participation.json`

公開 analytics 包含 `elections.v1_borough_chief`、`elections.youth_candidacy`、
`service_coverage`、`proposal_funnel`、`grants`、`budget` 與 `topics`。`topics`
內嵌年度 `youth_topic_weight` 與 `youth_keyword_frequency`，原本兩份 standalone
analytics 仍保留。公開 JSON 不包含 `raw_record`／`raw_records`。

可加 `--publish --snapshot-id dev-youth-participation-YYYYMMDD`，產生：

```text
data/analytics/published/{snapshot_id}/manifest.json
data/analytics/published/{snapshot_id}/dashboard_overview.json
data/analytics/published/{snapshot_id}/district_details.json
data/analytics/published/{snapshot_id}/analyses/participation.json
data/analytics/published/current.json
```

`manifest.json.artifacts.analyses.participation` 指向參政 artifact；T1 不會被
塞入 29 區 `districts`。缺值、`proxy`、`partial` 與 `unavailable` 均保留。

其餘 dataset（就業、居住、交通、教育、生育等）與青年參政頁無直接關係。
