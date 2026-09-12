import {
  DISCLAIMER_KEYWORD,
  StructuredOutputSchema,
  type StructuredOutput,
} from '../types/structuredOutput.js';

/**
 * 產生「資料不足」的合法 structured output，**不呼叫模型**。
 *
 * 為什麼不打 LLM：沒有 evidence 卻還是把請求送出去，是最容易產生捏造內容的路徑——
 * 模型手上沒有任何數字，但它仍然會盡力寫出四塊看起來像分析的文字。
 * `ai-service.md` 要求「資料不足時必須標示限制，不能硬答」，最可靠的做法就是
 * 在這種情況下根本不給模型機會。
 *
 * 為什麼不直接丟錯（原本的行為）：對前端來說「這一區這個主題目前沒有資料」是一個
 * 正常且需要顯示的狀態，不是 400 錯誤。回一個 dataSufficiency='insufficient' 的
 * 合法輸出，前端可以照原本的元件渲染，只是內容是誠實的「無法回答」。
 */
export function buildInsufficientDataOutput(reasons: readonly string[]): StructuredOutput {
  const limitations = reasons.length > 0 ? [...reasons] : ['目前沒有可引用的資料，因此無法產生分析。'];

  return StructuredOutputSchema.parse({
    // 這條路徑根本沒有 evidence，所以盤點結果全空是誠實的描述，不是偷懶。
    // missingForQuestion 必須非空（schema 要求 insufficient 時要說得出缺什麼），
    // 就直接用呼叫端給的原因。
    evidenceReview: {
      availableMetrics: [],
      youthSpecificMetrics: [],
      contextOnlyMetrics: [],
      missingForQuestion: limitations,
    },
    dataSufficiency: 'insufficient',
    // 沒有 evidence 時根本不會去搜尋（見 runFeature 的順序說明），所以一定是空的。
    webReferences: [],
    // 四塊全空是 schema 強制的：標示資料不足就不可以同時給實質結論。
    issues: [],
    strengths: [],
    resourceGaps: [],
    policyDirections: [],
    basis: [],
    limitations,
    disclaimer: `目前資料不足，未產生分析內容。AI 建議屬於政策輔助資訊，${DISCLAIMER_KEYWORD}。`,
  });
}

/**
 * 判斷這次請求是否應該走「資料不足」路徑。
 *
 * 條件是**兩種來源都沒有東西**：管線的 evidence 與網路搜尋結果都是空的。
 *
 * 只有網路資料（`evidenceCount === 0` 但 `webFindingCount > 0`）**不算**資料不足 ——
 * 使用者明確開啟了上網搜尋，那就該用網路資料回答。誠實性由 `StructuredOutputSchema`
 * 保證：純網路回答必須在 limitations 說明「沒有資料管線的官方統計支撐」。
 *
 * 刻意不加「少於 N 筆就算不足」這種門檻：那個 N 沒有依據，而且會把
 * 「只有一筆但很關鍵的資料」誤判成不足。資料夠不夠回答特定問題，
 * 交給模型在 dataSufficiency 裡判斷成 partial。
 */
export function shouldReportInsufficientData(
  evidenceCount: number,
  webFindingCount = 0,
): boolean {
  return evidenceCount === 0 && webFindingCount === 0;
}
