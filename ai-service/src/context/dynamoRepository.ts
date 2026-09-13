/**
 * 從 DynamoDB 的 analytics 表讀 evidence（線上正式路徑）。
 *
 * ## 讀的是 `AI_CONTEXT` item，不是 dashboard 用的 item
 *
 * `DASHBOARD/*`、`ANALYSIS#*` 是依 `api_contract.md` 裁切過的形狀，少了
 * `citySummary`、`daycareCoverage`、逐區的 employment / fertility 分析。
 * 以前這裡把那些 item 包回快照形狀再攤平，結果 employment 少 17 種指標、
 * fertility 少 48 種，而且 evidence 跟本機快照對不上 → 預先算永遠 miss。
 *
 * 現在 analytics Lambda 另外把**完整的** published snapshot 寫進同一張表
 * （`infrastructure/modules/analytics_lambda/lambda/dynamodb_projection.py`）：
 *
 * | pk | sk | 內容 |
 * |---|---|---|
 * | `AI_CONTEXT` | `MANIFEST` | 完整 `manifest.json` |
 * | `AI_CONTEXT` | `ARTIFACT#<key>` | 該 artifact 的完整 JSON |
 *
 * 內容是 gzip 過的 JSON 文字（`payload`，Binary），不是 DynamoDB Map：
 *
 * 1. Map 不保證 key 順序，而攤平後的 evidence 順序決定 `limitPerDataset` 截掉哪些。
 *    順序一變，evidence 子集就變，fingerprint 就對不上。
 * 2. 最大的 `dashboard_overview` 原始 472KB，超過單筆 400KB 上限；gzip 後約 49KB。
 *
 * 讀回來之後交給 `buildAnalyticsEvidenceBundle()`，跟本機快照是同一份程式，
 * 所以兩邊產生的 evidence（含順序、notes、sourcePath）相同。
 *
 * ## 完整性
 *
 * writer 最後才寫 `META/MANIFEST`。這裡要求它跟 `AI_CONTEXT` item 的 `snapshot_id`
 * 一致；不一致代表新快照寫到一半，回空集合＋說明，不混用兩個快照的資料。
 *
 * ## 兩次 BatchGetItem
 *
 * 第一次拿兩份 manifest，第二次只拿這次主題需要的 artifact（最多 7 筆）。
 * 不用 Query 也不用 Scan（IAM 刻意只給 GetItem / BatchGetItem）。
 */
import { gunzipSync } from 'node:zlib';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, BatchGetCommand } from '@aws-sdk/lib-dynamodb';
import { parseAnalyticsManifest, type AnalyticsArtifactRef } from './analyticsSnapshot.js';
import { buildAnalyticsEvidenceBundle, selectArtifacts } from './analyticsSnapshotRepository.js';
import type { EvidenceBundle, EvidenceQuery, EvidenceRepository } from './evidenceRepository.js';

/** 表的 key。`pk`/`sk` 都是 String，見 `modules/analytics_table/main.tf`。 */
export interface DynamoItemKey {
  pk: string;
  sk: string;
}

export const META_MANIFEST_KEY: DynamoItemKey = { pk: 'META', sk: 'MANIFEST' };
export const AI_CONTEXT_MANIFEST_KEY: DynamoItemKey = { pk: 'AI_CONTEXT', sk: 'MANIFEST' };
/** writer 寫入 `payload` 的編碼。改格式時兩邊要一起改。 */
export const AI_CONTEXT_ENCODING = 'gzip+json';

export function aiContextArtifactKey(artifactKey: string): DynamoItemKey {
  return { pk: 'AI_CONTEXT', sk: `ARTIFACT#${artifactKey}` };
}

export interface DynamoEvidenceRepositoryOptions {
  tableName: string;
  region?: string;
  /** 測試用：塞一個假的 document client。 */
  documentClient?: DynamoDBDocumentClient;
}

export class DynamoEvidenceRepository implements EvidenceRepository {
  readonly description: string;
  private readonly client: DynamoDBDocumentClient;
  private readonly tableName: string;

  constructor(options: DynamoEvidenceRepositoryOptions) {
    this.tableName = options.tableName;
    this.client =
      options.documentClient ??
      DynamoDBDocumentClient.from(
        new DynamoDBClient(options.region === undefined ? {} : { region: options.region }),
      );
    this.description = `dynamodb(${options.tableName})`;
  }

  async query(query: EvidenceQuery): Promise<EvidenceBundle> {
    const heads = await this.batchGet([META_MANIFEST_KEY, AI_CONTEXT_MANIFEST_KEY]);

    const meta = heads.get(keyOf(META_MANIFEST_KEY));
    if (meta === undefined) {
      // 這正是 schema 文件說的「manifest 不存在就是還沒發布」。
      // 誠實回空集合＋說明，不要丟錯 —— 呼叫端會據此回「資料不足」。
      return emptyBundle(
        `DynamoDB 表 ${this.tableName} 裡沒有 META/MANIFEST，` +
          '代表 data-pipeline 還沒發布任何 analytics snapshot，本次沒有可引用的資料。',
      );
    }

    const contextManifest = heads.get(keyOf(AI_CONTEXT_MANIFEST_KEY));
    if (contextManifest === undefined) {
      return emptyBundle(
        `DynamoDB 表 ${this.tableName} 有 META/MANIFEST 但沒有 AI_CONTEXT/MANIFEST，` +
          '代表寫入這張表的 analytics Lambda 還是不會寫 AI context 的舊版本；' +
          '重新部署並執行 analytics Lambda 之後才有資料。',
      );
    }

    const snapshotId = asString(meta.snapshot_id);
    const contextSnapshotId = asString(contextManifest.snapshot_id);
    if (snapshotId === null || contextSnapshotId !== snapshotId) {
      return emptyBundle(
        `DynamoDB 表 ${this.tableName} 的 META/MANIFEST（${snapshotId ?? '無 snapshot_id'}）` +
          `與 AI_CONTEXT/MANIFEST（${contextSnapshotId ?? '無 snapshot_id'}）不是同一個快照，` +
          '可能正在寫入新快照；本次不混用兩份資料。',
      );
    }

    const manifest = decodePayload(contextManifest, 'AI_CONTEXT/MANIFEST');
    if (manifest === null || typeof manifest !== 'object' || Array.isArray(manifest)) {
      throw new Error(`AI_CONTEXT/MANIFEST 的內容不是物件（表 ${this.tableName}）`);
    }
    // dataDir 傳空字串：sourcePath 仍是 `analytics/published/<id>/...`，跟本機快照一致；
    // absolutePath 在這條路徑上用不到。
    const snapshot = parseAnalyticsManifest(manifest as Record<string, unknown>, '', snapshotId);

    // 先決定要讀哪些 artifact 並一次抓回來。notes 丟掉：buildAnalyticsEvidenceBundle
    // 會用同一個函式再選一次並寫 notes，這裡只是要知道該抓哪些 key。
    const wanted = selectArtifacts(snapshot.artifacts, query, []);
    const items = await this.batchGet(wanted.map((artifact) => aiContextArtifactKey(artifact.key)));

    return buildAnalyticsEvidenceBundle(snapshot, query, async (artifact: AnalyticsArtifactRef) => {
      const key = aiContextArtifactKey(artifact.key);
      const label = `${key.pk}/${key.sk}`;
      const item = items.get(keyOf(key));
      if (item === undefined) {
        // 跟本機快照「manifest 宣告了但讀不到檔案」同樣丟錯：少一個 artifact 卻照常回答，
        // 模型會把殘缺的資料當成完整的講。
        throw new Error(
          `AI_CONTEXT/MANIFEST 宣告了 artifact ${artifact.key}，但表 ${this.tableName} 裡沒有 ${label}。`,
        );
      }
      if (asString(item.snapshot_id) !== snapshotId) {
        throw new Error(
          `${label} 屬於快照 ${asString(item.snapshot_id) ?? '(unknown)'}，不是目前的 ${snapshotId}；` +
            '可能正在寫入新快照，請稍後重試。',
        );
      }
      return decodePayload(item, label);
    });
  }

  /**
   * BatchGetItem。刻意處理 `UnprocessedKeys`：DynamoDB 在被節流時會回傳部分結果
   * 而**不報錯**，不重試的話症狀是「有些指標時有時無」，非常難查。
   */
  private async batchGet(
    keys: readonly DynamoItemKey[],
  ): Promise<Map<string, Record<string, unknown>>> {
    const found = new Map<string, Record<string, unknown>>();
    let pending: DynamoItemKey[] = [...keys];

    for (let attempt = 0; attempt < 3 && pending.length > 0; attempt += 1) {
      const response = await this.client.send(
        new BatchGetCommand({ RequestItems: { [this.tableName]: { Keys: pending } } }),
      );
      for (const item of response.Responses?.[this.tableName] ?? []) {
        const record = item as Record<string, unknown>;
        const pk = asString(record.pk);
        const sk = asString(record.sk);
        if (pk !== null && sk !== null) {
          found.set(keyOf({ pk, sk }), record);
        }
      }
      const unprocessed = response.UnprocessedKeys?.[this.tableName]?.Keys ?? [];
      pending = unprocessed.map((key) => ({
        pk: String(key.pk),
        sk: String(key.sk),
      }));
    }

    return found;
  }
}

function emptyBundle(note: string): EvidenceBundle {
  return { evidence: [], totalMatched: 0, truncated: false, notes: [note] };
}

function decodePayload(item: Record<string, unknown>, label: string): unknown {
  if (item.encoding !== AI_CONTEXT_ENCODING) {
    throw new Error(
      `${label} 的 encoding 是 ${String(item.encoding)}，這個版本只讀 ${AI_CONTEXT_ENCODING}。`,
    );
  }
  const payload = item.payload;
  if (!(payload instanceof Uint8Array)) {
    throw new Error(`${label} 缺少 Binary 型別的 payload 欄位。`);
  }
  return JSON.parse(gunzipSync(payload).toString('utf-8')) as unknown;
}

function keyOf(key: DynamoItemKey): string {
  return `${key.pk}\u0000${key.sk}`;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}
