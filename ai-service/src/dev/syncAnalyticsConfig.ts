/**
 * 從 pipeline 的 config 重新產生 `src/context/generated/analyticsConfig.ts`：
 * `npm run sync:metric-config`
 *
 * pipeline 改了權重之後跑這一支，然後 commit 產生出來的檔案。
 * 忘記跑的話 `npm run dev:metric-audit` 會報出漂移。
 *
 * 為什麼要產生檔案而不是直接 import 那個 JSON —— 見產生出來的檔案開頭的說明。
 */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';

/**
 * 只驗證我們真的會用到的欄位。
 *
 * 刻意不用 `.strict()`：pipeline 在這個 config 裡加自己的欄位是他們的自由，
 * 不該因為多了一個跟 AI 無關的設定就讓這支腳本失敗。
 */
const ConfigSchema = z.object({
  version: z.union([z.string(), z.number()]).transform(String),
  normalization: z.object({
    method: z.string(),
    constant_value: z.number(),
  }),
  yoi_weights: z.object({
    job: z.number(),
    salary: z.number(),
    talent: z.number(),
    housing: z.number(),
    transport: z.number(),
  }),
  fafi: z.object({
    salary_shrinkage_k: z.number(),
    weights: z.object({
      daycare_coverage: z.number(),
      housing: z.number(),
      salary: z.number(),
    }),
  }),
  service_radius_m: z.number(),
});

export function analyticsConfigPath(env: NodeJS.ProcessEnv = process.env): string {
  const override = env.AI_ANALYTICS_CONFIG?.trim();
  if (override !== undefined && override.length > 0) {
    return override;
  }
  const here = path.dirname(fileURLToPath(import.meta.url));
  // src/dev → src → ai-service → <repo root>
  return path.resolve(here, '..', '..', '..', 'data-pipeline', 'config', 'homepage_analytics.json');
}

export async function readAnalyticsConfig(
  configPath: string = analyticsConfigPath(),
): Promise<z.infer<typeof ConfigSchema>> {
  let raw: string;
  try {
    raw = await readFile(configPath, 'utf-8');
  } catch {
    throw new Error(
      `讀不到 pipeline 的 analytics config：${configPath}。` +
        '可用 AI_ANALYTICS_CONFIG 指定位置。',
    );
  }
  return ConfigSchema.parse(JSON.parse(raw));
}

function render(config: z.infer<typeof ConfigSchema>): string {
  const w = config.yoi_weights;
  const f = config.fafi;
  const sum = w.job + w.salary + w.talent + w.housing + w.transport;
  // 權重加起來不是 1 的話，prompt 上寫出來的貢獻度計算會是錯的 ——
  // 寧可在這裡停下來，也不要產生一份會誤導模型的定義。
  if (Math.abs(sum - 1) > 1e-6) {
    throw new Error(`yoi_weights 加起來是 ${sum}，不是 1。請先確認 pipeline 的 config。`);
  }
  const fafiSum = f.weights.daycare_coverage + f.weights.housing + f.weights.salary;
  if (Math.abs(fafiSum - 100) > 1e-6) {
    throw new Error(`fafi.weights 加起來是 ${fafiSum}，不是 100。`);
  }

  return `/**
 * ⚠️ 這個檔案是產生出來的，不要手動改。
 *
 * 來源：\`data-pipeline/config/homepage_analytics.json\`
 * 重新產生：\`npm run sync:metric-config\`
 * 漂移偵測：\`npm run dev:metric-audit\`（內容跟來源不一致就會報出來）
 *
 * ## 為什麼是「複製一份」而不是直接 import 那個 JSON
 *
 * 直接 \`import '../../../data-pipeline/config/homepage_analytics.json'\` 實測會壞：
 * 跨出 \`src/\` 之後 tsc 推導的 rootDir 變成 repo 根目錄，輸出跑到
 * \`dist/ai-service/src/handlers/\`，而 Lambda 的 handler 路徑是
 * \`dist/handlers/lambda.handler\` —— 乾淨 build 之後就找不到進入點了。
 * （另外 NodeNext ESM 匯入 JSON 還需要 import attributes，跨 runtime 支援不一。）
 *
 * 所以改成產生一份 TS 模組放在 \`src/\` 裡面。單一事實來源仍然是 pipeline 的
 * config —— 這裡只是它的投影，而且不一致時稽核會擋下來。
 */

/** \`data-pipeline/config/homepage_analytics.json\` 的 \`version\`。 */
export const ANALYTICS_CONFIG_VERSION = '${config.version}';

/** Youth Opportunity Index 五個子分數的權重（相加為 1）。 */
export const YOI_WEIGHTS = {
  job: ${w.job},
  salary: ${w.salary},
  talent: ${w.talent},
  housing: ${w.housing},
  transport: ${w.transport},
} as const;

/** 子分數的正規化方式。 */
export const NORMALIZATION = {
  method: '${config.normalization.method}',
  constantValue: ${config.normalization.constant_value},
} as const;

/** Family-Friendliness Index 的權重（百分比，相加為 100）與薪資收縮參數。 */
export const FAFI = {
  salaryShrinkageK: ${f.salary_shrinkage_k},
  weights: {
    daycareCoverage: ${f.weights.daycare_coverage},
    housing: ${f.weights.housing},
    salary: ${f.weights.salary},
  },
} as const;

/** 服務涵蓋率的判定半徑（公尺）。 */
export const SERVICE_RADIUS_M = ${config.service_radius_m};

/** 產生這份檔案時，來源 config 的原始內容（用來偵測漂移）。 */
export const SOURCE_CONFIG_SNAPSHOT = {
  version: '${config.version}',
  normalization: { method: '${config.normalization.method}', constant_value: ${config.normalization.constant_value} },
  yoi_weights: { job: ${w.job}, salary: ${w.salary}, talent: ${w.talent}, housing: ${w.housing}, transport: ${w.transport} },
  fafi: {
    salary_shrinkage_k: ${f.salary_shrinkage_k},
    weights: { daycare_coverage: ${f.weights.daycare_coverage}, housing: ${f.weights.housing}, salary: ${f.weights.salary} },
  },
  service_radius_m: ${config.service_radius_m},
} as const;
`;
}

const configPath = analyticsConfigPath();
const config = await readAnalyticsConfig(configPath);
const here = path.dirname(fileURLToPath(import.meta.url));
const outPath = path.resolve(here, '..', 'context', 'generated', 'analyticsConfig.ts');

await mkdir(path.dirname(outPath), { recursive: true });
await writeFile(outPath, render(config), 'utf-8');

console.log(`來源: ${configPath}`);
console.log(`輸出: ${outPath}`);
console.log(`版本: v${config.version}`);
console.log(
  `YOI 權重: ${Object.entries(config.yoi_weights)
    .map(([k, v]) => `${k}=${v}`)
    .join(' ')}`,
);
console.log('產生完成。記得 commit 這個檔案。');
