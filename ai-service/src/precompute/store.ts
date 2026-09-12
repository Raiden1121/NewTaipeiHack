/**
 * 預先算結果的存放層。
 *
 * explain 與 policyCopilot 沒有使用者問題 —— 它們的輸出是
 * `(行政區, 主題, 那批 evidence)` 的純函數，而且是給 dashboard 卡片用的。
 * 實測 Sonnet 4-6 各要 50 秒與 58 秒，遠超 API Gateway HTTP API 固定的 30 秒
 * 上限（那個上限不可調，見 `DEPLOYMENT.md`）。這種東西不該即時算。
 *
 * 介面刻意只有 get / put / list 三個動作，實作可以換成 S3 或 DynamoDB
 * 而不動呼叫端 —— 那是 infra 隊友的範圍，這裡先給檔案版讓功能能跑。
 */
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { z } from 'zod';
import { StructuredOutputSchema } from '../types/structuredOutput.js';
import { SourceAttributionSchema } from '../types/sourceAttribution.js';

/**
 * 一筆預先算的結果。
 *
 * `generatedBy` / `generatedAt` / `modelId` 都要存：demo 當天看到一份可疑的
 * 卡片內容時，第一個問題一定是「這是哪個模型什麼時候算的」。沒存的話只能猜。
 */
export const PrecomputedEntrySchema = z.object({
  fingerprint: z.string().min(1),
  action: z.string().min(1),
  focusDistrict: z.string().nullable(),
  focusArea: z.string().nullable(),
  /** 產生當時的 analytics 快照 id。純資訊用途，比對還是靠 fingerprint。 */
  snapshotId: z.string().nullable(),
  generatedAt: z.string().min(1),
  /** `BedrockClient.description`，含模型 id 與 region。 */
  generatedBy: z.string().min(1),
  /** 產生這份結果實際花了多久，用來回答「批次要跑多久」。 */
  elapsedMs: z.number().int().nonnegative(),
  output: StructuredOutputSchema,
  sources: z.array(SourceAttributionSchema),
});
export type PrecomputedEntry = z.infer<typeof PrecomputedEntrySchema>;

export interface PrecomputedStore {
  /** 給錯誤訊息與回應用的描述，例如 `file(...)` 或 `disabled`。 */
  readonly description: string;
  get(fingerprint: string): Promise<PrecomputedEntry | null>;
  put(entry: PrecomputedEntry): Promise<void>;
  list(): Promise<PrecomputedEntry[]>;
}

/**
 * 沒設定存放位置時用這個 —— 一律 miss，行為完全等於「沒有快取」。
 *
 * 預設是關閉而不是開啟：快取寫在 Lambda 的本機磁碟只會有短暫效果
 * （每個執行環境各自一份，而且會被回收），設定成什麼位置是部署時的決定，
 * 不該由這個模組猜。
 */
export class DisabledPrecomputedStore implements PrecomputedStore {
  readonly description = 'disabled';

  async get(): Promise<PrecomputedEntry | null> {
    return null;
  }

  async put(): Promise<void> {
    // 刻意什麼都不做：呼叫端不需要為「有沒有設快取」寫兩套流程。
  }

  async list(): Promise<PrecomputedEntry[]> {
    return [];
  }
}

/** 一個 fingerprint 一個 JSON 檔。檔名就是 fingerprint（十六進位，檔名安全）。 */
export class FilePrecomputedStore implements PrecomputedStore {
  readonly description: string;

  constructor(private readonly dir: string) {
    this.description = `file(${dir})`;
  }

  async get(fingerprint: string): Promise<PrecomputedEntry | null> {
    if (!isValidFingerprint(fingerprint)) {
      // 查詢用不合法的鍵一律當 miss：查不到就重新算，行為是安全的。
      return null;
    }
    let raw: string;
    try {
      raw = await readFile(this.pathFor(fingerprint), 'utf-8');
    } catch {
      // 檔案不存在是正常的 miss，不是錯誤。
      return null;
    }
    const parsed = PrecomputedEntrySchema.safeParse(JSON.parse(raw));
    if (!parsed.success) {
      // 舊格式或壞檔一律當 miss。這裡如果丟錯，一個壞檔會讓整個功能掛掉，
      // 而正確的降級行為是「重新算一次」。
      return null;
    }
    return parsed.data;
  }

  async put(entry: PrecomputedEntry): Promise<void> {
    await mkdir(this.dir, { recursive: true });
    await writeFile(this.pathFor(entry.fingerprint), `${JSON.stringify(entry, null, 2)}\n`, 'utf-8');
  }

  async list(): Promise<PrecomputedEntry[]> {
    let names: string[];
    try {
      names = await readdir(this.dir);
    } catch {
      return [];
    }
    const entries: PrecomputedEntry[] = [];
    for (const name of names.filter((item) => item.endsWith('.json'))) {
      const parsed = PrecomputedEntrySchema.safeParse(
        JSON.parse(await readFile(join(this.dir, name), 'utf-8')),
      );
      if (parsed.success) {
        entries.push(parsed.data);
      }
    }
    return entries;
  }

  private pathFor(fingerprint: string): string {
    if (!isValidFingerprint(fingerprint)) {
      throw new Error(
        `fingerprint「${fingerprint}」不是合法的十六進位字串，拒絕當檔名使用。` +
          'fingerprint 一律由 contextFingerprint() 產生（sha256 十六進位）。',
      );
    }
    return join(this.dir, `${fingerprint.toLowerCase()}.json`);
  }
}

/**
 * fingerprint 一律是 sha256 的十六進位字串，會直接變成檔名。
 *
 * 刻意用**嚴格驗證**而不是「把不合法的字元過濾掉」。過濾看起來比較寬容，
 * 但那會讓 `ab/cd` 與 `abcd` 對到同一個檔案 —— 不同的鍵指到同一份結果，
 * 也就是「回了別人的答案」，而這正是整個快取設計最不能出的錯。
 * 路徑穿越也是同一件事的另一面（`../../x` 過濾後會剩下一段看起來正常的字）。
 */
function isValidFingerprint(fingerprint: string): boolean {
  return /^[a-f0-9]{4,}$/i.test(fingerprint);
}

/**
 * 依環境變數決定要不要開快取。
 *
 * `AI_PRECOMPUTE_DIR` 沒設就是關閉 —— 見 `DisabledPrecomputedStore` 的說明。
 */
export function createPrecomputedStoreFromEnv(
  env: NodeJS.ProcessEnv = process.env,
): PrecomputedStore {
  const dir = env.AI_PRECOMPUTE_DIR?.trim();
  if (dir === undefined || dir.length === 0) {
    return new DisabledPrecomputedStore();
  }
  return new FilePrecomputedStore(dir);
}
