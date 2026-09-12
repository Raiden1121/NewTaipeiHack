import { describe, expect, it, vi } from 'vitest';
import { MockBedrockClient, type BedrockClient } from '../src/bedrock/client.js';
import { explainData } from '../src/handlers/explainData.js';
import { policyCopilot } from '../src/handlers/policyCopilot.js';
import { dataQa } from '../src/handlers/dataQa.js';
import { withKnownLimitations } from '../src/handlers/runFeature.js';
import { StructuredOutputSchema, type StructuredOutput } from '../src/types/structuredOutput.js';
import type { AiRequestContext } from '../src/types/aiEvidence.js';
import { makeEvidence, makeEvidenceReview, makeOutput } from './helpers.js';

const evidence = makeEvidence();

const baseContext: AiRequestContext = {
  question: null,
  focusDistrict: '板橋區',
  focusArea: 'population',
  evidence: [evidence],
  knownLimitations: [],
};

/** 回傳固定內容的假 client，用來測 handler 自己的把關邏輯。 */
function stubClient(output: unknown): BedrockClient {
  return {
    description: 'stub',
    invokeStructured: vi.fn(async () => output as StructuredOutput),
  };
}

describe('三個功能的基本路徑（用 MockBedrockClient）', () => {
  const client = new MockBedrockClient();

  it('explainData 回傳符合 schema 的六塊輸出', async () => {
    const { output } = await explainData(client, baseContext);

    expect(() => StructuredOutputSchema.parse(output)).not.toThrow();
    expect(output.basis[0]?.evidenceId).toBe(evidence.evidenceId);
  });

  it('policyCopilot 回傳符合 schema 的六塊輸出', async () => {
    const { output } = await policyCopilot(client, baseContext);

    expect(() => StructuredOutputSchema.parse(output)).not.toThrow();
  });

  it('dataQa 有 question 時正常回應', async () => {
    const { output } = await dataQa(client, { ...baseContext, question: '板橋區青年人口有多少？' });

    expect(() => StructuredOutputSchema.parse(output)).not.toThrow();
  });

  it('dataQa 沒有 question 時要丟錯：這是呼叫端的程式錯誤，不是資料問題', async () => {
    await expect(dataQa(client, { ...baseContext, question: null })).rejects.toThrow(
      'buildDataQaPrompt 需要 context.question',
    );
  });
});

/**
 * 「每個回應都要附資料來源」是這個服務最重要的要求，所以來源跟分析綁在同一個
 * 回傳值裡：拿得到 output 就一定拿得到 sources，不可能忘記。
 */
describe('每個回應都必須附資料來源', () => {
  const client = new MockBedrockClient();

  it('三個功能都回傳 sources', async () => {
    for (const feature of [explainData, policyCopilot]) {
      const result = await feature(client, baseContext);
      expect(result.sources.length).toBeGreaterThan(0);
    }
    const qa = await dataQa(client, { ...baseContext, question: '板橋區青年人口有多少？' });
    expect(qa.sources.length).toBeGreaterThan(0);
  });

  it('sources 帶中文機關名稱與可回溯的檔案路徑', async () => {
    const { sources } = await explainData(client, baseContext);

    expect(sources[0]?.organization).toBe('內政部戶政司');
    expect(sources[0]?.sourcePaths).toContain('curated/population.json');
    expect(sources[0]?.citedEvidenceIds).toContain(evidence.evidenceId);
  });

  it('沒有 evidence 時 sources 是空陣列，而不是編一個來源出來', async () => {
    const { sources, output } = await explainData(client, { ...baseContext, evidence: [] });

    expect(sources).toEqual([]);
    expect(output.dataSufficiency).toBe('insufficient');
  });

  it('模型沒引用到的 evidence 不會出現在 sources 裡', async () => {
    const unusedEvidence = makeEvidence({
      evidenceId: 'job_vacancies:11507:0:position_count',
      dataset: 'job_vacancies',
      source: 'taiwanjobs',
      sourcePath: 'curated/job_vacancies.json',
    });

    // MockBedrockClient 只會引用 prompt 裡第一個 evidenceId。
    const { sources } = await explainData(client, {
      ...baseContext,
      evidence: [evidence, unusedEvidence],
    });

    expect(sources.map((source) => source.sourceId)).toEqual(['moi_household_registration']);
  });
});

/**
 * 計畫書 Phase 1 步驟 7 的防呆測試：餵資料不足的 case，
 * 確認回「資料不足」而不是亂編數字。
 */
describe('資料不足時必須誠實標示，不可亂編（防呆）', () => {
  const client = new MockBedrockClient();
  const spy = vi.spyOn(client, 'invokeStructured');

  it('沒有 evidence 時完全不呼叫模型', async () => {
    spy.mockClear();
    await explainData(client, { ...baseContext, evidence: [] });

    expect(spy).not.toHaveBeenCalled();
  });

  it('沒有 evidence 時回 dataSufficiency=insufficient，且四塊全空', async () => {
    const { output } = await explainData(client, { ...baseContext, evidence: [] });

    expect(output.dataSufficiency).toBe('insufficient');
    expect(output.issues).toEqual([]);
    expect(output.strengths).toEqual([]);
    expect(output.resourceGaps).toEqual([]);
    expect(output.policyDirections).toEqual([]);
    expect(output.basis).toEqual([]);
  });

  it('沒有 evidence 時 limitations 一定要說明原因', async () => {
    const { output } = await explainData(client, { ...baseContext, evidence: [] });

    expect(output.limitations.length).toBeGreaterThan(0);
    expect(output.disclaimer).toContain('不代表政府正式政策決定');
  });

  it('沒有 evidence 但有既知限制時，把限制原因帶出來而不是用泛泛的句子', async () => {
    const { output } = await explainData(client, {
      ...baseContext,
      evidence: [],
      knownLimitations: ['dataset_index 沒有 wages 的條目，本次回應沒有這個資料集可引用。'],
    });

    expect(output.limitations.join('\n')).toContain('wages');
  });

  it('三個功能在沒有 evidence 時行為一致', async () => {
    for (const feature of [explainData, policyCopilot]) {
      const { output } = await feature(client, { ...baseContext, evidence: [] });
      expect(output.dataSufficiency).toBe('insufficient');
    }
    const qa = await dataQa(client, { ...baseContext, evidence: [], question: '哪一區最好？' });
    expect(qa.output.dataSufficiency).toBe('insufficient');
  });
});

/**
 * 模型捏造 evidenceId 是「不可捏造」最常見的違反方式。schema 看不到 context，
 * 所以只能在 handler 這層擋。這也是來源推導的前提：ID 對不上，來源就無從追溯。
 */
describe('捏造 evidenceId 必須被拒絕', () => {
  const fabricated = makeOutput({
    issues: ['板橋區青年人口偏低。'],
    basis: [{ evidenceId: 'population:11507:99:made_up_metric', note: '編的' }],
  });

  it('引用不存在的 evidenceId 時丟錯，並把違規的 ID 放進訊息', async () => {
    await expect(explainData(stubClient(fabricated), baseContext)).rejects.toThrow(
      /population:11507:99:made_up_metric/,
    );
  });

  it('錯誤訊息要說明為什麼拒絕，方便 demo 現場解釋', async () => {
    await expect(explainData(stubClient(fabricated), baseContext)).rejects.toThrow(/無法追溯到真實資料/);
  });
});

/**
 * context builder 確定知道的限制（截斷、缺 dataset、品質旗標）必須出現在輸出裡。
 * 模型漏抄的後果是使用者以為資料是完整的 —— 那比少一句話嚴重得多。
 */
describe('既知限制一定要出現在輸出', () => {
  const knownLimitations = ['job_vacancies 僅取樣 200 筆，實際符合條件共 3896 筆。'];

  it('模型漏抄時由 handler 補回去', async () => {
    const outputWithoutNote = makeOutput({
      dataSufficiency: 'partial',
      evidenceReview: makeEvidenceReview({ missingForQuestion: ['缺就業面向'] }),
      issues: ['板橋區青年人口 106,473 人。'],
      basis: [{ evidenceId: evidence.evidenceId, note: null }],
      limitations: ['其他無關的限制'],
    });

    const { output } = await explainData(stubClient(outputWithoutNote), {
      ...baseContext,
      knownLimitations,
    });

    expect(output.limitations).toContain(knownLimitations[0]);
  });

  it('模型已經改寫過的限制不重複列一次', () => {
    const output = StructuredOutputSchema.parse(
      makeOutput({
        dataSufficiency: 'partial',
        evidenceReview: makeEvidenceReview({ missingForQuestion: ['缺就業面向'] }),
        issues: [],
        basis: [],
        limitations: ['job_vacancies 僅取樣 200 筆'],
      }),
    );

    expect(withKnownLimitations(output, knownLimitations).limitations).toHaveLength(1);
  });
});
