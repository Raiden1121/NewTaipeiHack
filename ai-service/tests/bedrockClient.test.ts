import { describe, expect, it, vi } from 'vitest';
import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import {
  BedrockRuntimeAdapter,
  DEFAULT_MAX_TOKENS,
  MockBedrockClient,
  createBedrockClientFromEnv,
  parseJsonPayload,
} from '../src/bedrock/client.js';
import { STRUCTURED_OUTPUT_SCHEMA_NAME } from '../src/types/structuredOutputJsonSchema.js';
import { formatKnownLimitations } from '../src/prompts/guardrails.js';
import type { PromptPayload } from '../src/prompts/promptPayload.js';
import { makeEvidenceReview, makeOutput } from './helpers.js';

const prompt: PromptPayload = {
  system: '你是測試用的助理。',
  user: '可用的 evidence：\n1. evidenceId="population:11507:1:youth_18_35_total"',
};

const validOutput = makeOutput({
  dataSufficiency: 'partial',
  evidenceReview: makeEvidenceReview({ missingForQuestion: ['缺就業面向指標'] }),
  limitations: ['僅有人口資料，缺少就業面向。'],
});

/** 假的 Bedrock client：依序回傳預設好的文字內容，並記下收到的 request。 */
function fakeClient(...texts: string[]) {
  const requests: unknown[] = [];
  let call = 0;
  return {
    requests,
    send: vi.fn(async (command: unknown) => {
      requests.push((command as ConverseCommand).input);
      const text = texts[Math.min(call, texts.length - 1)];
      call += 1;
      return { output: { message: { content: [{ text }] } }, stopReason: 'end_turn' };
    }),
  };
}

describe('BedrockRuntimeAdapter 送出的 Converse request', () => {
  it('帶上原生 structured outputs 設定，且 schema 是 JSON 字串', async () => {
    const client = fakeClient(JSON.stringify(validOutput));
    const adapter = new BedrockRuntimeAdapter({
      modelId: 'test-model',
      region: 'us-east-1',
      client,
    });

    await adapter.invokeStructured(prompt);

    const input = client.requests[0] as Record<string, any>;
    expect(input.modelId).toBe('test-model');
    expect(input.system).toEqual([{ text: prompt.system }]);
    expect(input.messages[0]).toEqual({ role: 'user', content: [{ text: prompt.user }] });

    const textFormat = input.outputConfig.textFormat;
    expect(textFormat.type).toBe('json_schema');
    expect(textFormat.structure.jsonSchema.name).toBe(STRUCTURED_OUTPUT_SCHEMA_NAME);
    // Bedrock 要求是字串，傳物件會被拒絕。
    expect(typeof textFormat.structure.jsonSchema.schema).toBe('string');
  });

  it('temperature 預設 0，因為這是引用資料做解讀而不是創作', async () => {
    const client = fakeClient(JSON.stringify(validOutput));
    await new BedrockRuntimeAdapter({ modelId: 'm', region: 'r', client }).invokeStructured(prompt);

    expect((client.requests[0] as Record<string, any>).inferenceConfig.temperature).toBe(0);
  });

  it('useStructuredOutputs=false 時不帶 outputConfig（給不支援的模型當逃生門）', async () => {
    const client = fakeClient(JSON.stringify(validOutput));
    const adapter = new BedrockRuntimeAdapter({
      modelId: 'm',
      region: 'r',
      client,
      useStructuredOutputs: false,
    });

    await adapter.invokeStructured(prompt);

    expect((client.requests[0] as Record<string, any>).outputConfig).toBeUndefined();
  });
});

describe('BedrockRuntimeAdapter 的回應處理', () => {
  it('回傳通過 zod 驗證的 structured output', async () => {
    const adapter = new BedrockRuntimeAdapter({
      modelId: 'm',
      region: 'r',
      client: fakeClient(JSON.stringify(validOutput)),
    });

    const result = await adapter.invokeStructured(prompt);

    expect(result.dataSufficiency).toBe('partial');
    expect(result.basis[0]?.evidenceId).toBe('population:11507:1:youth_18_35_total');
  });

  it('被 markdown code fence 包起來的 JSON 也要能剖析', async () => {
    const adapter = new BedrockRuntimeAdapter({
      modelId: 'm',
      region: 'r',
      client: fakeClient(`這是你要的結果：\n\`\`\`json\n${JSON.stringify(validOutput)}\n\`\`\``),
    });

    await expect(adapter.invokeStructured(prompt)).resolves.toBeTruthy();
  });

  it('第一次違反語意規則時，把錯誤回饋給模型重試一次', async () => {
    // 第一次故意漏掉 disclaimer 關鍵字（形狀合法、語意不合法）。
    const client = fakeClient(
      JSON.stringify({ ...validOutput, disclaimer: '僅供參考' }),
      JSON.stringify(validOutput),
    );
    const adapter = new BedrockRuntimeAdapter({ modelId: 'm', region: 'r', client });

    const result = await adapter.invokeStructured(prompt);

    expect(client.send).toHaveBeenCalledTimes(2);
    expect(result.disclaimer).toContain('不代表政府正式政策決定');

    // 第二次呼叫必須帶上前一輪的回答與具體錯誤，否則模型不知道要修什麼。
    const retry = client.requests[1] as Record<string, any>;
    expect(retry.messages).toHaveLength(3);
    expect(retry.messages[1].role).toBe('assistant');
    expect(retry.messages[2].content[0].text).toContain('不代表政府正式政策決定');
  });

  it('重試用盡後要丟錯，不可把不合格的內容回傳給前端', async () => {
    const client = fakeClient(JSON.stringify({ ...validOutput, disclaimer: '僅供參考' }));
    const adapter = new BedrockRuntimeAdapter({ modelId: 'm', region: 'r', client, maxAttempts: 2 });

    await expect(adapter.invokeStructured(prompt)).rejects.toThrow(/StructuredOutputSchema/);
    expect(client.send).toHaveBeenCalledTimes(2);
  });

  it('回應沒有文字內容時要丟出帶上下文的錯誤', async () => {
    const adapter = new BedrockRuntimeAdapter({
      modelId: 'm',
      region: 'r',
      client: { send: vi.fn(async () => ({ output: {}, stopReason: 'max_tokens' })) },
    });

    await expect(adapter.invokeStructured(prompt)).rejects.toThrow(/max_tokens/);
  });

  /**
   * 這一組是實測踩到的：接上 analytics 的彙總指標後 context 變成 250 筆 evidence，
   * 模型的輸出超過當時的預設 4096 token，JSON 被截斷。
   * 當時的行為是拿截斷的 JSON 去 parse、失敗、再重試一次（同樣的上限，同樣被截斷），
   * 最後丟出 `Expected ',' or ']' after array element in JSON at position 8045`。
   * Opus 兩次各兩分鐘，白等四分鐘才得到一個看不出真正原因的訊息。
   */
  it('被 maxTokens 截斷時立刻失敗，不重試（同樣的上限重試必然同樣被截斷）', async () => {
    const truncated = JSON.stringify(validOutput).slice(0, 120);
    const send = vi.fn(async () => ({
      output: { message: { content: [{ text: truncated }] } },
      stopReason: 'max_tokens',
    }));
    const adapter = new BedrockRuntimeAdapter({
      modelId: 'm',
      region: 'r',
      client: { send },
      maxAttempts: 3,
    });

    await expect(adapter.invokeStructured(prompt)).rejects.toThrow(/輸出上限/);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('截斷的錯誤訊息要說得出怎麼修，而不是丟出 JSON 剖析錯誤', async () => {
    const adapter = new BedrockRuntimeAdapter({
      modelId: 'm',
      region: 'r',
      client: {
        send: vi.fn(async () => ({
          output: { message: { content: [{ text: '{"issues":[' }] } },
          stopReason: 'max_tokens',
        })),
      },
      maxTokens: 4096,
    });

    const error = await adapter.invokeStructured(prompt).catch((caught: unknown) => caught);

    expect(String(error)).toContain('maxTokens=4096');
    expect(String(error)).toContain('BEDROCK_MAX_TOKENS');
    expect(String(error)).toContain('maxEvidence');
    // 不該是原本那個看不懂的訊息
    expect(String(error)).not.toContain("Expected ',' or ']'");
  });

  it('預設輸出上限是 16384（4096 與 8192 實測都不夠寫完 Policy Copilot 的六塊輸出）', async () => {
    const client = fakeClient(JSON.stringify(validOutput));
    await new BedrockRuntimeAdapter({ modelId: 'm', region: 'r', client }).invokeStructured(prompt);

    expect((client.requests[0] as Record<string, any>).inferenceConfig.maxTokens).toBe(
      DEFAULT_MAX_TOKENS,
    );
    expect(DEFAULT_MAX_TOKENS).toBe(16384);
  });
});

describe('parseJsonPayload', () => {
  it('乾淨的 JSON', () => {
    expect(parseJsonPayload('{"a":1}')).toEqual({ a: 1 });
  });

  it('code fence 包裹', () => {
    expect(parseJsonPayload('```json\n{"a":1}\n```')).toEqual({ a: 1 });
  });

  it('前後夾雜多餘文字', () => {
    expect(parseJsonPayload('好的，結果如下：{"a":1} 以上。')).toEqual({ a: 1 });
  });

  it('完全不是 JSON 時要丟錯，並把看到的內容放進訊息方便排查', () => {
    expect(() => parseJsonPayload('抱歉，我無法回答。')).toThrow(/抱歉/);
  });
});

describe('createBedrockClientFromEnv', () => {
  it('沒設 AWS_REGION / BEDROCK_MODEL_ID 時退回 Mock，讓沒有 AWS 的機器也能跑', () => {
    expect(createBedrockClientFromEnv({})).toBeInstanceOf(MockBedrockClient);
    expect(createBedrockClientFromEnv({ AWS_REGION: 'us-east-1' })).toBeInstanceOf(MockBedrockClient);
    expect(createBedrockClientFromEnv({ BEDROCK_MODEL_ID: 'm' })).toBeInstanceOf(MockBedrockClient);
  });

  it('兩個都設好時用真的 Bedrock，description 要看得出用了哪個模型與 region', () => {
    const client = createBedrockClientFromEnv({
      AWS_REGION: 'us-east-1',
      BEDROCK_MODEL_ID: 'us.anthropic.some-model',
    });

    expect(client).toBeInstanceOf(BedrockRuntimeAdapter);
    expect(client.description).toContain('us.anthropic.some-model');
    expect(client.description).toContain('us-east-1');
  });

  it('也接受 AWS_DEFAULT_REGION（AWS CLI 的慣用變數）', () => {
    expect(
      createBedrockClientFromEnv({ AWS_DEFAULT_REGION: 'us-west-2', BEDROCK_MODEL_ID: 'm' }),
    ).toBeInstanceOf(BedrockRuntimeAdapter);
  });

  /**
   * Lambda 會自動把 AWS_REGION 設成 function 所在的 region，所以 BEDROCK_REGION
   * 必須能覆寫它，否則「Lambda 在 A 區、模型只在 B 區」的部署會永遠打錯 region。
   */
  it('BEDROCK_REGION 優先於 Lambda 自動設定的 AWS_REGION', () => {
    const client = createBedrockClientFromEnv({
      AWS_REGION: 'ap-northeast-1',
      BEDROCK_REGION: 'us-west-2',
      BEDROCK_MODEL_ID: 'm',
    });

    expect(client.description).toContain('us-west-2');
    expect(client.description).not.toContain('ap-northeast-1');
  });

  it('沒設 BEDROCK_REGION 時才用 AWS_REGION', () => {
    expect(
      createBedrockClientFromEnv({ AWS_REGION: 'ap-northeast-1', BEDROCK_MODEL_ID: 'm' }).description,
    ).toContain('ap-northeast-1');
  });
});

describe('MockBedrockClient', () => {
  it('內容標明是 mock，避免 demo 當天把假分析當真的用', async () => {
    const result = await new MockBedrockClient().invokeStructured(prompt);

    expect(result.issues.join()).toContain('[mock]');
    expect(result.dataSufficiency).not.toBe('sufficient');
  });

  it('引用 prompt 裡真的存在的 evidenceId，這樣 handler 的驗證才過得去', async () => {
    const result = await new MockBedrockClient().invokeStructured(prompt);

    expect(result.basis[0]?.evidenceId).toBe('population:11507:1:youth_18_35_total');
  });

  it('把 prompt 裡的既知限制帶進 limitations', async () => {
    const result = await new MockBedrockClient().invokeStructured({
      system: '',
      // 用 formatKnownLimitations 組 prompt，不要自己再寫一份標題字串 ——
      // 標題已經是共用常數，測試自己複製一份等於又把那個耦合帶回來。
      user:
        '可用的 evidence：\n1. evidenceId="x"\n\n' +
        `${formatKnownLimitations(['只取樣 3 筆／共 100 筆']) ?? ''}\n`,
    });

    expect(result.limitations.join('\n')).toContain('只取樣 3 筆／共 100 筆');
  });
});
