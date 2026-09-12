// Backend read API 型別，對應 api_contract.md 的欄位形狀。
// 命名採 pipeline 實際輸出（district_id、yoiComponents.* 等），見 api_contract.md §2。

export interface ApiMeta {
  api_version: string;
  snapshot_id: string;
  generated_at: string;
  as_of: string | null;
  warnings: string[];
}

export interface ApiEnvelope<T> {
  data: T;
  meta: ApiMeta;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: unknown[] };
  request_id: string;
}

export type RetentionRiskLevel = "low" | "medium" | "high";
export type AvailabilityStatus = "available" | "partial" | "unavailable";
export type QualityStatus = "observed" | "partial" | "unavailable";

export interface YoiComponents {
  job: number;
  salary: number;
  talent: number;
  housing: number;
  transport: number;
}

// districts[] 內一筆（dashboard/overview），等同 districts/{id} 的 metrics + district_id/district_name。
export interface DistrictSummary {
  district_id: string;
  district_name: string;
  youth_18_35_total: number;
  vacancies_per_10k_youth: number;
  occupation_shannon_index: number;
  talent_demand_yoy: number;
  salary_median: number;
  high_salary_ratio: number;
  adjusted_youth_wage: number;
  college_student_density: number;
  vt_course_count: number;
  training_people_per_10k_youth: number;
  rent_median: number;
  house_price_median: number;
  rent_wage_ratio: number;
  bus_stops_per_10k_youth: number;
  railway_stop_density: number;
  bike_stop_density: number;
  opportunityIndex: number;
  yoiComponents: YoiComponents;
  retentionRiskLevel: RetentionRiskLevel;
  fertilityRate: number;
  fertilityVsCityAvg: number;
  serviceCoverageRate: number | null;
  serviceCoverageStatus: AvailabilityStatus;
  youthCandidacyRatePer100k: number | null;
  /** 青年里長占比（%），僅民國 111 年屆有效；來自 elections.borough_chief_v1，見 api_contract.md §6.2。 */
  youthBoroughChiefRatioPercent: number | null;
  qualityStatus: QualityStatus;
  sourcePeriods: Record<string, unknown>;
}

export interface DistrictDetail {
  district_id: string;
  district_name: string;
  metrics: Omit<DistrictSummary, "district_id" | "district_name">;
}

export interface DashboardKpis {
  nationalYouthPopulation: number;
  nationalYouthPopulationQuality: "proxy" | "observed";
  cityYouthPopulationShare: number;
  cityYouthPopulation: number;
  cityYouthPopulationYoY: number;
  referenceYearRoc: number;
}

export interface PopulationYear {
  year_roc: number;
  city: { youth_population: number; youth_share_percent: number };
  districts: {
    district_id: string;
    district_name: string;
    youth_population: number;
    youth_share_percent: number;
  }[];
}

export interface FertilityYear {
  year_roc: number;
  city: {
    births_mother_age_18_35: number;
    fertility_rate: number;
    quality_status: QualityStatus;
  };
  districts: {
    district_id: string;
    district_name: string;
    births_mother_age_18_35: number;
    fertility_rate: number;
    quality_status: QualityStatus;
  }[];
}

export interface CityCouncilorCitywideYear {
  year_roc: number;
  youth_candidacy_rate: number | null;
  quality_status: QualityStatus;
}

export interface BoroughChiefRow {
  district_id: string;
  district_name: string;
  year_roc: number;
  elected_count: number;
  youth_elected_count: number;
}

/** 全市加總（民國 111 年屆），供未選取行政區時的「全市」KPI 卡使用，見 api_contract.md §6.2。 */
export interface BoroughChiefCitywide {
  year_roc: number;
  elected_count: number;
  youth_elected_count: number;
  ratio_percent: number;
}

export interface ServiceCoverage {
  value: number;
  status: AvailabilityStatus;
  radius_m: number;
  verified_point_count: number;
  excluded_point_count: number;
  population_coverage_ratio: number;
  boundary_village_count: number;
  joined_village_count: number;
  blocking_reasons: string[];
}

export interface BudgetTrendPoint {
  year_roc: number;
  value_thousand: number | null;
}

export interface PolicyBlock {
  currentBudget: number;
  budgetUnit: "TWD_thousand";
  budgetYoY: number;
  executionRate: number | null;
  executionFailure: string | null;
  budgetTrend: BudgetTrendPoint[];
}

export interface DashboardAvailability {
  opportunityIndex: AvailabilityStatus;
  fertility: AvailabilityStatus;
  youthParticipationIndex: AvailabilityStatus;
  serviceCoverage: AvailabilityStatus;
  budget: AvailabilityStatus;
}

export interface DashboardOverview {
  kpis: DashboardKpis;
  districts: DistrictSummary[];
  annual: {
    population: { years: PopulationYear[] };
    fertility: { years: FertilityYear[] };
  };
  elections: {
    city_councilor_t1_citywide: CityCouncilorCitywideYear[];
    /** 3 屆 × 29 區明細（103/107/111），供未來歷年趨勢用；KPI 卡請用 districts[].youthBoroughChiefRatioPercent 或 borough_chief_v1_citywide，不要在前端自行篩選收斂。 */
    borough_chief_v1: BoroughChiefRow[];
    borough_chief_v1_citywide: BoroughChiefCitywide;
  };
  service_coverage: ServiceCoverage;
  policy: PolicyBlock;
  availability: DashboardAvailability;
}

export interface Regression {
  slope: number;
  intercept: number;
  r_squared: number;
}

export interface ScatterPoint {
  district_id: string;
  district_name: string;
  x: number;
  y: number;
}

export interface EmploymentScatterAnalysis {
  analysis_id: "employment-scatter";
  geo_level: "district";
  plots: {
    id: string;
    title: string;
    x_label: string;
    y_label: string;
    points: ScatterPoint[];
    regression: Regression;
    note: string;
  }[];
  limitations: string[];
}

export interface PoliticsResourceIoAnalysis {
  analysis_id: "politics-resource-io";
  // 各科別預算比例是青年局組織層級資料，非可拆分到 29 區的地理量測，見 api_contract.md §6.3。
  geo_level: "county";
  budget_by_department: { label: string; amount_thousand: number; share_percent: number }[];
  budgetTrend: BudgetTrendPoint[];
  executionRate: number | null;
}

export interface YouthTopicWeightTopic {
  label: string;
  weight: number;
  signal: string;
  join_mentions: number;
  minutes_mentions: number;
  resolved: boolean;
  escalated: boolean;
  join_support_score: number;
  raw_score: number;
}

// 攤平形狀，見 api_contract.md §6.4：backend 已固定回傳最新一年（114）的 topics[]。
export interface YouthTopicWeightAnalysis {
  analysis_id: "youth-topic-weight";
  year_roc: number;
  topics: YouthTopicWeightTopic[];
}

export interface FertilityOverlayAnalysis {
  analysis_id: "fertility-overlay";
  geo_level: "district";
  points: ScatterPoint[];
  regression: Regression;
}

export interface FamilyFriendlinessDistrict {
  district_id: string;
  district_name: string;
  fafi_score: number;
  fafi_level: "low" | "medium" | "high";
}

export interface FamilyFriendlinessAnalysis {
  analysis_id: "fertility-family-friendliness";
  geo_level: "district";
  districts: FamilyFriendlinessDistrict[];
}

export interface WageTrendPoint {
  year_roc: number;
  wage: number | null;
  yoy: number | null;
  quality_status: QualityStatus;
}

export interface PopulationTrendPoint {
  year_roc: number;
  population: number;
  yoy: number | null;
}

export interface PolicyOutcomesAnalysis {
  analysis_id: "policy-outcomes";
  geo_level: "county";
  wageTrend: WageTrendPoint[];
  populationTrend: PopulationTrendPoint[];
  currentWageGrowth: number | null;
  currentPopGrowth: number | null;
  /** 每指標「往哪個方向是好事」，見 api_contract.md §8.1。前端據此決定顏色，不要寫死。 */
  desiredDirection: { wageGrowth: "up" | "down"; populationChange: "up" | "down" };
}

export interface CatalogData {
  snapshot_id: string;
  generated_at: string;
  calculation_version: string;
  districts_count: number;
  time_policy: { annual_years_roc: number[]; election_years_roc: number[] };
  quality: { status: string };
}
