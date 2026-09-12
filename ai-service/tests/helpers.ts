import type { EvidenceReview, StructuredOutput } from '../src/types/structuredOutput.js';
import type { AiEvidence, AiRequestContext } from '../src/types/aiEvidence.js';
import type { WebFinding } from '../src/types/webFinding.js';

/**
 * 測試用的共用建構函式。
 *
 * 存在理由：`AiEvidence` 有 20 幾個欄位、`StructuredOutput` 有 9 個，
 * 每個測試檔各寫一份完整字面值的話，contract 一改就要改五個檔案 ——
 * 而那正是「改 contract 很痛所以乾脆不改」的開始。
 */

const DISCLAIMER = 'AI 建議屬於政策輔助資訊，不代表政府正式政策決定。';

/** 一筆真實形狀的 population evidence（欄位值取自實際 curated 輸出）。 */
export function makeEvidence(overrides: Partial<AiEvidence> = {}): AiEvidence {
  return {
    evidenceId: 'population:11507:1:youth_18_35_total',
    dataset: 'population',
    source: 'moi_household_registration',
    sourceRecordId: 'population:65000010:2026-07',
    sourceUrl: null,
    sourceKind: 'dataset',
    geoLevel: 'district',
    districtId: '65000010',
    districtName: '板橋區',
    period: '11507',
    periodStart: '2026-07-01',
    periodEnd: '2026-07-31',
    periodType: 'month',
    metricId: 'youth_18_35_total',
    metricSource: 'metric_id',
    value: 106473,
    unit: 'people',
    ageScope: 'derived_18_35',
    youthEligibility: 'eligible',
    qualityFlags: [],
    sourcePath: 'curated/population.json',
    fetchedAt: '2026-09-12T01:56:04.525401+00:00',
    ...overrides,
  };
}

export function makeEvidenceReview(overrides: Partial<EvidenceReview> = {}): EvidenceReview {
  return {
    availableMetrics: ['youth_18_35_total（板橋區／11507）'],
    youthSpecificMetrics: ['youth_18_35_total'],
    contextOnlyMetrics: [],
    missingForQuestion: [],
    ...overrides,
  };
}

/**
 * 一份通過所有不變式的 StructuredOutput。
 *
 * 預設是 `sufficient` + `missingForQuestion: []` + 有結論有 basis，
 * 這樣每個測試只要覆寫它關心的那一兩個欄位，不會被無關的不變式擋住。
 */
export function makeOutput(overrides: Partial<StructuredOutput> = {}): StructuredOutput {
  return {
    evidenceReview: makeEvidenceReview(),
    dataSufficiency: 'sufficient',
    // 六塊格式（explain / policyCopilot）沒有使用者問題，所以 answer 是 null。
    // Q&A 的預設用 makeQaOutput()。
    answer: null,
    issues: ['板橋區青年人口高於三重區，但職缺資料粒度不足以判斷機會是否相稱。'],
    strengths: [],
    resourceGaps: [],
    policyDirections: [],
    basis: [{ evidenceId: 'population:11507:1:youth_18_35_total', note: '引用青年人口指標' }],
    webReferences: [],
    limitations: [],
    disclaimer: DISCLAIMER,
    ...overrides,
  };
}

/** 一筆網路搜尋結果。 */
export function makeWebFinding(overrides: Partial<WebFinding> = {}): WebFinding {
  return {
    findingId: 'web:1',
    title: '新北市青年局 - 青年創業基地',
    url: 'https://www.youth.ntpc.gov.tw/example',
    snippet: '新北市青年局營運多處青年創業基地，提供進駐空間與輔導資源。',
    publishedDate: null,
    retrievedAt: '2026-09-12T05:00:00.000Z',
    ...overrides,
  };
}

/** 預設關閉上網搜尋的請求 context。 */
export function makeRequestContext(
  overrides: Partial<AiRequestContext> = {},
): AiRequestContext {
  return {
    question: null,
    focusDistrict: '板橋區',
    focusArea: 'population',
    evidence: [makeEvidence()],
    knownLimitations: [],
    webFindings: [],
    webSearch: { enabled: false, contextSize: 'low' },
    ...overrides,
  };
}

export { DISCLAIMER };

/**
 * 一份通過所有不變式的 **Q&A** 輸出。
 *
 * 跟 `makeOutput()` 的差別就是 Q&A 格式的差別：`answer` 有內容、四塊留空。
 * 這是「純查值問題」的正常形狀 —— 使用者問一個數字，就回一句話加引用，
 * 不需要政策分析。
 */
export function makeQaOutput(overrides: Partial<StructuredOutput> = {}): StructuredOutput {
  return {
    evidenceReview: makeEvidenceReview(),
    dataSufficiency: 'sufficient',
    answer: '板橋區 18–35 歲青年人口為 106,473 人（內政部戶政司戶籍人口統計）。',
    issues: [],
    strengths: [],
    resourceGaps: [],
    policyDirections: [],
    basis: [{ evidenceId: 'population:11507:1:youth_18_35_total', note: '引用青年人口指標' }],
    webReferences: [],
    limitations: [],
    disclaimer: DISCLAIMER,
    ...overrides,
  };
}
