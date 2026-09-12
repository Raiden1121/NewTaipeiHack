import { describe, expect, it } from 'vitest';
import { AI_ACTIONS, AiRequestSchema, handler } from '../src/handlers/lambda.js';
import type { AiEvidence } from '../src/types/aiEvidence.js';

const evidence: AiEvidence = {
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
  sourceUrl: null,
  sourceKind: 'dataset',
  fetchedAt: '2026-09-12T01:56:04.525401+00:00',
};

function requestBody(action: string, overrides: Record<string, unknown> = {}) {
  return JSON.stringify({
    action,
    context: {
      question: null,
      focusDistrict: '板橋區',
      focusArea: 'population',
      evidence: [evidence],
      knownLimitations: [],
      ...overrides,
    },
  });
}

describe('handler 成功路徑', () => {
  it('回 200，envelope 帶 action / generatedBy / output', async () => {
    const response = await handler({ body: requestBody('explain') });
    const payload = JSON.parse(response.body);

    expect(response.statusCode).toBe(200);
    expect(response.headers['content-type']).toContain('charset=utf-8');
    expect(payload.action).toBe('explain');
    expect(payload.output.dataSufficiency).toBeTruthy();
  });

  it('generatedBy 讓前端看得出來是 mock 還是真模型', async () => {
    const payload = JSON.parse((await handler({ body: requestBody('explain') })).body);

    // 測試環境沒有設 AWS 環境變數，所以一定是 mock。
    expect(payload.generatedBy).toContain('mock');
  });

  /**
   * `cache` 是排查的第一個線索：看到內容不對的卡片時，`hit` 代表可能是舊快照的
   * 答案，`bypass` / `miss` 代表是模型這次的輸出。少了它就分不出來。
   */
  it('envelope 帶 cache / precomputedAt，讓前端分得出是預先算還是即時算', async () => {
    const explain = JSON.parse((await handler({ body: requestBody('explain') })).body);
    // 測試環境沒設 AI_PRECOMPUTE_DIR，所以快取是關閉的（行為等於沒有快取）。
    expect(explain.cache).toBe('disabled');
    expect(explain.precomputedAt).toBeNull();

    const qa = JSON.parse(
      (await handler({ body: requestBody('qa', { question: '板橋區有多少青年？' }) })).body,
    );
    // Q&A 永遠不快取：問法無限多種，預先算不可能涵蓋。
    expect(qa.cache).toBe('bypass');
    expect(qa.precomputedAt).toBeNull();
  });

  it('回應一定帶 sources，且來源可回溯到真實檔案路徑', async () => {
    const payload = JSON.parse((await handler({ body: requestBody('explain') })).body);

    expect(Array.isArray(payload.sources)).toBe(true);
    expect(payload.sources.length).toBeGreaterThan(0);
    expect(payload.sources[0].organization).toBe('內政部戶政司');
    expect(payload.sources[0].sourcePaths).toContain('curated/population.json');
  });

  it('三個 action 都能分派', async () => {
    for (const action of AI_ACTIONS) {
      const body = action === 'qa' ? requestBody(action, { question: '板橋區青年人口多少？' }) : requestBody(action);
      const response = await handler({ body });

      expect(response.statusCode, `${action} 應該成功`).toBe(200);
    }
  });

  it('沒有 evidence 時仍然回 200，內容是誠實的「資料不足」而不是錯誤', async () => {
    const response = await handler({ body: requestBody('explain', { evidence: [] }) });
    const payload = JSON.parse(response.body);

    expect(response.statusCode).toBe(200);
    expect(payload.output.dataSufficiency).toBe('insufficient');
  });
});

describe('handler 錯誤處理', () => {
  it('request 格式錯誤回 400，並列出逐欄位問題', async () => {
    const response = await handler({ body: JSON.stringify({ action: 'explain' }) });
    const payload = JSON.parse(response.body);

    expect(response.statusCode).toBe(400);
    expect(payload.issues.length).toBeGreaterThan(0);
    expect(payload.issues[0].path).toContain('context');
  });

  it('未知 action 回 400', async () => {
    const response = await handler({ body: requestBody('unknownAction') });

    expect(response.statusCode).toBe(400);
    expect(JSON.parse(response.body).issues[0].path).toBe('action');
  });

  it('body 不是 JSON 時回 400 而不是 500', async () => {
    const response = await handler({ body: '這不是 JSON' });

    expect(response.statusCode).toBe(400);
    expect(JSON.parse(response.body).issues[0].message).toContain('不是有效的 JSON');
  });

  /**
   * API Gateway / Function URL 在某些設定下會 base64 包裝 body。
   * 沒處理的話部署後只會看到「不是有效的 JSON」，很難聯想到是編碼問題。
   */
  it('isBase64Encoded=true 時要先解碼再剖析', async () => {
    const encoded = Buffer.from(requestBody('explain'), 'utf-8').toString('base64');
    const response = await handler({ body: encoded, isBase64Encoded: true });

    expect(response.statusCode).toBe(200);
  });

  it('isBase64Encoded 沒設時當成純文字處理', async () => {
    expect((await handler({ body: requestBody('explain') })).statusCode).toBe(200);
  });

  it('body 為空時回 400', async () => {
    for (const body of [null, undefined, '']) {
      expect((await handler({ body })).statusCode).toBe(400);
    }
  });

  it('evidence 欄位不符合 contract 時回 400（例如 value 傳了物件）', async () => {
    const response = await handler({
      body: requestBody('explain', {
        evidence: [{ ...evidence, value: { raw_record: '整包原始資料' } }],
      }),
    });

    expect(response.statusCode).toBe(400);
  });

  it('執行期失敗回 502 而不是 400：格式沒問題，是伺服器側的問題', async () => {
    // qa 缺 question 會在 prompt 組裝時丟錯 —— schema 允許 question 為 null，
    // 所以這條路徑走到的是執行期錯誤。
    const response = await handler({ body: requestBody('qa', { question: null }) });

    expect(response.statusCode).toBe(502);
    expect(JSON.parse(response.body).error).toContain('context.question');
  });
});

describe('AiRequestSchema（給 backend / frontend 對齊的契約）', () => {
  it('knownLimitations 可以省略，預設空陣列', () => {
    const parsed = AiRequestSchema.parse({
      action: 'explain',
      context: { question: null, focusDistrict: null, focusArea: null, evidence: [] },
    });

    expect(parsed.context.knownLimitations).toEqual([]);
  });

  it('action 只接受三個合法值', () => {
    expect(AI_ACTIONS).toEqual(['explain', 'policyCopilot', 'qa']);
  });
});
