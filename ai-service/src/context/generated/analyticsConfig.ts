/**
 * ⚠️ 這個檔案是產生出來的，不要手動改。
 *
 * 來源：`data-pipeline/config/homepage_analytics.json`
 * 重新產生：`npm run sync:metric-config`
 * 漂移偵測：`npm run dev:metric-audit`（內容跟來源不一致就會報出來）
 *
 * ## 為什麼是「複製一份」而不是直接 import 那個 JSON
 *
 * 直接 `import '../../../data-pipeline/config/homepage_analytics.json'` 實測會壞：
 * 跨出 `src/` 之後 tsc 推導的 rootDir 變成 repo 根目錄，輸出跑到
 * `dist/ai-service/src/handlers/`，而 Lambda 的 handler 路徑是
 * `dist/handlers/lambda.handler` —— 乾淨 build 之後就找不到進入點了。
 * （另外 NodeNext ESM 匯入 JSON 還需要 import attributes，跨 runtime 支援不一。）
 *
 * 所以改成產生一份 TS 模組放在 `src/` 裡面。單一事實來源仍然是 pipeline 的
 * config —— 這裡只是它的投影，而且不一致時稽核會擋下來。
 */

/** `data-pipeline/config/homepage_analytics.json` 的 `version`。 */
export const ANALYTICS_CONFIG_VERSION = '2';

/** Youth Opportunity Index 五個子分數的權重（相加為 1）。 */
export const YOI_WEIGHTS = {
  job: 0.25,
  salary: 0.25,
  talent: 0.15,
  housing: 0.2,
  transport: 0.15,
} as const;

/** 子分數的正規化方式。 */
export const NORMALIZATION = {
  method: 'min_max',
  constantValue: 50,
} as const;

/** Family-Friendliness Index 的權重（百分比，相加為 100）與薪資收縮參數。 */
export const FAFI = {
  salaryShrinkageK: 30,
  weights: {
    daycareCoverage: 45,
    housing: 45,
    salary: 10,
  },
} as const;

/** 服務涵蓋率的判定半徑（公尺）。 */
export const SERVICE_RADIUS_M = 2500;

/** 產生這份檔案時，來源 config 的原始內容（用來偵測漂移）。 */
export const SOURCE_CONFIG_SNAPSHOT = {
  version: '2',
  normalization: { method: 'min_max', constant_value: 50 },
  yoi_weights: { job: 0.25, salary: 0.25, talent: 0.15, housing: 0.2, transport: 0.15 },
  fafi: {
    salary_shrinkage_k: 30,
    weights: { daycare_coverage: 45, housing: 45, salary: 10 },
  },
  service_radius_m: 2500,
} as const;
