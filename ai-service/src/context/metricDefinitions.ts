/**
 * 複合指標的算法定義 —— 讓模型知道「這個分數是怎麼算出來的」。
 *
 * ## 為什麼需要
 *
 * 實測「為什麼樹林區的青年機會指數能排進那麼高的名次？」，模型答得很好，
 * 但最後誠實地說：
 *
 * > 各子分數的合成權重本次資料未揭露，無法精確說明各維度對總分的貢獻比例。
 *
 * 那句話是對的 —— analytics 快照裡沒有任何 weight 欄位。但權重其實存在，
 * 在 `data-pipeline/config/homepage_analytics.json`。有了它，模型可以算出
 * 「樹林的就業子分數 75.80 × 0.25 = 18.95 分，是五項裡貢獻最大的」，
 * 而不是只能說「就業子分數最高」。
 *
 * ## 為什麼不放在每一筆 evidence 的 `computation` 裡
 *
 * **公式是「每個指標一份」，不是「每個行政區一份」。** `opportunityIndex` 的
 * 公式對 29 區完全相同，塞進每筆 evidence 等於同一串字重複 29 次。
 * 以 YOI 公式約 60 字估：
 *
 * - 每筆帶公式：60 字 × 29 區 × 6 個複合指標 ≈ 10,000 字
 * - 每個指標講一次：60 字 × 6 ≈ 360 字
 *
 * 這跟 `buildComputation()` 刻意不放上游 dataset 清單是同一個理由
 * （實測那一段在 477 筆 evidence 下多了 4 萬字元）。
 *
 * ## 過濾是必要的
 *
 * `formatMetricDefinitions()` 只輸出**這次 evidence 真的出現過**的指標。
 * evidence 裡通常只有 10–20 種指標，而定義表會隨 pipeline 成長 ——
 * 無條件全印等於為沒用到的指標付 token。
 */
import {
  ANALYTICS_CONFIG_VERSION,
  FAFI,
  NORMALIZATION,
  SERVICE_RADIUS_M,
  YOI_WEIGHTS,
} from './generated/analyticsConfig.js';
import type { AiEvidence } from '../types/aiEvidence.js';

export interface MetricDefinition {
  /** 一行公式或算法說明。 */
  formula: string;
  /** 正規化、收縮估計這類會影響解讀的處理。 */
  normalization?: string;
  /**
   * 解讀這個數字時必須知道的限制。
   *
   * 這裡刻意放「口徑陷阱」而不是一般性的免責聲明：例如 YOI 的 salary 子分數
   * 來自求才職缺（全年齡），跟 `adjusted_youth_wage`（青年適用）不是同一件事。
   * 模型看不到這句的話，會把兩者混著講。
   */
  caveat?: string;
}

const yoiFormula =
  `job×${YOI_WEIGHTS.job} + salary×${YOI_WEIGHTS.salary} + talent×${YOI_WEIGHTS.talent}` +
  ` + housing×${YOI_WEIGHTS.housing} + transport×${YOI_WEIGHTS.transport}`;

const yoiNormalization =
  `五個子分數各自先做 ${NORMALIZATION.method} 正規化（0–100）；` +
  `某個面向缺資料時該子分數以 ${NORMALIZATION.constantValue} 代入`;

const fafiFormula =
  `daycareCoverage×${FAFI.weights.daycareCoverage}% + housing×${FAFI.weights.housing}%` +
  ` + salary×${FAFI.weights.salary}%`;

/**
 * metricId（葉名）→ 算法定義。
 *
 * 權重數字全部來自 `generated/analyticsConfig.ts`（pipeline config 的投影），
 * **沒有任何一個是手寫的**。文字說明是手寫的，但那些是口徑與限制，
 * 不是會隨 config 變動的數值。
 */
export const METRIC_DEFINITIONS: Readonly<Record<string, MetricDefinition>> = {
  opportunityIndex: {
    formula: `青年機會指數（0–100）= ${yoiFormula}`,
    normalization: yoiNormalization,
    caveat:
      'salary 子分數的母體是求才職缺（全年齡，context_only），' +
      '跟 adjusted_youth_wage（青年適用）不是同一個口徑，不可混著講。',
  },
  'yoiComponents.job': {
    formula: `機會指數的就業子分數（0–100），在總分裡的權重 ${YOI_WEIGHTS.job}`,
    normalization: yoiNormalization,
  },
  'yoiComponents.salary': {
    formula: `機會指數的薪資子分數（0–100），在總分裡的權重 ${YOI_WEIGHTS.salary}`,
    normalization: yoiNormalization,
    caveat: '母體是求才職缺（全年齡），不是青年專屬薪資。',
  },
  'yoiComponents.talent': {
    formula: `機會指數的人才子分數（0–100），在總分裡的權重 ${YOI_WEIGHTS.talent}`,
    normalization: yoiNormalization,
  },
  'yoiComponents.housing': {
    formula: `機會指數的住宅子分數（0–100），在總分裡的權重 ${YOI_WEIGHTS.housing}`,
    normalization: yoiNormalization,
    caveat: '分數越高代表居住負擔越輕；房價與租金越高，這個子分數越低。',
  },
  'yoiComponents.transport': {
    formula: `機會指數的交通子分數（0–100），在總分裡的權重 ${YOI_WEIGHTS.transport}`,
    normalization: yoiNormalization,
  },
  yoiRaw: {
    formula: '機會指數正規化前的原始加權值',
    normalization: yoiNormalization,
  },
  fafiScore: {
    formula: `家庭友善指數（0–100）= ${fafiFormula}`,
    normalization: `各子項先 ${NORMALIZATION.method} 正規化`,
  },
  daycareCoverageScore: {
    formula: `家庭友善指數的托育子項，權重 ${FAFI.weights.daycareCoverage}%`,
  },
  housingScore: {
    formula: `家庭友善指數的居住子項，權重 ${FAFI.weights.housing}%`,
  },
  wageScore: {
    formula: `家庭友善指數的薪資子項，權重 ${FAFI.weights.salary}%`,
  },
  salary_median_shrunk: {
    formula: '職缺薪資中位數，經收縮估計',
    normalization:
      `收縮參數 k=${FAFI.salaryShrinkageK}：樣本數少的行政區，估計值會往全市水準拉，` +
      '避免少數幾筆高薪職缺把中位數推高',
    caveat:
      '跟 salary_median（未收縮）並列時，兩者差距大就代表該區樣本數少、' +
      '原始中位數不穩定 —— 這正是判斷「排名是否可信」的線索。',
  },
  serviceCoverageRate: {
    formula: '青年服務據點涵蓋率 = 服務半徑內的青年人口 ÷ 該區青年人口',
    caveat: '半徑是直線距離，不是實際交通可及性。',
  },
  daycareCoverage: {
    formula: '托育服務涵蓋率 = 服務半徑內的目標人口 ÷ 該區目標人口',
    caveat: '半徑是直線距離，不是實際交通可及性。',
  },
  rent_wage_ratio: {
    formula: '租金佔薪資比例 = 租金中位數 ÷ 薪資中位數',
    caveat: '分子分母都是全體統計（context_only），不是青年專屬。',
  },
  yrr: {
    formula: '青年參政代表性比 = 青年當選比例 ÷ 青年人口比例',
    caveat: '1 代表席次與人口比相符，小於 1 代表青年在席次上代表性不足。',
  },
};

/** 涵蓋率的判定半徑。是 config 值而不是公式的一部分，所以單獨一行。 */
export const COVERAGE_RADIUS_NOTE = `涵蓋率的判定半徑取自資料管線設定：直線距離 ${SERVICE_RADIUS_M} 公尺。`;

/**
 * 組出 prompt 上的「指標定義」段落。
 *
 * 只輸出這批 evidence 真的用到的指標；一個都沒用到時回 null，
 * 呼叫端就不必在 prompt 上留一個空標題。
 */
export function formatMetricDefinitions(evidence: readonly AiEvidence[]): string | null {
  const present = new Set<string>();
  for (const item of evidence) {
    // metricId 可能帶 `#識別字`（keywords[].weight#居住正義），定義是看前面那段。
    const base = item.metricId.split('#')[0]!;
    if (METRIC_DEFINITIONS[base] !== undefined) {
      present.add(base);
    }
  }
  if (present.size === 0) {
    return null;
  }

  const lines = [
    `指標算法（資料管線設定 v${ANALYTICS_CONFIG_VERSION}；每個指標只講一次，不隨行政區重複）`,
    '這些是複合指標的計算方式。回答「為什麼這個分數高／低」時可以用它說明是哪個子項在拉抬或拖累，',
    '包含用權重算出各子項的貢獻（子分數 × 權重）。但**不可**用它去推算 evidence 裡沒有的數字。',
    '',
  ];
  for (const metricId of [...present].sort()) {
    const definition = METRIC_DEFINITIONS[metricId]!;
    lines.push(`- ${metricId}：${definition.formula}`);
    if (definition.normalization !== undefined) {
      lines.push(`  正規化：${definition.normalization}`);
    }
    if (definition.caveat !== undefined) {
      lines.push(`  ⚠️ ${definition.caveat}`);
    }
  }
  return lines.join('\n');
}
