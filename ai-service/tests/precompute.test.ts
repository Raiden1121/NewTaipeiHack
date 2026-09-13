import { mkdtemp, readdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { MockBedrockClient } from '../src/bedrock/client.js';
import { buildFingerprintInput, contextFingerprint } from '../src/precompute/fingerprint.js';
import {
  DisabledPrecomputedStore,
  FilePrecomputedStore,
  createPrecomputedStoreFromEnv,
  type PrecomputedEntry,
} from '../src/precompute/store.js';
import {
  dispatchWithPrecompute,
  isPrecomputable,
  PRECOMPUTABLE_ACTIONS,
} from '../src/precompute/servePrecomputed.js';
import { QA_ANSWER_MAX_CHARS, buildDataQaPrompt } from '../src/prompts/dataQa.js';
import { createEvidenceRepositoryFromEnv } from '../src/context/buildContext.js';
import type { AiFeatureResult } from '../src/handlers/runFeature.js';
import { makeEvidence, makeOutput, makeRequestContext } from './helpers.js';

async function tempDir(): Promise<string> {
  return mkdtemp(join(tmpdir(), 'ai-precompute-'));
}

function stubResult(): AiFeatureResult {
  return { output: makeOutput(), sources: [] };
}

describe('fingerprint：快取鍵', () => {
  it('同樣的輸入得到同樣的指紋', () => {
    const context = makeRequestContext();
    expect(contextFingerprint('explain', context)).toBe(contextFingerprint('explain', context));
  });

  it('action 不同就是不同的指紋（同一份資料兩個功能輸出不一樣）', () => {
    const context = makeRequestContext();
    expect(contextFingerprint('explain', context)).not.toBe(
      contextFingerprint('policyCopilot', context),
    );
  });

  /**
   * 這是整個設計最重要的一條。
   *
   * evidenceId 的格式是 `{dataset}:{period}:{scope}:{metricId}`，**不含數值**。
   * 資料管線重算同一期的指標時（值變了、id 沒變），如果指紋只看 id，
   * 線上就會回一份用舊數字算出來的分析，而且不會有任何跡象。
   */
  it('evidence 的值變了，指紋一定要變', () => {
    const before = makeRequestContext({ evidence: [makeEvidence({ value: 106_473 })] });
    const after = makeRequestContext({ evidence: [makeEvidence({ value: 107_970 })] });

    expect(contextFingerprint('explain', before)).not.toBe(contextFingerprint('explain', after));
  });

  it('單位變了，指紋也要變（220,101 千元跟 220,101 元不是同一件事）', () => {
    const thousands = makeRequestContext({ evidence: [makeEvidence({ unit: 'TWD_thousand' })] });
    const dollars = makeRequestContext({ evidence: [makeEvidence({ unit: 'TWD' })] });

    expect(contextFingerprint('explain', thousands)).not.toBe(
      contextFingerprint('explain', dollars),
    );
  });

  it('evidence 順序不同但內容相同時要命中（呼叫端沒有義務跟我們同一個順序）', () => {
    const first = makeEvidence({ evidenceId: 'population:11507:1:a' });
    const second = makeEvidence({ evidenceId: 'population:11507:1:b' });

    expect(contextFingerprint('explain', makeRequestContext({ evidence: [first, second] }))).toBe(
      contextFingerprint('explain', makeRequestContext({ evidence: [second, first] })),
    );
  });

  it('question 不進指紋（explain / policyCopilot 沒有使用者問題）', () => {
    expect(contextFingerprint('explain', makeRequestContext({ question: null }))).toBe(
      contextFingerprint('explain', makeRequestContext({ question: '隨便問一句' })),
    );
  });

  /**
   * 搜尋結果每次都不一樣，納入指紋等於永遠 miss，快取就完全失效了。
   * 追溯性不會掉：快取條目裡存著當初實際用到的網路來源。
   */
  it('webFindings 不進指紋', () => {
    const input = buildFingerprintInput('explain', makeRequestContext());
    expect(JSON.stringify(input)).not.toContain('webFindings');
  });

  it('搜尋範圍（all / trusted）會影響指紋：不可以把全網的答案回給只要可信來源的人', () => {
    const all = makeRequestContext({ webSearch: { enabled: true, contextSize: 'low', scope: 'all' } });
    const trusted = makeRequestContext({
      webSearch: { enabled: true, contextSize: 'low', scope: 'trusted' },
    });

    expect(contextFingerprint('explain', all)).not.toBe(contextFingerprint('explain', trusted));
  });
});

describe('FilePrecomputedStore', () => {
  it('寫進去讀得回來', async () => {
    const store = new FilePrecomputedStore(await tempDir());
    const entry: PrecomputedEntry = {
      fingerprint: 'abc123',
      action: 'explain',
      focusDistrict: '板橋區',
      focusArea: 'employment',
      snapshotId: 'dev-full-20260912',
      generatedAt: '2026-09-12T00:00:00.000Z',
      generatedBy: 'bedrock(mock)',
      elapsedMs: 50_000,
      output: makeOutput(),
      sources: [],
    };

    await store.put(entry);

    expect(await store.get('abc123')).toEqual(entry);
  });

  it('沒有這筆就回 null（miss 是正常狀況，不是錯誤）', async () => {
    const store = new FilePrecomputedStore(await tempDir());
    await expect(store.get('deadbeef')).resolves.toBeNull();
  });

  it('目錄不存在時 list 回空陣列而不是丟錯', async () => {
    const store = new FilePrecomputedStore(join(await tempDir(), 'not-created-yet'));
    await expect(store.list()).resolves.toEqual([]);
  });

  /**
   * 一個壞檔不該讓整個功能掛掉：正確的降級行為是「重新算一次」。
   * 丟錯的話，dashboard 上那張卡片會變成 502。
   */
  it('壞掉或舊格式的檔案當成 miss，不丟錯', async () => {
    const dir = await tempDir();
    const store = new FilePrecomputedStore(dir);
    await writeFile(join(dir, 'aaaa.json'), '{"action":"explain"}', 'utf-8');

    await expect(store.get('aaaa')).resolves.toBeNull();
  });

  it('查詢用不合法的鍵一律當 miss（查不到就重新算，行為是安全的）', async () => {
    const store = new FilePrecomputedStore(await tempDir());
    await expect(store.get('../../etc/passwd')).resolves.toBeNull();
    await expect(store.get('')).resolves.toBeNull();
  });

  /**
   * 刻意用嚴格驗證而不是把不合法字元過濾掉。
   * 過濾的話 `ab/cd` 與 `abcd` 會對到同一個檔案 —— 不同的鍵指到同一份結果，
   * 也就是「回了別人的答案」，那是這個快取最不能出的錯。
   */
  it('寫入時 fingerprint 不合法就丟錯，不做寬容過濾', async () => {
    const dir = await tempDir();
    const store = new FilePrecomputedStore(dir);

    await expect(
      store.put({ ...(await validEntry()), fingerprint: 'ab/cd' }),
    ).rejects.toThrow('十六進位');
    await expect(
      store.put({ ...(await validEntry()), fingerprint: '../../evil' }),
    ).rejects.toThrow('十六進位');

    expect(await readdir(dir)).toEqual([]);
  });
});

/**
 * evidence 來源的預設值直接決定預先算能不能命中：批次腳本與線上請求走的來源不同時，
 * evidence 不同 → 指紋不同 → 每次 miss → 即時算 50 秒 → 被 API Gateway 切斷。
 * 所以把預設鎖在測試裡，改動時要有人明確決定。
 */
describe('createEvidenceRepositoryFromEnv：預設只讀 analytics', () => {
  it('沒設 AI_EVIDENCE_SOURCE 時只讀 analytics 快照', () => {
    const repo = createEvidenceRepositoryFromEnv({ AI_DATA_DIR: 'C:/tmp/data' });
    expect(repo.description).toContain('analytics-snapshot');
    // 進 DynamoDB 的只有 analytics 算完的結果，curated 留在 S3，線上不會有。
    expect(repo.description).not.toContain('curated');
  });

  it('composite 要明確指定才會兩個都讀', () => {
    const repo = createEvidenceRepositoryFromEnv({
      AI_DATA_DIR: 'C:/tmp/data',
      AI_EVIDENCE_SOURCE: 'composite',
    });
    expect(repo.description).toContain('curated');
    expect(repo.description).toContain('analytics-snapshot');
  });

  it('curated 只讀 curated', () => {
    const repo = createEvidenceRepositoryFromEnv({
      AI_DATA_DIR: 'C:/tmp/data',
      AI_EVIDENCE_SOURCE: 'curated',
    });
    expect(repo.description).toContain('curated');
    expect(repo.description).not.toContain('analytics-snapshot');
  });
});

describe('createPrecomputedStoreFromEnv', () => {
  it('沒設 AI_PRECOMPUTE_DIR 就是關閉（不猜一個位置寫檔）', () => {
    expect(createPrecomputedStoreFromEnv({})).toBeInstanceOf(DisabledPrecomputedStore);
  });

  it('設了就用檔案版', () => {
    const store = createPrecomputedStoreFromEnv({ AI_PRECOMPUTE_DIR: 'C:/tmp/x' });
    expect(store).toBeInstanceOf(FilePrecomputedStore);
    expect(store.description).toContain('C:/tmp/x');
  });
});

describe('dispatchWithPrecompute', () => {
  const client = new MockBedrockClient();

  it('Q&A 一律 bypass：問法無限多種，預先算不可能涵蓋', async () => {
    const live = vi.fn(async () => stubResult());
    const result = await dispatchWithPrecompute('qa', live, client, makeRequestContext(), {
      store: new FilePrecomputedStore(await tempDir()),
    });

    expect(result.cache).toBe('bypass');
    expect(result.fingerprint).toBeNull();
    expect(live).toHaveBeenCalledTimes(1);
  });

  it('沒設快取時是 disabled，行為等於沒有快取', async () => {
    const live = vi.fn(async () => stubResult());
    const result = await dispatchWithPrecompute('explain', live, client, makeRequestContext());

    expect(result.cache).toBe('disabled');
    expect(live).toHaveBeenCalledTimes(1);
  });

  it('命中時不呼叫模型，並回報當初產生的時間', async () => {
    const store = new FilePrecomputedStore(await tempDir());
    const context = makeRequestContext();
    const cachedOutput = makeOutput({ issues: ['這是預先算的內容'] });
    await store.put({
      ...(await validEntry()),
      fingerprint: contextFingerprint('explain', context),
      generatedAt: '2026-09-01T12:00:00.000Z',
      output: cachedOutput,
    });

    const live = vi.fn(async () => stubResult());
    const result = await dispatchWithPrecompute('explain', live, client, context, { store });

    expect(result.cache).toBe('hit');
    expect(result.output.issues).toEqual(['這是預先算的內容']);
    expect(result.precomputedAt).toBe('2026-09-01T12:00:00.000Z');
    expect(live).not.toHaveBeenCalled();
  });

  it('evidence 的值變了就不命中（不會回用舊數字算出來的分析）', async () => {
    const store = new FilePrecomputedStore(await tempDir());
    const before = makeRequestContext({ evidence: [makeEvidence({ value: 106_473 })] });
    await store.put({
      ...(await validEntry()),
      fingerprint: contextFingerprint('explain', before),
    });

    const after = makeRequestContext({ evidence: [makeEvidence({ value: 107_970 })] });
    const live = vi.fn(async () => stubResult());
    const result = await dispatchWithPrecompute('explain', live, client, after, { store });

    expect(result.cache).toBe('miss');
    expect(live).toHaveBeenCalledTimes(1);
  });

  it('miss 時預設不寫回快取', async () => {
    const store = new FilePrecomputedStore(await tempDir());
    const live = vi.fn(async () => stubResult());

    await dispatchWithPrecompute('explain', live, client, makeRequestContext(), { store });

    expect(await store.list()).toEqual([]);
  });

  it('writeThrough=true 才寫回，並記下模型與耗時', async () => {
    const store = new FilePrecomputedStore(await tempDir());
    const live = vi.fn(async () => stubResult());

    await dispatchWithPrecompute('explain', live, client, makeRequestContext(), {
      store,
      writeThrough: true,
      snapshotId: 'snap-1',
    });

    const entries = await store.list();
    expect(entries).toHaveLength(1);
    expect(entries[0]?.generatedBy).toContain('mock');
    expect(entries[0]?.snapshotId).toBe('snap-1');
    expect(entries[0]?.action).toBe('explain');
  });
});

describe('PRECOMPUTABLE_ACTIONS', () => {
  it('只有 explain 與 policyCopilot', () => {
    expect([...PRECOMPUTABLE_ACTIONS]).toEqual(['explain', 'policyCopilot']);
    expect(isPrecomputable('qa')).toBe(false);
  });
});

describe('Q&A answer 字數上限', () => {
  it('prompt 有寫出上限（延遲直接由輸出長度決定）', () => {
    const prompt = buildDataQaPrompt(makeRequestContext({ question: '板橋區有多少青年？' }));
    expect(prompt.system).toContain(`${QA_ANSWER_MAX_CHARS} 字以內`);
  });

  /**
   * 壓字數不可以壓掉誠實性。實測模型在被要求「簡短」時最先犧牲的就是不確定性說明，
   * 而一個簡短但看起來很確定的錯誤回答比長篇大論更有害。
   */
  it('prompt 明確說前提更正與不確定性不可為了字數省略', () => {
    const prompt = buildDataQaPrompt(makeRequestContext({ question: '為何八里薪資第六高？' }));
    expect(prompt.system).toContain('不可以為了字數而省略');
  });

  /**
   * 實測踩到的：加了字數上限之後，「為何坪林薪資最高」這題模型只回了
   * 「坪林並非最高，與烏來並列第一。這個前提需要先更正。」就停筆 ——
   * 343 字（沒有超過上限），但完全沒有回答「為什麼」。
   * 它砍掉的是解釋，不是鋪陳，正好跟指示相反。
   */
  /**
   * 實測抓到的：模型把「為什麼」答成指標清單。
   *
   * 「為什麼樹林區的機會指數這麼高」拿到的是「就業 75.80、人才 51.42、薪資 50.43、
   * 住宅 30.29、交通 15.07，就業最高」—— 資料全對，但那是報告不是解釋，
   * 而且明明已經給了權重卻沒有把貢獻度乘出來。
   *
   * 根因有兩個，都在 prompt 裡：
   * 1. 結構要求寫的是「列出方向一致的指標」，那就是在叫它做清單
   * 2. 「不可講因果」讓它只能退回「兩個指標方向一致」這種安全但無用的句式
   */
  it('prompt 要求算出主導因素，不是列出所有因素', () => {
    const prompt = buildDataQaPrompt(makeRequestContext({ question: '為什麼樹林機會指數高？' }));

    expect(prompt.system).toContain('哪個因素主導');
    expect(prompt.system).toContain('貢獻度乘出來');
    // 明確禁止清單句式
    expect(prompt.system).toContain('清單句式');
  });

  it('prompt 要求提出機制並標示成推論（不是禁止機制）', () => {
    const prompt = buildDataQaPrompt(makeRequestContext({ question: '為什麼八里薪資高？' }));

    expect(prompt.system).toContain('最可能的機制');
    expect(prompt.system).toContain('因果語言是允許的');
    // 「只說無法判斷原因」等於沒回答，這條要寫出來
    expect(prompt.system).toContain('等於沒有回答');
  });

  it('prompt 要求檢查競爭解釋與指出矛盾', () => {
    const prompt = buildDataQaPrompt(makeRequestContext({ question: '為什麼坪林薪資最高？' }));

    expect(prompt.system).toContain('競爭解釋');
    expect(prompt.system).toContain('矛盾');
  });

  it('prompt 明確說更正前提不算回答完畢', () => {
    const prompt = buildDataQaPrompt(makeRequestContext({ question: '為何坪林薪資最高？' }));
    expect(prompt.system).toContain('更正前提不算回答完畢');
    expect(prompt.system).toContain('不可以只留下一句更正就結束');
  });
});

async function validEntry(): Promise<PrecomputedEntry> {
  return {
    fingerprint: 'ff00',
    action: 'explain',
    focusDistrict: '板橋區',
    focusArea: 'employment',
    snapshotId: null,
    generatedAt: '2026-09-12T00:00:00.000Z',
    generatedBy: 'bedrock(mock)',
    elapsedMs: 1,
    output: makeOutput(),
    sources: [],
  };
}
