import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  SOURCE_REGISTRY,
  collectSourceAttributions,
  formatSourceAttributions,
} from '../src/types/sourceAttribution.js';
import { buildEvidenceForDataset } from '../src/context/buildContext.js';
import type { AiEvidence } from '../src/types/aiEvidence.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDataDir = path.join(here, 'fixtures', 'data-pipeline-data');

function evidenceOf(overrides: Partial<AiEvidence>): AiEvidence {
  return {
    evidenceId: 'population:11507:0:youth_18_35_total',
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
    sourceUrl: null,
    sourceKind: 'dataset',
    fetchedAt: '2026-09-12T01:56:04.525401+00:00',
    ...overrides,
  };
}

/**
 * 這組測試守的是「附資料來源」這個核心需求。
 * 重點不只是「有來源」，而是**來源不可能被模型捏造**：清單完全由程式從
 * 實際被引用的 evidence 推導。
 */
describe('collectSourceAttributions', () => {
  it('只列出被 basis 實際引用的來源', () => {
    const cited = evidenceOf({ evidenceId: 'a', source: 'moi_household_registration' });
    const notCited = evidenceOf({
      evidenceId: 'b',
      source: 'taiwanjobs',
      dataset: 'job_vacancies',
    });

    const sources = collectSourceAttributions([cited, notCited], {
      basis: [{ evidenceId: 'a', note: null }],
    });

    expect(sources).toHaveLength(1);
    expect(sources[0]?.sourceId).toBe('moi_household_registration');
  });

  it('沒有被引用的來源不會出現：否則使用者會以為某機關的資料支持了某結論', () => {
    const sources = collectSourceAttributions([evidenceOf({ evidenceId: 'a' })], { basis: [] });

    expect(sources).toEqual([]);
  });

  it('includeUncited 可以列出全部可用來源，但 citedEvidenceIds 會是空的', () => {
    const sources = collectSourceAttributions(
      [evidenceOf({ evidenceId: 'a' })],
      { basis: [] },
      { includeUncited: true },
    );

    expect(sources).toHaveLength(1);
    expect(sources[0]?.citedEvidenceIds).toEqual([]);
  });

  it('把 source 對應成中文機關與資料集名稱', () => {
    const sources = collectSourceAttributions([evidenceOf({ evidenceId: 'a' })], {
      basis: [{ evidenceId: 'a', note: null }],
    });

    expect(sources[0]?.organization).toBe('內政部戶政司');
    expect(sources[0]?.datasetLabel).toContain('戶籍人口統計');
    expect(sources[0]?.url).toMatch(/^https:\/\//);
  });

  it('同一個來源的多筆 evidence 合併成一筆來源，dataset 清單去重', () => {
    const sources = collectSourceAttributions(
      [
        evidenceOf({ evidenceId: 'a', dataset: 'population' }),
        evidenceOf({ evidenceId: 'b', dataset: 'population' }),
        evidenceOf({ evidenceId: 'c', dataset: 'movement', sourcePath: 'curated/movement.json' }),
      ],
      {
        basis: [
          { evidenceId: 'a', note: null },
          { evidenceId: 'b', note: null },
          { evidenceId: 'c', note: null },
        ],
      },
    );

    expect(sources).toHaveLength(1);
    expect(sources[0]?.datasets).toEqual(['population', 'movement']);
    expect(sources[0]?.sourcePaths).toEqual(['curated/population.json', 'curated/movement.json']);
    expect(sources[0]?.citedEvidenceIds).toEqual(['a', 'b', 'c']);
  });

  it('fetchedAt 取最新的一筆，讓使用者知道資料多舊', () => {
    const sources = collectSourceAttributions(
      [
        evidenceOf({ evidenceId: 'a', fetchedAt: '2026-01-01T00:00:00+00:00' }),
        evidenceOf({ evidenceId: 'b', fetchedAt: '2026-09-12T01:56:04+00:00' }),
      ],
      {
        basis: [
          { evidenceId: 'a', note: null },
          { evidenceId: 'b', note: null },
        ],
      },
    );

    expect(sources[0]?.fetchedAt).toBe('2026-09-12T01:56:04+00:00');
  });

  it('逐筆網址會被收集，但有數量上限避免回應被連結淹掉', () => {
    const evidence = Array.from({ length: 6 }, (_, index) =>
      evidenceOf({
        evidenceId: `e${index}`,
        source: 'taiwanjobs',
        dataset: 'job_vacancies',
        sourceUrl: `https://job.taiwanjobs.gov.tw/detail/${index}`,
      }),
    );

    const sources = collectSourceAttributions(evidence, {
      basis: evidence.map((item) => ({ evidenceId: item.evidenceId, note: null })),
    });

    expect(sources[0]?.recordUrls).toHaveLength(3);
    expect(sources[0]?.recordUrls[0]).toContain('job.taiwanjobs.gov.tw');
  });

  it('registry 沒登記的 source 仍然列出來，不可靜默消失', () => {
    const sources = collectSourceAttributions(
      [evidenceOf({ evidenceId: 'a', source: 'some_future_source' })],
      { basis: [{ evidenceId: 'a', note: null }] },
    );

    expect(sources[0]?.sourceId).toBe('some_future_source');
    expect(sources[0]?.organization).toBeNull();
    // 沒有機關名稱時，至少還有本地路徑可以回溯。
    expect(sources[0]?.sourcePaths).toEqual(['curated/population.json']);
  });

  it('source 為 null 時退回 dataset 名稱，來源不會整筆消失', () => {
    const sources = collectSourceAttributions(
      [evidenceOf({ evidenceId: 'a', source: null })],
      { basis: [{ evidenceId: 'a', note: null }] },
    );

    expect(sources[0]?.sourceId).toBe('dataset:population');
  });

  it('web 來源的 kind 會被保留，不會混進 dataset 裡看不出差別', () => {
    const sources = collectSourceAttributions(
      [
        evidenceOf({
          evidenceId: 'w1',
          source: 'some_web_page',
          sourceKind: 'web',
          sourceUrl: 'https://example.gov.tw/policy',
        }),
      ],
      { basis: [{ evidenceId: 'w1', note: null }] },
    );

    expect(sources[0]?.kind).toBe('web');
    expect(sources[0]?.recordUrls).toEqual(['https://example.gov.tw/policy']);
  });
});

describe('SOURCE_REGISTRY', () => {
  it('涵蓋真實資料裡出現的所有 source 值', async () => {
    const seen = new Set<string>();
    for (const dataset of ['population', 'job_vacancies', 'youth_budgets', 'training_numbers']) {
      for (const item of await buildEvidenceForDataset(fixtureDataDir, dataset)) {
        if (item.source) {
          seen.add(item.source);
        }
      }
    }

    expect(seen.size).toBeGreaterThan(0);
    for (const source of seen) {
      expect(SOURCE_REGISTRY, `${source} 沒有登記在 SOURCE_REGISTRY`).toHaveProperty(source);
    }
  });

  it('每個登記的來源都有機關名稱與資料集名稱', () => {
    for (const [sourceId, entry] of Object.entries(SOURCE_REGISTRY)) {
      expect(entry.organization, `${sourceId} 缺 organization`).toBeTruthy();
      expect(entry.datasetLabel, `${sourceId} 缺 datasetLabel`).toBeTruthy();
    }
  });

  it('有填 url 的就必須是 https，不可放半成品', () => {
    for (const [sourceId, entry] of Object.entries(SOURCE_REGISTRY)) {
      if (entry.url !== null) {
        expect(entry.url, `${sourceId} 的 url 不是 https`).toMatch(/^https:\/\//);
      }
    }
  });
});

/**
 * 真實資料驗證：curated record 的來源網址藏在 raw_record 裡（`source_document_url`、
 * `URL_QUERY（職缺資料URL）`），要確認白名單真的撈得到，否則 sourceUrl 永遠是 null。
 */
describe('從真實 curated 資料抽出來源網址', () => {
  it('youth_budgets 抽得到預算書 PDF 網址', async () => {
    const evidence = await buildEvidenceForDataset(fixtureDataDir, 'youth_budgets');
    const withUrl = evidence.filter((item) => item.sourceUrl !== null);

    expect(withUrl.length).toBeGreaterThan(0);
    expect(withUrl[0]?.sourceUrl).toMatch(/^https?:\/\//);
  });

  it('job_vacancies 抽得到職缺頁面網址', async () => {
    const evidence = await buildEvidenceForDataset(fixtureDataDir, 'job_vacancies');
    const withUrl = evidence.filter((item) => item.sourceUrl !== null);

    expect(withUrl.length).toBeGreaterThan(0);
    expect(withUrl[0]?.sourceUrl).toContain('taiwanjobs.gov.tw');
  });

  it('抽網址不會把 raw_record 整包帶出來', async () => {
    const evidence = await buildEvidenceForDataset(fixtureDataDir, 'youth_budgets');
    const serialized = JSON.stringify(evidence);

    expect(serialized).not.toContain('raw_record');
    expect(serialized).not.toContain('source_row_text');
  });

  it('每個 dataset 都有 source 值可以標示來源', async () => {
    for (const dataset of ['population', 'job_vacancies', 'youth_budgets', 'training_numbers']) {
      const evidence = await buildEvidenceForDataset(fixtureDataDir, dataset);
      expect(evidence.every((item) => item.source !== null), `${dataset} 有 source 為 null 的資料`).toBe(
        true,
      );
    }
  });
});

describe('formatSourceAttributions', () => {
  it('沒有來源時明確說出來，不要回空字串', () => {
    expect(formatSourceAttributions([])).toContain('沒有引用任何資料來源');
  });

  it('一行一筆，含機關、資料集與抓取時間', () => {
    const sources = collectSourceAttributions([evidenceOf({ evidenceId: 'a' })], {
      basis: [{ evidenceId: 'a', note: null }],
    });
    const formatted = formatSourceAttributions(sources);

    expect(formatted).toContain('內政部戶政司');
    expect(formatted).toContain('戶籍人口統計');
    expect(formatted).toContain('2026-09-12');
  });
});
