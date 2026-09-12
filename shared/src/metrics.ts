export type MetricStatus = "available" | "partial" | "unavailable";
export type YouthEligibility = "eligible" | "proxy_only" | "context_only";
export type PeriodType = "day" | "month" | "year" | "snapshot";

export interface MetricValue<T = number> {
  metric_id: string;
  value: T | null;
  unit: string | null;
  period_start: string | null;
  period_end: string | null;
  period_type: PeriodType;
  geo_level: "district" | "county" | "national" | "organization";
  youth_eligibility: YouthEligibility;
  source: string | null;
  sourceName: string | null;
  sourceUrl: string | null;
  sourceRefs: string[];
  quality_flags: string[];
  status: MetricStatus;
  is_proxy: boolean;
}
