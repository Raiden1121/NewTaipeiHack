import { describe, expect, it } from 'vitest';
import {
  COVERAGE_RADIUS_NOTE,
  METRIC_DEFINITIONS,
  formatMetricDefinitions,
} from '../src/context/metricDefinitions.js';
import {
  FAFI,
  SOURCE_CONFIG_SNAPSHOT,
  YOI_WEIGHTS,
} from '../src/context/generated/analyticsConfig.js';
import { buildDataQaPrompt } from '../src/prompts/dataQa.js';
import { makeEvidence, makeRequestContext } from './helpers.js';

describe('generated/analyticsConfig', () => {
  /**
   * 權重加起來不是 1 的話，prompt 上「子分數 × 權重 = 貢獻度」的算法就是錯的，
   * 而模型會照著算出一個看起來有理有據的錯數字。
   * 產生腳本會擋，這裡再擋一次（產生出來的檔案是 commit 進版控的）。
   */
  it('YOI 五個權重加起來是 1', () => {
    const sum =
      YOI_WEIGHTS.job +
      YOI_WEIGHTS.salary +
      YOI_WEIGHTS.talent +
      YOI_WEIGHTS.housing +
      YOI_WEIGHTS.transport;
    expect(sum).toBeCloseTo(1, 6);
  });

  it('FAFI 三個權重加起來是 100', () => {
    const sum = FAFI.weights.daycareCoverage + FAFI.weights.housing + FAFI.weights.salary;
    expect(sum).toBe(100);
  });

  /**
   * 產生出來的常數與它記錄的來源快照必須一致 —— 不一致代表有人手改了這個檔案，
   * 而那會讓 `dev:metric-audit` 的漂移偵測失去意義（它比對的是 SOURCE_CONFIG_SNAPSHOT）。
   */
  it('匯出的常數跟記錄的來源快照一致（沒有人手改過）', () => {
    expect(YOI_WEIGHTS.job).toBe(SOURCE_CONFIG_SNAPSHOT.yoi_weights.job);
    expect(YOI_WEIGHTS.housing).toBe(SOURCE_CONFIG_SNAPSHOT.yoi_weights.housing);
    expect(FAFI.salaryShrinkageK).toBe(SOURCE_CONFIG_SNAPSHOT.fafi.salary_shrinkage_k);
    expect(FAFI.weights.daycareCoverage).toBe(
      SOURCE_CONFIG_SNAPSHOT.fafi.weights.daycare_coverage,
    );
  });
});

describe('formatMetricDefinitions', () => {
  it('沒有任何複合指標時回 null（不要在 prompt 留空標題）', () => {
    const evidence = [makeEvidence({ metricId: 'youth_18_35_total' })];
    expect(formatMetricDefinitions(evidence)).toBeNull();
  });

  /**
   * 這是整個設計的重點：公式是「每個指標一份」，不是「每個行政區一份」。
   * 29 區的 opportunityIndex 只能讓公式出現一次，否則同一串字重複 29 次。
   */
  it('同一個指標跨 29 區時，公式只出現一次', () => {
    const evidence = Array.from({ length: 29 }, (_, index) =>
      makeEvidence({
        evidenceId: `analytics:11507:d${index}:opportunityIndex`,
        metricId: 'opportunityIndex',
        districtName: `第${index}區`,
      }),
    );

    const block = formatMetricDefinitions(evidence)!;
    const occurrences = block.split('青年機會指數').length - 1;
    expect(occurrences).toBe(1);
  });

  it('只列出這次 evidence 真的用到的指標', () => {
    const block = formatMetricDefinitions([makeEvidence({ metricId: 'opportunityIndex' })])!;

    expect(block).toContain('opportunityIndex');
    // 沒用到的定義不該出現，否則是為沒引用的指標付 token
    expect(block).not.toContain('fafiScore');
    expect(block).not.toContain('serviceCoverageRate');
  });

  it('權重數字直接來自 config，不是手寫的', () => {
    const block = formatMetricDefinitions([makeEvidence({ metricId: 'opportunityIndex' })])!;

    expect(block).toContain(`job×${YOI_WEIGHTS.job}`);
    expect(block).toContain(`transport×${YOI_WEIGHTS.transport}`);
  });

  it('帶 #識別字 的 metricId 也對得到定義', () => {
    const block = formatMetricDefinitions([
      makeEvidence({ metricId: 'opportunityIndex#板橋區' }),
    ]);
    expect(block).not.toBeNull();
  });

  /**
   * 口徑陷阱要講出來：YOI 的 salary 子分數來自求才職缺（全年齡），
   * 跟 adjusted_youth_wage（青年適用）不是同一件事。
   * 不講的話模型會把兩者混著當「青年薪資」講。
   */
  it('會標明 salary 子分數不是青年專屬', () => {
    const block = formatMetricDefinitions([
      makeEvidence({ metricId: 'yoiComponents.salary' }),
    ])!;
    expect(block).toContain('不是青年專屬');
  });

  it('禁止用公式去推算 evidence 裡沒有的數字', () => {
    const block = formatMetricDefinitions([makeEvidence({ metricId: 'opportunityIndex' })])!;
    expect(block).toContain('不可');
  });

  it('半徑說明取自 config 而不是硬寫', () => {
    expect(COVERAGE_RADIUS_NOTE).toContain(String(SOURCE_CONFIG_SNAPSHOT.service_radius_m));
  });
});

describe('指標算法會進到 prompt', () => {
  it('Q&A 的 prompt 帶上這次用到的指標算法', () => {
    const context = makeRequestContext({
      question: '為什麼樹林區的青年機會指數這麼高？',
      evidence: [makeEvidence({ metricId: 'opportunityIndex', value: 91.8 })],
    });

    const prompt = buildDataQaPrompt(context);

    expect(prompt.user).toContain('指標算法');
    expect(prompt.user).toContain(`job×${YOI_WEIGHTS.job}`);
  });

  it('沒有複合指標時 prompt 不會多一段空的算法說明', () => {
    const context = makeRequestContext({
      question: '板橋區有多少青年？',
      evidence: [makeEvidence({ metricId: 'youth_18_35_total' })],
    });

    expect(buildDataQaPrompt(context).user).not.toContain('指標算法');
  });
});

describe('METRIC_DEFINITIONS 的內容', () => {
  it('五個 yoiComponents 子分數都有定義（缺一個就會有面向解釋不了）', () => {
    for (const facet of ['job', 'salary', 'talent', 'housing', 'transport']) {
      expect(METRIC_DEFINITIONS[`yoiComponents.${facet}`]).toBeDefined();
    }
  });

  it('每個定義都有 formula', () => {
    for (const [metricId, definition] of Object.entries(METRIC_DEFINITIONS)) {
      expect(definition.formula, metricId).toBeTruthy();
    }
  });
});
