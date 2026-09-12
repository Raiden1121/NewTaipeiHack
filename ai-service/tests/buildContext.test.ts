import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  CuratedFileEvidenceRepository,
  buildAiContext,
  buildEvidenceForDataset,
  loadEvidenceFromCuratedFile,
  readDatasetIndex,
  selectIndexEntry,
} from '../src/context/buildContext.js';
import { EXCLUDED_RECORD_FIELDS } from '../src/context/curatedRecord.js';
import { AiEvidenceSchema } from '../src/types/aiEvidence.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDataDir = path.join(here, 'fixtures', 'data-pipeline-data');

/**
 * 這整個檔案跑的是 **data-pipeline 真的產生出來的資料切片**（見 fixtures/README.md），
 * 不是照文件想像手寫的 fixture。這是唯一能擋掉「格式對不上」的機制 ——
 * 之前手寫 fixture 時 19 個測試全綠，但真實資料一接上就全盤崩掉。
 */
describe('readDatasetIndex（真實 schema_version 2 格式）', () => {
  it('datasets 是物件而不是陣列，且把 map 的 key 補成 dataset 欄位', async () => {
    const index = await readDatasetIndex(fixtureDataDir);

    expect(index.schemaVersion).toBe(2);
    expect(index.entries.length).toBeGreaterThan(0);
    expect(index.entries.map((entry) => entry.dataset)).toContain('population');
  });

  it('路徑欄位是 path（不是 curated_path）', async () => {
    const index = await readDatasetIndex(fixtureDataDir);
    const entry = selectIndexEntry(index, 'population');

    expect(entry?.path).toBe('curated/population.json');
    // 真實 index 沒有 status 欄位；靠 status === 'ok' 過濾會永遠得到空結果。
    expect(entry).not.toHaveProperty('status');
  });

  it('讀不到 index 時，錯誤訊息要直接告訴你該跑哪個指令', async () => {
    await expect(readDatasetIndex(path.join(here, 'fixtures', 'does-not-exist'))).rejects.toThrow(
      /run_pipeline\.py/,
    );
  });
});

describe('long-form dataset（metric_id 與 value 有值）', () => {
  it('population 的每個 metric_id 各成一筆 evidence，欄位對應到真實 curated 欄位名', async () => {
    const evidence = await buildEvidenceForDataset(fixtureDataDir, 'population');

    expect(evidence.length).toBeGreaterThan(0);
    for (const item of evidence) {
      expect(() => AiEvidenceSchema.parse(item)).not.toThrow();
    }

    const youthTotal = evidence.find((item) => item.metricId === 'youth_18_35_total');
    expect(youthTotal).toBeDefined();
    expect(youthTotal?.metricSource).toBe('metric_id');
    // 這三個是計畫書列的「原本讀錯的欄位」：district_name / youth_eligibility / fetched_at。
    expect(youthTotal?.districtName).toBeTruthy();
    expect(youthTotal?.youthEligibility).toBe('eligible');
    expect(youthTotal?.fetchedAt).toBeTruthy();
    expect(typeof youthTotal?.value).toBe('number');
    expect(youthTotal?.districtId).toMatch(/^\d+$/);
  });

  it('youth_budgets 是 organization 層級，districtName 為 null 但仍要有指標值', async () => {
    const evidence = await buildEvidenceForDataset(fixtureDataDir, 'youth_budgets');

    expect(evidence.length).toBeGreaterThan(0);
    expect(evidence[0]?.geoLevel).toBe('organization');
    expect(evidence[0]?.districtName).toBeNull();
    expect(evidence[0]?.metricId).toBe('budget_amount');
    expect(typeof evidence[0]?.value).toBe('number');
  });
});

describe('wide-form dataset（metric_id 與 value 都是 null）', () => {
  it('job_vacancies 從 dataset 專屬欄位取值，不會產出 value=null 的空 evidence', async () => {
    const evidence = await buildEvidenceForDataset(fixtureDataDir, 'job_vacancies');

    expect(evidence.length).toBeGreaterThan(0);
    // 全部都必須有值 —— 這正是原本「通用讀 record.value」會失敗的地方。
    expect(evidence.every((item) => item.value !== null)).toBe(true);
    expect(evidence.every((item) => item.metricSource === 'record_field')).toBe(true);
    expect(evidence.map((item) => item.metricId)).toContain('position_count');

    const positionCount = evidence.find((item) => item.metricId === 'position_count');
    expect(positionCount?.unit).toBe('positions');
  });

  it('一筆 record 攤成多筆 evidence 時 evidenceId 仍然唯一', async () => {
    const evidence = await buildEvidenceForDataset(fixtureDataDir, 'job_vacancies');
    const ids = evidence.map((item) => item.evidenceId);

    expect(new Set(ids).size).toBe(ids.length);
  });

  it('training_numbers 是 county 層級', async () => {
    const evidence = await buildEvidenceForDataset(fixtureDataDir, 'training_numbers');

    expect(evidence.length).toBeGreaterThan(0);
    expect(evidence.every((item) => item.geoLevel === 'county')).toBe(true);
    expect(evidence.every((item) => item.districtName === null)).toBe(true);
  });
});

describe('raw_record 等大體積欄位不可外流', () => {
  it('evidence 的 value 永遠是純量，不會夾帶原始整包資料', async () => {
    for (const dataset of ['population', 'job_vacancies', 'youth_budgets', 'training_numbers']) {
      const evidence = await buildEvidenceForDataset(fixtureDataDir, dataset);
      for (const item of evidence) {
        expect(['number', 'string']).toContain(typeof item.value);
      }
    }
  });

  it('序列化後的 evidence 不含任何被排除的欄位名', async () => {
    const evidence = await buildEvidenceForDataset(fixtureDataDir, 'population');
    const serialized = JSON.stringify(evidence);

    for (const field of EXCLUDED_RECORD_FIELDS) {
      expect(serialized).not.toContain(field);
    }
  });
});

describe('index 條目查不到時的行為', () => {
  it('沒有這個 dataset 時回空陣列，不丟錯（呼叫端要當成資料不足處理）', async () => {
    expect(await buildEvidenceForDataset(fixtureDataDir, 'not_a_real_dataset')).toEqual([]);
  });

  it('指定不存在的 period 時回空陣列', async () => {
    expect(await buildEvidenceForDataset(fixtureDataDir, 'population', '99999')).toEqual([]);
  });

  it('index 指到不存在的檔案時要丟錯，不可靜默當成沒資料', async () => {
    const index = await readDatasetIndex(fixtureDataDir);
    const entry = selectIndexEntry(index, 'house_prices');

    expect(entry).not.toBeNull();
    await expect(loadEvidenceFromCuratedFile(fixtureDataDir, entry!)).rejects.toThrow();
  });
});

describe('CuratedFileEvidenceRepository', () => {
  const repository = new CuratedFileEvidenceRepository(fixtureDataDir);

  it('預設排除逐筆交易明細的 dataset，並在 notes 說明缺了什麼', async () => {
    const bundle = await repository.query({ datasets: ['population', 'house_prices'] });

    expect(bundle.evidence.every((item) => item.dataset !== 'house_prices')).toBe(true);
    expect(bundle.notes.join('\n')).toContain('house_prices');
    expect(bundle.notes.join('\n')).toContain('analytics');
  });

  it('超過 limitPerDataset 時要截斷，並在 notes 說明實際筆數', async () => {
    const bundle = await repository.query({ datasets: ['population'], limitPerDataset: 3 });

    expect(bundle.evidence).toHaveLength(3);
    expect(bundle.truncated).toBe(true);
    expect(bundle.totalMatched).toBeGreaterThan(3);
    expect(bundle.notes.join('\n')).toMatch(/僅取樣 3 筆/);
  });

  it('把來源的品質旗標整理進 notes', async () => {
    const bundle = await repository.query({ datasets: ['job_vacancies'] });

    expect(bundle.notes.join('\n')).toContain('query_district_mismatch_filtered');
  });

  it('篩行政區時保留機關／縣市層級資料，不可把青年局預算濾掉', async () => {
    const districtName = (await buildEvidenceForDataset(fixtureDataDir, 'population')).find(
      (item) => item.districtName !== null,
    )?.districtName;
    expect(districtName).toBeTruthy();

    const bundle = await repository.query({
      datasets: ['population', 'youth_budgets', 'training_numbers'],
      districtNames: [districtName!],
    });
    const datasets = new Set(bundle.evidence.map((item) => item.dataset));

    expect(datasets).toContain('population');
    expect(datasets).toContain('youth_budgets');
    expect(datasets).toContain('training_numbers');
    // district 層級的資料仍然只留下指定的那一區。
    const districtLevel = bundle.evidence.filter((item) => item.geoLevel === 'district');
    expect(districtLevel.every((item) => item.districtName === districtName)).toBe(true);
  });

  it('明確要求 geoLevels=[district] 時就不再夾帶跨區脈絡資料', async () => {
    const bundle = await repository.query({
      datasets: ['population', 'youth_budgets'],
      geoLevels: ['district'],
    });

    expect(bundle.evidence.every((item) => item.geoLevel === 'district')).toBe(true);
  });
});

describe('buildAiContext', () => {
  const repository = new CuratedFileEvidenceRepository(fixtureDataDir);

  it('把 repository 的 notes 全部帶進 knownLimitations', async () => {
    const context = await buildAiContext(repository, {
      focusArea: 'employment',
      datasets: ['population', 'house_prices'],
      limitPerDataset: 2,
    });

    expect(context.knownLimitations.length).toBeGreaterThan(0);
    expect(context.knownLimitations.join('\n')).toContain('house_prices');
  });

  it('完全沒有資料時回空 evidence 而不是丟錯，並註明來源', async () => {
    const context = await buildAiContext(repository, { datasets: ['not_a_real_dataset'] });

    expect(context.evidence).toEqual([]);
    expect(context.knownLimitations.join('\n')).toContain('curated-files');
  });

  it('指定 focusDistrict 時自動當成行政區篩選條件', async () => {
    const all = await buildAiContext(repository, { datasets: ['population'] });
    const single = await buildAiContext(repository, {
      focusDistrict: '板橋區',
      datasets: ['population'],
    });

    expect(single.focusDistrict).toBe('板橋區');
    expect(single.evidence.length).toBeLessThan(all.evidence.length);
    expect(
      single.evidence
        .filter((item) => item.geoLevel === 'district')
        .every((item) => item.districtName === '板橋區'),
    ).toBe(true);
  });
});
