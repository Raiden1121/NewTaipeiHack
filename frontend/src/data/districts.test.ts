import { describe, expect, it, vi, beforeEach } from "vitest";
import { fetchDistrictSummaries } from "./districts";

function mockFetchResolvedWith(csvText: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      text: async () => csvText,
    }),
  );
}

const VALID_HEADER =
  "id,name,youthPopulation,opportunityIndex,retentionRiskLevel,youthParticipationIndex,fertilityRate,policySupportScore";

describe("fetchDistrictSummaries", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("parses a valid CSV row into a typed DistrictSummary", async () => {
    mockFetchResolvedWith(
      `${VALID_HEADER}\n65000010,板橋區,148000,86,low,72,42.1,81\n`,
    );

    const result = await fetchDistrictSummaries();

    expect(result).toEqual([
      {
        id: "65000010",
        name: "板橋區",
        youthPopulation: 148000,
        opportunityIndex: 86,
        retentionRiskLevel: "low",
        youthParticipationIndex: 72,
        fertilityRate: 42.1,
        policySupportScore: 81,
      },
    ]);
  });

  it("throws when the HTTP response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500 }),
    );

    await expect(fetchDistrictSummaries()).rejects.toThrow("HTTP 500");
  });

  it("throws when retentionRiskLevel is not a known value", async () => {
    mockFetchResolvedWith(
      `${VALID_HEADER}\n65000010,板橋區,148000,86,unknown,72,42.1,81\n`,
    );

    await expect(fetchDistrictSummaries()).rejects.toThrow(
      "未知的留才風險等級",
    );
  });

  it("throws when a numeric field cannot be parsed", async () => {
    mockFetchResolvedWith(
      `${VALID_HEADER}\n65000010,板橋區,not-a-number,86,low,72,42.1,81\n`,
    );

    await expect(fetchDistrictSummaries()).rejects.toThrow(
      "不是有效數字",
    );
  });
});
