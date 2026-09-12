/**
 * 預先算的快取鍵：**輸入內容的指紋**。
 *
 * ## 為什麼不是 `action:行政區:主題:快照id`
 *
 * 因為這個服務的 lambda **收到的是 backend 已經組好的 context**（evidence 直接
 * 在 request body 裡），請求裡沒有快照 id 這個欄位。要用快照 id 當鍵，就得要求
 * backend 多傳一個欄位 —— 那是跨隊的契約改動，而且擋不住真正危險的情況：
 * backend 送來的 evidence 子集跟預先算當時不一樣時，快照 id 仍然相同，
 * 於是會回一份「用別的資料算出來的答案」。
 *
 * 指紋把輸入本身納入雜湊，所以只有輸入完全一致才會命中。代價是命中率取決於
 * 呼叫端有沒有用同樣的方式組 context；沒命中就退回即時計算（正確但慢），
 * 不會回錯答案。**寧可 miss，不要回錯的。**
 *
 * ## 哪些欄位進雜湊
 *
 * - `action`：同一份 evidence 給 explain 和 policyCopilot 會得到不同輸出
 * - `focusDistrict` / `focusArea`：prompt 會提到，也決定 analytics 讀哪些分析
 * - `evidence` 的 `evidenceId` + `value` + `unit`
 * - `knownLimitations`：它會整段進 prompt，也會整段回填到輸出
 * - `webSearch.enabled` / `scope`
 *
 * **`value` 一定要進去。** evidenceId 的格式是
 * `{dataset}:{period}:{scope}:{metricId}`，不含數值 —— 只雜湊 id 的話，
 * 資料管線重算同一期的指標（值變了、id 沒變）會命中舊答案，
 * 那是這個設計最容易出的錯，而且錯得很安靜。
 *
 * ## 哪些欄位刻意不進雜湊
 *
 * - `question`：explain / policyCopilot 沒有使用者問題；Q&A 有問題但**不快取**
 *   （見 `servePrecomputed.ts`），所以不需要它
 * - `webFindings`：網路搜尋結果每次都不一樣，納入等於永遠 miss。快取條目裡
 *   已經記著當時實際用到的網路來源，追溯性不會掉
 */
import { createHash } from 'node:crypto';
import type { AiRequestContext } from '../types/aiEvidence.js';

/** 指紋的輸入形狀。獨立成型別是為了讓測試能直接檢查「哪些欄位被納入」。 */
export interface FingerprintInput {
  action: string;
  focusDistrict: string | null;
  focusArea: string | null;
  evidence: { evidenceId: string; value: number | string | null; unit: string | null }[];
  knownLimitations: string[];
  webSearchEnabled: boolean;
  webSearchScope: string;
}

export function buildFingerprintInput(action: string, context: AiRequestContext): FingerprintInput {
  return {
    action,
    focusDistrict: context.focusDistrict ?? null,
    focusArea: context.focusArea ?? null,
    // 排序讓「同一批 evidence 但順序不同」也能命中。
    // 順序在 prompt 上有意義（優先權），但對「這批資料是什麼」沒有意義，
    // 而呼叫端沒有義務用跟我們一樣的順序。
    evidence: context.evidence
      .map((item) => ({
        evidenceId: item.evidenceId,
        value: item.value,
        unit: item.unit ?? null,
      }))
      .sort((left, right) => left.evidenceId.localeCompare(right.evidenceId)),
    knownLimitations: [...context.knownLimitations].sort(),
    webSearchEnabled: context.webSearch.enabled,
    webSearchScope: context.webSearch.scope,
  };
}

/**
 * 算出指紋（sha256 的十六進位字串）。
 *
 * 用 sha256 而不是隨手寫的字串雜湊：這個值會變成檔名，也會出現在回應裡，
 * 碰撞的後果是「回了別人的答案」。sha256 的碰撞機率可以不必考慮。
 */
export function contextFingerprint(action: string, context: AiRequestContext): string {
  return fingerprintOf(buildFingerprintInput(action, context));
}

export function fingerprintOf(input: FingerprintInput): string {
  return createHash('sha256').update(JSON.stringify(input)).digest('hex');
}
