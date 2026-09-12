/**
 * 環境變數解析，集中一個地方處理「同一件事有好幾個變數名」的問題。
 *
 * 現實情況：黑客松的 `.env` 是隊上共用的，變數名不一定跟這個服務原本假設的一樣
 * （例如模型是 `MODEL_NAMME`，Bedrock API key 叫 `CLAUDE_KEY`）。
 * 與其要求大家改共用檔案，這裡接受多個別名，並在 `description` 裡回報實際用了什麼，
 * 這樣設錯的時候看輸出就知道。
 */

export type BedrockAuthMode = 'sigv4' | 'bearer';

export interface BedrockEnvConfig {
  modelId: string | null;
  region: string | null;
  /** Bedrock API key（bearer token），主控台產生的那種，值以 `ABSK` 開頭。 */
  apiKey: string | null;
  authMode: BedrockAuthMode;
  /** 實際採用的變數名，放進 description 方便排查。 */
  resolvedFrom: { modelId: string | null; region: string | null; apiKey: string | null };
}

/** 依序嘗試，先找到的優先。第一個是這個服務的正式名稱，後面是相容別名。 */
const MODEL_ID_KEYS = ['BEDROCK_MODEL_ID', 'MODEL_NAMME', 'MODEL_NAME', 'BEDROCK_MODEL'] as const;
/**
 * `BEDROCK_REGION` 刻意排在最前面。
 *
 * 原因是 Lambda：`AWS_REGION` 是 Lambda 的保留環境變數，執行時**一定會被自動設成
 * 這個 function 所在的 region**。如果 `AWS_REGION` 優先，那麼「Lambda 部署在 A 區、
 * Bedrock 模型只在 B 區」的情況下，`BEDROCK_REGION` 會永遠被蓋掉而完全失效 ——
 * 而且錯誤訊息會是「找不到 model identifier」，很難聯想到是 region 被覆寫。
 */
const REGION_KEYS = ['BEDROCK_REGION', 'AWS_REGION', 'AWS_DEFAULT_REGION'] as const;
/**
 * `AWS_BEARER_TOKEN_BEDROCK` 是 AWS SDK 自己會讀的標準變數名。
 * `CLAUDE_KEY` 是隊上 `.env` 用的名字 —— 名字看起來像 Anthropic 的 key，
 * 但值以 `ABSK` 開頭，那是 **Amazon Bedrock API key**，不是 Anthropic API key，
 * 所以要走 Bedrock 的 bearer 認證，不是接 Anthropic 的 SDK。
 */
const API_KEY_KEYS = ['AWS_BEARER_TOKEN_BEDROCK', 'BEDROCK_API_KEY', 'CLAUDE_KEY'] as const;

export function resolveBedrockEnv(env: NodeJS.ProcessEnv = process.env): BedrockEnvConfig {
  const model = pick(env, MODEL_ID_KEYS);
  const region = pick(env, REGION_KEYS);
  const apiKey = pick(env, API_KEY_KEYS);

  return {
    modelId: model.value,
    region: region.value,
    apiKey: apiKey.value,
    authMode: resolveAuthMode(env, apiKey.value),
    resolvedFrom: { modelId: model.key, region: region.key, apiKey: apiKey.key },
  };
}

/**
 * 決定用哪種認證。
 *
 * 為什麼要能選：`.env` 裡同時有 STS 臨時憑證（`AWS_ACCESS_KEY_ID` 以 `ASIA` 開頭
 * ＋ `AWS_SESSION_TOKEN`）和一組 Bedrock API key。臨時憑證會過期（通常幾小時），
 * demo 進行到一半失效是很現實的風險；Bedrock API key 通常活得久一些。
 * 所以兩條路都留著，可以用 `BEDROCK_AUTH=bearer` 手動切過去，不用改程式。
 *
 * 預設維持 AWS SDK 原本的優先順序（有 sigv4 憑證就用 sigv4），避免跟其他 AWS
 * 工具的行為不一致造成困惑。
 */
function resolveAuthMode(env: NodeJS.ProcessEnv, apiKey: string | null): BedrockAuthMode {
  const explicit = env.BEDROCK_AUTH?.toLowerCase();
  if (explicit === 'bearer' || explicit === 'sigv4') {
    return explicit;
  }
  const hasSigV4 = Boolean(env.AWS_ACCESS_KEY_ID) || Boolean(env.AWS_PROFILE);
  if (hasSigV4) {
    return 'sigv4';
  }
  return apiKey ? 'bearer' : 'sigv4';
}

/** 提醒訊息：設定明顯不對時，早點講清楚，不要等呼叫失敗才猜。 */
export function describeEnvProblems(config: BedrockEnvConfig, env: NodeJS.ProcessEnv = process.env): string[] {
  const problems: string[] = [];

  if (config.modelId === null) {
    problems.push(`找不到模型設定，請設定 ${MODEL_ID_KEYS.join(' 或 ')}。`);
  }
  if (config.region === null) {
    problems.push(`找不到 region 設定，請設定 ${REGION_KEYS.join(' 或 ')}。`);
  }
  if (config.authMode === 'bearer' && config.apiKey === null) {
    problems.push(`BEDROCK_AUTH=bearer 但找不到 API key，請設定 ${API_KEY_KEYS.join(' 或 ')}。`);
  }
  if (config.authMode === 'sigv4' && !env.AWS_ACCESS_KEY_ID && !env.AWS_PROFILE) {
    problems.push(
      '要用 sigv4 但沒有 AWS_ACCESS_KEY_ID / AWS_PROFILE。' +
        '如果只有 Bedrock API key，設定 BEDROCK_AUTH=bearer。',
    );
  }
  if (config.apiKey !== null && !config.apiKey.startsWith('ABSK')) {
    problems.push(
      `${config.resolvedFrom.apiKey} 的值不是以 ABSK 開頭，可能不是 Amazon Bedrock API key。` +
        'Anthropic 自家的 API key（sk-ant- 開頭）在 Bedrock 上不能用。',
    );
  }
  if (env.AWS_ACCESS_KEY_ID?.startsWith('ASIA') && !env.AWS_SESSION_TOKEN) {
    problems.push(
      'AWS_ACCESS_KEY_ID 是 ASIA 開頭的臨時憑證，但沒有 AWS_SESSION_TOKEN，這組憑證不會生效。',
    );
  }

  return problems;
}

function pick(
  env: NodeJS.ProcessEnv,
  keys: readonly string[],
): { key: string | null; value: string | null } {
  for (const key of keys) {
    const value = env[key]?.trim();
    if (value) {
      return { key, value };
    }
  }
  return { key: null, value: null };
}
