import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';
import { describe, expect, it, vi } from 'vitest';
import {
  AI_CONTEXT_ENCODING,
  AI_CONTEXT_MANIFEST_KEY,
  DynamoEvidenceRepository,
  META_MANIFEST_KEY,
  aiContextArtifactKey,
} from '../src/context/dynamoRepository.js';
import {
  AnalyticsSnapshotEvidenceRepository,
  createEvidenceRepositoryFromEnv,
  readAnalyticsSnapshot,
} from '../src/context/buildContext.js';
import type { EvidenceQuery } from '../src/context/evidenceRepository.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDataDir = path.join(here, 'fixtures', 'data-pipeline-data');
const SNAPSHOT_ID = 'test-snapshot';

type Item = Record<string, unknown> & { pk: string; sk: string };
type SendCommand = { input: { RequestItems: Record<string, { Keys: { pk: string; sk: string }[] }> } };

/**
 * 假的 DynamoDBDocumentClient：只要有 `send` 就夠。
 *
 * 刻意不用 aws-sdk-client-mock 之類的套件 —— 這裡要驗的是「item 怎麼變成
 * evidence」，不是 SDK 的行為，多一個依賴只是多一個要維護的東西。
 */
function fakeClient(items: Item[], options: { unprocessedOnce?: boolean } = {}) {
  let call = 0;
  const send = vi.fn(async (command: SendCommand) => {
    call += 1;
    const table = Object.keys(command.input.RequestItems)[0]!;
    const keys = command.input.RequestItems[table]!.Keys;
    const matched = items.filter((item) =>
      keys.some((key) => key.pk === item.pk && key.sk === item.sk),
    );
    // 第一次只回一筆並把其餘宣告為 UnprocessedKeys，用來驗證重試。
    if (options.unprocessedOnce === true && call === 1) {
      const returned = matched.slice(0, 1);
      return {
        Responses: { [table]: returned },
        UnprocessedKeys: {
          [table]: {
            Keys: keys.filter(
              (key) => !returned.some((item) => item.pk === key.pk && item.sk === key.sk),
            ),
          },
        },
      };
    }
    return { Responses: { [table]: matched }, UnprocessedKeys: {} };
  });
  return { client: { send } as never, send };
}

function encode(value: unknown): Uint8Array {
  return gzipSync(Buffer.from(JSON.stringify(value), 'utf-8'));
}

/**
 * 用 fixture 快照組出 analytics Lambda 會寫進表的 item。
 * 形狀對應 `dynamodb_projection.py` 的 `_ai_context_items`。
 */
async function fixtureItems(): Promise<Item[]> {
  const snapshotDir = path.join(fixtureDataDir, 'analytics', 'published', SNAPSHOT_ID);
  const manifest: unknown = JSON.parse(await readFile(path.join(snapshotDir, 'manifest.json'), 'utf-8'));
  const snapshot = await readAnalyticsSnapshot(fixtureDataDir, SNAPSHOT_ID);

  const items: Item[] = [
    {
      ...AI_CONTEXT_MANIFEST_KEY,
      snapshot_id: SNAPSHOT_ID,
      encoding: AI_CONTEXT_ENCODING,
      payload: encode(manifest),
    },
  ];
  for (const artifact of snapshot.artifacts) {
    const content: unknown = JSON.parse(await readFile(artifact.absolutePath, 'utf-8'));
    items.push({
      ...aiContextArtifactKey(artifact.key),
      snapshot_id: SNAPSHOT_ID,
      artifact_key: artifact.key,
      encoding: AI_CONTEXT_ENCODING,
      payload: encode(content),
    });
  }
  items.push({ ...META_MANIFEST_KEY, snapshot_id: SNAPSHOT_ID });
  return items;
}

function repository(items: Item[], options?: { unprocessedOnce?: boolean }) {
  const { client, send } = fakeClient(items, options);
  return {
    repo: new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client }),
    send,
  };
}

/**
 * 這組是整個設計的核心保證：同一個查詢從 DynamoDB 讀跟從本機快照讀，
 * 結果（evidence、順序、notes）必須**完全相同**。不同的話，本機跑的
 * `npm run precompute` 產生的 fingerprint 在線上永遠 miss，explain / policyCopilot
 * 每次都即時算 50–58 秒。
 */
describe('DynamoEvidenceRepository 與本機快照一致', () => {
  const queries: [string, EvidenceQuery][] = [
    ['沒有條件（全讀）', {}],
    ['employment 主題', { focusArea: 'employment' }],
    ['fertility 主題＋單一行政區', { focusArea: 'fertility', districtNames: ['板橋區'] }],
    ['participation 主題＋截斷', { focusArea: 'participation', limitPerDataset: 3 }],
    ['只指名一個 dataset', { datasets: ['analytics_policy_support'] }],
  ];

  it.each(queries)('%s', async (_label, query) => {
    const { repo } = repository(await fixtureItems());
    const local = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir, SNAPSHOT_ID);

    const [fromDynamo, fromFiles] = await Promise.all([repo.query(query), local.query(query)]);

    expect(fromDynamo.evidence.length).toBeGreaterThan(0);
    expect(fromDynamo).toEqual(fromFiles);
  });
});

describe('DynamoEvidenceRepository', () => {
  it('只抓這次主題需要的 artifact', async () => {
    const { repo, send } = repository(await fixtureItems());

    await repo.query({ focusArea: 'fertility' });

    const artifactKeys = send.mock.calls[1]![0].input.RequestItems['test-analytics']!.Keys.map(
      (key) => key.sk,
    );
    expect(artifactKeys).toContain('ARTIFACT#fertility');
    expect(artifactKeys).not.toContain('ARTIFACT#employment');
  });

  /**
   * schema 文件說得很明白：manifest 不存在就代表 pipeline 還沒發布。
   * 這種情況要誠實回空集合＋說明，**不要丟錯** —— 丟錯的話呼叫端會變成 502，
   * 而正確的行為是回「資料不足」。
   */
  it('沒有 META/MANIFEST 時回空集合與說明，不丟錯', async () => {
    const items = (await fixtureItems()).filter((item) => item.pk !== 'META');
    const { repo } = repository(items);

    const bundle = await repo.query({ focusArea: 'employment' });

    expect(bundle.evidence).toEqual([]);
    expect(bundle.notes.join('\n')).toContain('還沒發布');
  });

  it('表是舊版 writer 寫的（沒有 AI_CONTEXT）時說清楚要重跑 analytics Lambda', async () => {
    const { repo } = repository([{ ...META_MANIFEST_KEY, snapshot_id: SNAPSHOT_ID }]);

    const bundle = await repo.query({ focusArea: 'employment' });

    expect(bundle.evidence).toEqual([]);
    expect(bundle.notes.join('\n')).toContain('AI_CONTEXT/MANIFEST');
  });

  it('META 與 AI_CONTEXT 不是同一個快照時不混用', async () => {
    const items = (await fixtureItems()).map((item) =>
      item.pk === 'META' ? { ...item, snapshot_id: 'newer-snapshot' } : item,
    );
    const { repo } = repository(items);

    const bundle = await repo.query({ focusArea: 'employment' });

    expect(bundle.evidence).toEqual([]);
    expect(bundle.notes.join('\n')).toContain('不是同一個快照');
  });

  it('manifest 宣告的 artifact 不在表裡時丟錯，不靜默少一個面向', async () => {
    const items = (await fixtureItems()).filter((item) => item.sk !== 'ARTIFACT#employment');
    const { repo } = repository(items);

    await expect(repo.query({ focusArea: 'employment' })).rejects.toThrow('ARTIFACT#employment');
  });

  it('artifact 屬於別的快照時丟錯', async () => {
    const items = (await fixtureItems()).map((item) =>
      item.sk === 'ARTIFACT#employment' ? { ...item, snapshot_id: 'older-snapshot' } : item,
    );
    const { repo } = repository(items);

    await expect(repo.query({ focusArea: 'employment' })).rejects.toThrow('older-snapshot');
  });

  /**
   * DynamoDB 被節流時會回傳部分結果**而不報錯**。不重試的話症狀是
   * 「有些指標時有時無」，那是最難查的一種 bug。
   */
  it('UnprocessedKeys 會重試', async () => {
    const { repo, send } = repository(await fixtureItems(), { unprocessedOnce: true });

    const bundle = await repo.query({ focusArea: 'employment' });

    expect(send.mock.calls.length).toBeGreaterThan(2);
    expect(bundle.evidence.length).toBeGreaterThan(0);
  });
});

describe('createEvidenceRepositoryFromEnv 的 dynamo 模式', () => {
  it('AI_EVIDENCE_SOURCE=dynamo 需要 ANALYTICS_TABLE_NAME', () => {
    expect(() => createEvidenceRepositoryFromEnv({ AI_EVIDENCE_SOURCE: 'dynamo' })).toThrow(
      'ANALYTICS_TABLE_NAME',
    );
  });

  it('設了表名就用 DynamoDB', () => {
    const repo = createEvidenceRepositoryFromEnv({
      AI_EVIDENCE_SOURCE: 'dynamo',
      ANALYTICS_TABLE_NAME: 'newtaipei-youth-analytics',
      AWS_DEFAULT_REGION: 'us-west-2',
    });
    expect(repo.description).toBe('dynamodb(newtaipei-youth-analytics)');
  });

  it('dynamodb 也是合法的寫法', () => {
    const repo = createEvidenceRepositoryFromEnv({
      AI_EVIDENCE_SOURCE: 'dynamodb',
      ANALYTICS_TABLE_NAME: 't',
    });
    expect(repo.description).toContain('dynamodb');
  });
});
