export type RetentionRiskLevel = "low" | "medium" | "high";

export interface DistrictSummary {
  id: string;
  name: string;
  youthPopulation: number;
  opportunityIndex: number;
  retentionRiskLevel: RetentionRiskLevel;
  youthParticipationIndex: number;
  fertilityRate: number;
  policySupportScore: number;
}
