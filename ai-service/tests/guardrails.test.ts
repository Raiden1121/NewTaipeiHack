import { describe, expect, it } from 'vitest';
import {
  AI_GUARDRAILS,
  KNOWN_LIMITATIONS_HEADER,
  buildUserPrompt,
  formatEvidenceForPrompt,
  formatKnownLimitations,
} from '../src/prompts/guardrails.js';
import { MockBedrockClient } from '../src/bedrock/client.js';
import type { AiContext, AiEvidence } from '../src/types/aiEvidence.js';

const longFormEvidence: AiEvidence = {
  evidenceId: 'population:11507:1:youth_18_35_total',
  dataset: 'population',
  source: 'moi_household_registration',
  sourceRecordId: 'population:65000010:2026-07',
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
};

const wideFormEvidence: AiEvidence = {
  ...longFormEvidence,
  evidenceId: 'job_vacancies:11507:0:position_count',
  dataset: 'job_vacancies',
  source: 'taiwanjobs',
  metricId: 'position_count',
  metricSource: 'record_field',
  value: 5,
  unit: 'positions',
  ageScope: 'not_age_specific',
  youthEligibility: 'context_only',
  qualityFlags: ['query_district_mismatch_filtered'],
  sourcePath: 'curated/job_vacancies.json',
};

describe('formatEvidenceForPrompt', () => {
  it('每筆都放上可引用的 evidenceId', () => {
    const formatted = formatEvidenceForPrompt([longFormEvidence]);

    expect(formatted).toContain('evidenceId="population:11507:1:youth_18_35_total"');
    expect(formatted).toContain('dataset=population');
    expect(formatted).toContain('metric=youth_18_35_total');
    expect(formatted).toContain('scope=板橋區');
    expect(formatted).toContain('value=106473');
    expect(formatted).toContain('unit=people');
  });

  it('帶上 youthEligibility，模型才知道能不能當青年資料解讀', () => {
    expect(formatEvidenceForPrompt([longFormEvidence])).toContain('youthEligibility=eligible');
    expect(formatEvidenceForPrompt([wideFormEvidence])).toContain('youthEligibility=context_only');
  });

  it('帶上 metricSource，模型才知道這是資料集指標還是單筆記錄欄位', () => {
    expect(formatEvidenceForPrompt([longFormEvidence])).toContain('(metric_id)');
    expect(formatEvidenceForPrompt([wideFormEvidence])).toContain('(record_field)');
  });

  it('有品質旗標時要顯示出來，不可靜默吞掉', () => {
    expect(formatEvidenceForPrompt([wideFormEvidence])).toContain(
      'qualityFlags=query_district_mismatch_filtered',
    );
    // 沒有旗標時不要多印一行空的。
    expect(formatEvidenceForPrompt([longFormEvidence])).not.toContain('qualityFlags=');
  });

  it('非行政區層級的資料用 geoLevel 當範圍標示，不會印出 null', () => {
    const formatted = formatEvidenceForPrompt([
      { ...longFormEvidence, geoLevel: 'organization', districtName: null, districtId: null },
    ]);

    expect(formatted).toContain('scope=organization-level');
    expect(formatted).not.toContain('scope=null');
  });
});

describe('formatKnownLimitations', () => {
  it('沒有限制時回 null，不要在 prompt 裡留一個空標題', () => {
    expect(formatKnownLimitations([])).toBeNull();
  });

  it('標題用共用常數，MockBedrockClient 靠它定位這個區塊', () => {
    const formatted = formatKnownLimitations(['只取樣 3 筆']);

    // 不再比對寫死的中文字串：兩邊都用 KNOWN_LIMITATIONS_HEADER，結構上就不可能不同步。
    // （原本是兩份一樣的字串 ＋ 一個「改了要一起改」的提醒測試，而它真的被踩到了。）
    expect(formatted).toContain(KNOWN_LIMITATIONS_HEADER);
    expect(formatted).toContain('- 只取樣 3 筆');
  });

  it('明確叫模型不要把既知限制抄進 limitations（實測那佔了 25% 的輸出）', () => {
    expect(KNOWN_LIMITATIONS_HEADER).toContain('不要抄寫');
    // 但仍然要告訴模型結論不可與限制衝突，否則它會寫出跟限制打架的結論。
    expect(KNOWN_LIMITATIONS_HEADER).toContain('衝突');
  });

  it('MockBedrockClient 仍然解析得到既知限制（標題常數化之後沒有壞掉）', async () => {
    const output = await new MockBedrockClient().invokeStructured({
      system: 'test',
      // 一定要帶一筆 evidenceId：mock 會引用第一筆 evidence 當 basis，
      // 而 schema 要求「有結論就要有依據」。真實請求也永遠至少有一筆
      // （沒有 evidence 時 runFeature 根本不會呼叫模型）。
      user: `1. evidenceId="x"\n\n${formatKnownLimitations(['只取樣 3 筆', '未涵蓋房價']) ?? ''}`,
    });

    expect(output.limitations).toContain('只取樣 3 筆');
    expect(output.limitations).toContain('未涵蓋房價');
  });
});

describe('buildUserPrompt', () => {
  const context: AiContext = {
    question: null,
    focusDistrict: '板橋區',
    focusArea: 'employment',
    evidence: [longFormEvidence],
    knownLimitations: ['未涵蓋房價與租金資料'],
    webFindings: [],
  };

  it('順序固定：情境 → evidence → 既知限制', () => {
    const prompt = buildUserPrompt(context, ['使用者目前查看的行政區：板橋區']);

    expect(prompt.indexOf('使用者目前查看的行政區')).toBeLessThan(prompt.indexOf('可用的 evidence'));
    expect(prompt.indexOf('可用的 evidence')).toBeLessThan(prompt.indexOf('已知的資料限制'));
  });

  it('過濾掉 null 的情境行，不會留下空段落', () => {
    const prompt = buildUserPrompt(context, [null, '主題：employment']);

    expect(prompt).not.toContain('\n\n\n');
  });
});

describe('AI_GUARDRAILS', () => {
  it('禁止自行計算與捏造', () => {
    expect(AI_GUARDRAILS).toContain('不可自行推算');
    expect(AI_GUARDRAILS).toContain('不要把多筆 evidence 自己加總或平均');
  });

  it('要求每個論點都有 evidenceId 依據', () => {
    expect(AI_GUARDRAILS).toContain('evidenceId');
    expect(AI_GUARDRAILS).toContain('basis');
  });

  it('要求資料不足時寫進 limitations', () => {
    expect(AI_GUARDRAILS).toContain('limitations');
    expect(AI_GUARDRAILS).toContain('不可假裝資料充足');
  });

  it('解釋 youthEligibility 三個值的意義', () => {
    expect(AI_GUARDRAILS).toContain('eligible');
    expect(AI_GUARDRAILS).toContain('proxy_only');
    expect(AI_GUARDRAILS).toContain('context_only');
  });

  it('要求 disclaimer 帶固定字樣', () => {
    expect(AI_GUARDRAILS).toContain('不代表政府正式政策決定');
  });
});
