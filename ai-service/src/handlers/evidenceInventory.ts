import { evidenceScopeLabel, type AiEvidence } from '../types/aiEvidence.js';
import type { EvidenceReview } from '../types/structuredOutput.js';

/**
 * 由**程式**盤點這次的 evidence，取代原本要模型逐條列出來的做法。
 *
 * ## 為什麼改成程式算
 *
 * `evidenceReview` 原本四個欄位全部由模型輸出。實測一次 Data Explanation
 * （板橋區、250 筆 evidence、Opus）的輸出組成：
 *
 * | 欄位 | 字元 | 佔比 |
 * |---|---|---|
 * | `evidenceReview` | 4,842 | **35%** |
 * | `basis` | 3,812 | 27% |
 * | `limitations` | 3,469 | 25% |
 * | 四塊分析結論 | 1,510 | **11%** |
 *
 * 也就是說模型花了三分之一的輸出在**重打一份程式已經知道的清單** ——
 * `availableMetrics`、`youthSpecificMetrics`、`contextOnlyMetrics` 這三個欄位，
 * 內容完全來自 `context.evidence` 的 `metricId`、`youthEligibility`、`period`，
 * 沒有任何判斷成分。而延遲是被輸出量決定的，所以那三分之一直接反映在等待時間上。
 *
 * ## 為什麼不是整塊刪掉
 *
 * `evidenceReview` 有兩個真正的價值，都保留下來了：
 *
 * 1. **順序效果。** 它在 schema 裡排第一，而 JSON 是依欄位順序生成的，
 *    所以模型會先面對「這次有什麼資料」再寫結論，而不是先寫結論再回頭湊 basis。
 *    現在它只需要填 `missingForQuestion`，順序效果仍然成立。
 * 2. **可稽核。** 出問題時要分得出是「資料判讀錯」還是「有資料但推論錯」。
 *    程式算的盤點在這件事上**比模型寫的更可靠** —— 它不可能列錯或漏列。
 *
 * `missingForQuestion` 留給模型，因為那是唯一需要判斷的欄位：
 * 「要回答眼前這個問題還缺什麼」取決於問題本身，程式無從得知。
 * 而 `StructuredOutputSchema` 的一致性檢查主要就是綁在這個欄位上
 * （列出缺什麼卻宣稱 sufficient → 擋掉）。
 */
export function buildEvidenceInventory(
  evidence: readonly AiEvidence[],
  missingForQuestion: readonly string[],
): EvidenceReview {
  const available: string[] = [];
  const youthSpecific: string[] = [];
  const contextOnly: string[] = [];

  for (const label of describeEvidence(evidence)) {
    available.push(label.text);
    // 分類直接照 evidence 的 youthEligibility，不做任何推測。
    // 這個欄位的意義在 aiEvidence.ts 有定義：eligible 才可以當青年專屬數據解讀。
    if (label.youthEligibility === 'eligible') {
      youthSpecific.push(label.text);
    } else if (
      label.youthEligibility === 'context_only' ||
      label.youthEligibility === 'proxy_only'
    ) {
      contextOnly.push(label.text);
    }
    // youthEligibility 為 null 時兩邊都不放：它既不能證明是青年資料，
    // 也不該被斷言成「只能當脈絡」。列在 availableMetrics 裡就夠了。
  }

  return {
    availableMetrics: available,
    youthSpecificMetrics: youthSpecific,
    contextOnlyMetrics: contextOnly,
    missingForQuestion: [...missingForQuestion],
  };
}

interface EvidenceLabel {
  text: string;
  youthEligibility: AiEvidence['youthEligibility'];
}

/**
 * 產生「metricId（範圍／期間）」格式的標籤，格式與原本要求模型輸出的一致，
 * 所以前端不需要改。
 *
 * 去重是必要的：同一個 metricId 可能在多筆 evidence 出現（例如同一區同一指標
 * 有多個期間就會各一筆），但盤點清單重複列同一個字串沒有意義。
 */
function describeEvidence(evidence: readonly AiEvidence[]): EvidenceLabel[] {
  const seen = new Map<string, EvidenceLabel>();
  for (const item of evidence) {
    const scope = evidenceScopeLabel(item.districtName, item.geoLevel);
    const text = `${item.metricId}（${scope}／${item.period}）`;
    if (!seen.has(text)) {
      seen.set(text, { text, youthEligibility: item.youthEligibility });
    }
  }
  return [...seen.values()];
}
