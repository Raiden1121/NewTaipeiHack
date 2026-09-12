import { describe, expect, it } from "vitest";
import type { MetricValue } from "./metrics";

describe("MetricValue source contract", () => {
  it("keeps direct source display fields", () => {
    const metric: MetricValue = {
      metric_id: "population",
      value: 100,
      unit: "people",
      period_start: null,
      period_end: null,
      period_type: "month",
      geo_level: "district",
      youth_eligibility: "eligible",
      source: "moi_household_registration",
      sourceName: "內政部戶政司",
      sourceUrl: "https://example.gov.tw/population",
      sourceRefs: [],
      quality_flags: [],
      status: "available",
      is_proxy: false,
    };

    expect(metric.sourceName).toBe("內政部戶政司");
    expect(metric.sourceUrl).toContain("https://");
  });

  it("represents derived metrics with source references and nullable direct source", () => {
    const metric: MetricValue = {
      metric_id: "opportunity_index",
      value: 50,
      unit: "score",
      period_start: null,
      period_end: null,
      period_type: "snapshot",
      geo_level: "district",
      youth_eligibility: "context_only",
      source: null,
      sourceName: null,
      sourceUrl: null,
      sourceRefs: ["moi_household_registration", "taiwanjobs"],
      quality_flags: [],
      status: "available",
      is_proxy: false,
    };

    expect(metric.source).toBeNull();
    expect(metric.sourceUrl).toBeNull();
    expect(metric.sourceRefs).toEqual([
      "moi_household_registration",
      "taiwanjobs",
    ]);
  });
});
