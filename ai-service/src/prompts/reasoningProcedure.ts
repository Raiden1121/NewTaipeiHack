/**
 * LLM 的思考程序。
 *
 * 為什麼要有這個檔案：原本的 prompt 只有「規則 + 範例 + 你答」。規則幾乎全是
 * 禁止事項（不可推算、不可捏造），但**沒有規定順序**。結果是模型可以先寫出結論，
 * 再回頭找 evidence 湊 basis —— 那個順序寫出來的東西表面上合規，實際上是
 * 先有立場再找證據。
 *
 * 所以這裡規定的是「先盤點、再判斷充足度、最後才下結論」這個順序，
 * 並且把盤點結果變成**必須輸出的欄位**（`evidenceReview`）而不是心裡想想就好。
 * 理由：
 * 1. 有輸出才驗得到。`StructuredOutputSchema` 可以檢查盤點結果與
 *    `dataSufficiency` 是否自相矛盾（見那邊的 superRefine）。
 * 2. `evidenceReview` 在 schema 裡排第一個。JSON 是依欄位順序生成的，
 *    所以把盤點放最前面，模型會真的先盤點才寫結論。
 * 3. 稽核價值：出問題時可以看出模型是「資料判讀錯」還是「有資料但推論錯」。
 */

/** 六塊輸出之前必須走完的思考步驟。 */
export const REASONING_PROCEDURE = `
思考程序（依序執行，不可跳步，也不可先寫結論再回頭找依據）：

【第 1 步：盤點 evidence】先把上面的 evidence 清單讀完一遍，特別注意每一筆的
  youthEligibility（eligible 才能當青年專屬數據解讀，context_only / proxy_only 只能當脈絡）
  與 metricSource（record_field 是單筆、不代表全區；analytics_metric 是全區彙總指標）。
  這一步只做描述，不做判斷。
  指標清單由系統自動盤點，**你不需要也不能把指標逐條列出來**。
  evidenceReview 你只要填一個欄位：
  - missingForQuestion：要回答眼前這個問題，還缺哪些資料。沒有缺就填空陣列。

【第 2 步：判斷 dataSufficiency】依下列規則，不要憑感覺：
  - insufficient：evidence 完全無法回答被問的問題（例如問就業，但只有人口資料）。
    此時 missingForQuestion 必須非空，且四塊結論必須全部留空。
  - partial：部分面向有資料、部分缺漏。只要 missingForQuestion 非空就至少是 partial，
    不可以是 sufficient。
  - sufficient：問題涵蓋的每個面向都有對應 evidence，且沒有需要保留的解讀限制。
    這是最少見的情況 —— 覺得是 sufficient 之前，先再想一次真的沒有缺什麼嗎。

【第 3 步：若為 insufficient】只寫 limitations 說明缺什麼，然後停止。
  不要因為「總得說點什麼」而寫出沒有依據的分析。誠實說無法回答，比硬答有價值。

【第 4 步：若為 partial 或 sufficient】才開始寫四塊結論。每一條都必須：
  - 指得出依據，並加進對應的陣列：
      資料管線的指標 → basis（用 evidenceId）
      網路搜尋結果   → webReferences（用 findingId）
    完全沒有引用的論點一律不可寫出來。
  - 只使用 contextOnlyMetrics 的論點，不可寫成青年專屬的結論

【第 4b 步：只有網路資料、沒有任何 evidence 時】
  這種情況是允許的（使用者開啟了上網搜尋，而資料管線沒有相關指標），但：
  - basis 留空陣列，不要把 findingId 塞進 basis
  - 每一條論點都要在文字裡寫明「根據網路資料」，不可寫成官方統計的語氣
  - limitations 必須有一條明確說明「本次沒有資料管線的官方統計，以下內容僅來自網路搜尋」
  - dataSufficiency 最多只能是 partial，不可以是 sufficient

【第 5 步：自我檢查】輸出前逐項確認：
  □ 四塊裡每一條都能在 basis 找到對應的 evidenceId，或在 webReferences 找到 findingId？
  □ 若 basis 為空（只有網路資料），limitations 有明確說明「沒有官方統計、僅來自網路」？
  □ basis 的每個 evidenceId 都真的出現在上面的 evidence 清單裡（沒有自己組的）？
  □ 有沒有把多筆 evidence 加總、平均、相除，或算出成長率？（都不允許）
  □ 數字與單位都照抄 evidence 的原值？沒有自行換算單位？
  □ missingForQuestion 非空時，dataSufficiency 不是 sufficient？
  □ 每個 basis 的 note 都寫出資料提供者名稱？
  □ limitations 只寫了**新的**限制，沒有重複抄寫 context 已經給的既知限制？
  □ disclaimer 有固定字樣？
`.trim();

/**
 * 單位處理規則，獨立出來是因為這是**實測抓到的真實錯誤**，不是預防性規則。
 *
 * 實際發生過：evidence 是 `value=220101, unit=TWD_thousand`（22 萬千元），
 * 模型輸出「約 2 億 2,010 萬千元」—— 它把千元換算成元（換算對了），
 * 但單位標籤沿用了原本的「千元」，變成差 1000 倍。
 *
 * 數字對、單位錯，在政策場景是很嚴重的錯誤，而且看起來很專業所以不容易被抓到。
 * 最保險的做法是根本不要換算。
 */
export const UNIT_HANDLING_RULES = `
單位處理（這是實際發生過的錯誤，請特別小心）：
1. **直接使用 evidence 的 unit 原值，不要自行換算單位。** 例如 unit=TWD_thousand
   就寫「220,101 千元」，不要換算成「2 億 2,010 萬元」。
2. 如果為了讓讀者好理解而必須換算，必須同時寫出原值與換算後的值，
   例如「220,101 千元（約 2.2 億元）」，讓人可以自己核對。
   絕對不要只寫換算後的值，也不要換算後還沿用原本的單位。
3. unit 是 null 的時候，不要自己猜單位是什麼，直接說明這筆資料沒有單位資訊。
4. 常見單位對照：TWD_thousand=新臺幣千元、people=人、positions=職位數、
   TWD_per_month=每月新臺幣元、hours=小時、person_times=人次。
`.trim();
