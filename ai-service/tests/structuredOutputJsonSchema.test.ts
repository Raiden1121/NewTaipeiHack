import { describe, expect, it } from 'vitest';
import {
  QA_OUTPUT_JSON_SCHEMA,
  STRUCTURED_OUTPUT_JSON_SCHEMA,
  UNSUPPORTED_JSON_SCHEMA_KEYWORDS,
  qaOutputSchemaJson,
  structuredOutputSchemaJson,
} from '../src/types/structuredOutputJsonSchema.js';
import { QaOutputSchema, StructuredOutputSchema } from '../src/types/structuredOutput.js';

/**
 * 這組測試的存在理由：Bedrock structured outputs 只吃 JSON Schema Draft 2020-12 的
 * **子集**，用到不支援的功能會直接回 400（不是靜默忽略）。
 *
 * 如果沒有這些測試，schema 長出一個 `minLength` 之後要等到 demo 現場真的呼叫
 * Bedrock 才會發現 —— 那時候通常沒有時間排查。
 */
describe('Bedrock structured outputs 的 JSON Schema 限制', () => {
  const serialized = structuredOutputSchemaJson();

  it('不含任何不支援的 JSON Schema 關鍵字', () => {
    for (const keyword of UNSUPPORTED_JSON_SCHEMA_KEYWORDS) {
      expect(serialized, `schema 不可使用 ${keyword}`).not.toContain(`"${keyword}"`);
    }
  });

  it('每個 object 都必須明確設定 additionalProperties: false', () => {
    const visit = (node: unknown, pathLabel: string): void => {
      if (node === null || typeof node !== 'object') {
        return;
      }
      const record = node as Record<string, unknown>;
      if (record.type === 'object') {
        expect(record.additionalProperties, `${pathLabel} 缺少 additionalProperties: false`).toBe(false);
      }
      for (const [key, value] of Object.entries(record)) {
        visit(value, `${pathLabel}.${key}`);
      }
    };
    visit(STRUCTURED_OUTPUT_JSON_SCHEMA, 'root');
  });

  it('陣列的 minItems 只允許 0 或 1', () => {
    const found: number[] = [];
    const visit = (node: unknown): void => {
      if (node === null || typeof node !== 'object') {
        return;
      }
      const record = node as Record<string, unknown>;
      if (typeof record.minItems === 'number') {
        found.push(record.minItems);
      }
      Object.values(record).forEach(visit);
    };
    visit(STRUCTURED_OUTPUT_JSON_SCHEMA);

    for (const value of found) {
      expect([0, 1]).toContain(value);
    }
  });

  it('nullable 欄位用 anyOf 表達（anyOf 是明確支援的）', () => {
    const note = STRUCTURED_OUTPUT_JSON_SCHEMA.properties.basis.items.properties.note;
    expect(note.anyOf).toEqual([{ type: 'string' }, { type: 'null' }]);
  });

  it('Bedrock 要求 schema 是 JSON 字串而不是物件', () => {
    expect(typeof serialized).toBe('string');
    expect(() => JSON.parse(serialized)).not.toThrow();
  });
});

/**
 * 兩套 schema（送給 Bedrock 的 JSON Schema、自己驗的 zod schema）如果欄位對不上，
 * 就會出現「Bedrock 說形狀合法，zod 卻拒絕」的無窮重試。所以要鎖住兩邊一致。
 */
describe('JSON Schema 與 zod schema 必須同步', () => {
  /**
   * `answer` 刻意只存在 Q&A 的 schema 裡。
   *
   * 六塊格式（explain / policyCopilot）沒有使用者問題，所以不該有 answer；
   * 而 `additionalProperties: false` 會讓模型連想輸出都不行。
   * zod 那邊 `answer` 是 `.default(null)`，所以模型不給也能通過驗證。
   */
  const QA_ONLY_KEYS = ['answer'];

  it('六塊 schema 的 required 等於 zod 的 key（扣掉只有 Q&A 才有的欄位）', () => {
    const jsonRequired = [...STRUCTURED_OUTPUT_JSON_SCHEMA.required].sort();
    // superRefine 包在外層，用 innerType() 取回底下的 object schema。
    const zodKeys = Object.keys(StructuredOutputSchema.innerType().shape)
      .filter((key) => !QA_ONLY_KEYS.includes(key))
      .sort();

    expect(jsonRequired).toEqual(zodKeys);
  });

  it('Q&A schema 的 required 等於 zod 的全部 key（含 answer）', () => {
    const jsonRequired = [...QA_OUTPUT_JSON_SCHEMA.required].sort();
    const zodKeys = Object.keys(QaOutputSchema.innerType().shape).sort();

    expect(jsonRequired).toEqual(zodKeys);
  });

  it('六塊 schema 不可以出現 answer（那是 Q&A 專屬）', () => {
    expect(Object.keys(STRUCTURED_OUTPUT_JSON_SCHEMA.properties)).not.toContain('answer');
    expect(STRUCTURED_OUTPUT_JSON_SCHEMA.required).not.toContain('answer');
  });

  it('Q&A schema 沒有用到 Bedrock 不支援的關鍵字', () => {
    const serializedQa = qaOutputSchemaJson();
    for (const keyword of UNSUPPORTED_JSON_SCHEMA_KEYWORDS) {
      expect(serializedQa).not.toContain(`"${keyword}"`);
    }
  });

  it('Q&A schema 的 evidenceReview 也只要 missingForQuestion', () => {
    expect(QA_OUTPUT_JSON_SCHEMA.properties.evidenceReview.required).toEqual(['missingForQuestion']);
  });

  it('Q&A schema 的形狀可以通過 QaOutputSchema 驗證', () => {
    const sample = {
      evidenceReview: { missingForQuestion: [] },
      dataSufficiency: 'sufficient',
      answer: '板橋區 18–35 歲青年人口為 107,970 人。',
      basis: [{ evidenceId: 'population:11507:0:youth_18_35_total', note: null }],
      issues: [],
      strengths: [],
      resourceGaps: [],
      policyDirections: [],
      webReferences: [],
      limitations: [],
      disclaimer: 'AI 建議屬於政策輔助資訊，不代表政府正式政策決定。',
    };

    expect(() => QaOutputSchema.parse(sample)).not.toThrow();
  });

  it('JSON Schema 描述的形狀可以通過 zod 驗證', () => {
    const sample = {
      evidenceReview: {
        availableMetrics: ['youth_18_35_total（板橋區／11507）'],
        youthSpecificMetrics: ['youth_18_35_total'],
        contextOnlyMetrics: [],
        missingForQuestion: ['缺少職缺彙總指標'],
      },
      dataSufficiency: 'partial',
      issues: ['問題'],
      strengths: [],
      resourceGaps: [],
      policyDirections: [],
      basis: [{ evidenceId: 'population:11507:0:people_total', note: null }],
      limitations: ['缺少職缺彙總指標'],
      disclaimer: 'AI 建議屬於政策輔助資訊，不代表政府正式政策決定。',
    };

    expect(() => StructuredOutputSchema.parse(sample)).not.toThrow();
  });

  /**
   * 欄位順序不只是美觀問題：JSON 是依欄位順序生成的，所以 evidenceReview 排第一
   * 等於強制模型先盤點再下結論。有人重排欄位時要被這個測試擋下來。
   */
  it('evidenceReview 必須是第一個欄位，dataSufficiency 第二個', () => {
    const keys = Object.keys(STRUCTURED_OUTPUT_JSON_SCHEMA.properties);

    expect(keys[0]).toBe('evidenceReview');
    expect(keys[1]).toBe('dataSufficiency');
    // 四塊結論必須排在盤點與充足度之後。
    expect(keys.indexOf('issues')).toBeGreaterThan(keys.indexOf('dataSufficiency'));
    expect(keys.indexOf('basis')).toBeGreaterThan(keys.indexOf('issues'));
  });
});
