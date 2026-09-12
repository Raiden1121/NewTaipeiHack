/**
 * 讀 data-pipeline 的行政區清單。
 *
 * 為什麼不在 ai-service 自己寫一份 29 區的陣列：那份清單會跟 pipeline 的
 * `district_id` 對不上（改制、正名、或單純打錯字），而 evidence 的
 * `districtName` 是 pipeline 產生的。硬寫一份的結果是「有幾區永遠算不出來」，
 * 而且不會有任何錯誤訊息。
 */
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { z } from 'zod';

const DistrictsFileSchema = z.object({
  districts: z.array(
    z.object({
      district_id: z.string(),
      district_name: z.string(),
    }),
  ),
});

/**
 * 從 dataDir 推出 config 的位置：`data-pipeline/data` → `data-pipeline/config`。
 * 用 `AI_DISTRICTS_FILE` 可以直接指定，測試與非標準佈局時用得到。
 */
export function defaultDistrictsFile(dataDir: string, env: NodeJS.ProcessEnv = process.env): string {
  const override = env.AI_DISTRICTS_FILE?.trim();
  if (override !== undefined && override.length > 0) {
    return override;
  }
  return join(dirname(dataDir), 'config', 'districts.json');
}

export async function readDistrictNames(path: string): Promise<string[]> {
  let raw: string;
  try {
    raw = await readFile(path, 'utf-8');
  } catch {
    throw new Error(
      `讀不到行政區清單 ${path}。` +
        '請確認 data-pipeline 的 config 存在，或用 AI_DISTRICTS_FILE 指定位置。',
    );
  }
  const parsed = DistrictsFileSchema.parse(JSON.parse(raw));
  const names = parsed.districts.map((item) => item.district_name.trim()).filter((name) => name.length > 0);
  if (names.length === 0) {
    throw new Error(`${path} 裡沒有任何行政區。`);
  }
  return names;
}
