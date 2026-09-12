import { describe, expect, it } from 'vitest';
import { StructuredOutputSchema, findUnknownEvidenceIds } from '../src/types/structuredOutput.js';
import { AiContextSchema } from '../src/types/aiEvidence.js';
import {
  FEW_SHOT_EXAMPLE_CONTEXT,
  FEW_SHOT_EXAMPLE_OUTPUT,
  formatFewShotExample,
} from '../src/prompts/fewShotExample.js';
import { MEASURE_FIELDS_BY_DATASET } from '../src/context/curatedRecord.js';

/**
 * 放進 prompt 教模型的範例，本身也要守規矩 —— 範例違規的話，模型會照著違規。
 */
describe('few-shot example', () => {
  it('example context 符合 AiContextSchema', () => {
    expect(() => AiContextSchema.parse(FEW_SHOT_EXAMPLE_CONTEXT)).not.toThrow();
  });

  it('example output 符合 StructuredOutputSchema', () => {
    expect(() => StructuredOutputSchema.parse(FEW_SHOT_EXAMPLE_OUTPUT)).not.toThrow();
  });

  it('basis 只引用 example context 裡真的存在的 evidenceId', () => {
    const knownIds = FEW_SHOT_EXAMPLE_CONTEXT.evidence.map((item) => item.evidenceId);

    expect(findUnknownEvidenceIds(FEW_SHOT_EXAMPLE_OUTPUT, knownIds)).toEqual([]);
  });

  it('limitations 不是空的：範例要示範「誠實講缺什麼」，不能只示範好的一面', () => {
    expect(FEW_SHOT_EXAMPLE_OUTPUT.limitations.length).toBeGreaterThan(0);
  });

  it('範例把既知限制原封不動抄進 limitations，示範這個行為', () => {
    for (const note of FEW_SHOT_EXAMPLE_CONTEXT.knownLimitations) {
      expect(FEW_SHOT_EXAMPLE_OUTPUT.limitations).toContain(note);
    }
  });

  it('示範的是 partial 而不是 sufficient —— 部分能答才是實際最常見的情況', () => {
    expect(FEW_SHOT_EXAMPLE_OUTPUT.dataSufficiency).toBe('partial');
  });
});

/**
 * 範例的 period 用 `00000`（不是合法民國期間），所以範例 evidenceId 永遠不會跟
 * 真實 evidenceId 撞號。這樣萬一模型誤引用範例 ID，`runFeature` 的驗證會抓到，
 * 而不是讓一個看起來合理的假引用混過去。
 */
describe('範例 evidenceId 不會跟真實資料撞號', () => {
  it('所有範例 evidenceId 的 period 段都是 00000', () => {
    for (const item of FEW_SHOT_EXAMPLE_CONTEXT.evidence) {
      expect(item.evidenceId.split(':')[1]).toBe('00000');
      expect(item.period).toBe('00000');
    }
  });

  it('evidenceId 格式跟 context builder 產生的一致：dataset:period:index:metricId', () => {
    for (const item of FEW_SHOT_EXAMPLE_CONTEXT.evidence) {
      const parts = item.evidenceId.split(':');
      expect(parts).toHaveLength(4);
      expect(parts[0]).toBe(item.dataset);
      expect(parts[3]).toBe(item.metricId);
    }
  });
});

/**
 * 範例用真實的 metricId 才有教學價值。如果範例裡的欄位名是編的，
 * 模型學到的詞彙就跟實際 evidence 對不上。
 */
describe('範例使用的 metricId 是真實存在的', () => {
  it('record_field 類的 metricId 必須出現在 MEASURE_FIELDS_BY_DATASET', () => {
    const recordFieldExamples = FEW_SHOT_EXAMPLE_CONTEXT.evidence.filter(
      (item) => item.metricSource === 'record_field',
    );
    expect(recordFieldExamples.length).toBeGreaterThan(0);

    for (const item of recordFieldExamples) {
      const fields = MEASURE_FIELDS_BY_DATASET[item.dataset]?.map((spec) => spec.field) ?? [];
      expect(fields).toContain(item.metricId);
    }
  });
});

describe('formatFewShotExample', () => {
  it('同時包含範例輸入與輸出', () => {
    const formatted = formatFewShotExample();

    expect(formatted).toContain('population:00000:0:youth_18_35_total');
    expect(formatted).toContain('"issues"');
    expect(formatted).toContain('"dataSufficiency"');
    expect(formatted).toContain('disclaimer');
  });

  it('明確告訴模型不要引用範例的 evidenceId', () => {
    expect(formatFewShotExample()).toContain('不要引用它們');
  });

  it('包含既知限制區塊，示範這個欄位長什麼樣', () => {
    expect(formatFewShotExample()).toContain('已知的資料限制');
  });
});
