import Papa from "papaparse";
import type { DistrictSummary, RetentionRiskLevel } from "@/types/district";
import districtsCsvUrl from "@/fixtures/districts.csv?url";

const VALID_RISK_LEVELS: RetentionRiskLevel[] = ["low", "medium", "high"];

interface DistrictCsvRow {
  id: string;
  name: string;
  youthPopulation: string;
  opportunityIndex: string;
  retentionRiskLevel: string;
  youthParticipationIndex: string;
  fertilityRate: string;
  policySupportScore: string;
}

function toRiskLevel(value: string): RetentionRiskLevel {
  const normalized = value.trim().toLowerCase();
  if ((VALID_RISK_LEVELS as string[]).includes(normalized)) {
    return normalized as RetentionRiskLevel;
  }
  throw new Error(`未知的留才風險等級："${value}"`);
}

function toNumber(value: string, field: string): number {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    throw new Error(`欄位 "${field}" 不是有效數字："${value}"`);
  }
  return parsed;
}

function parseRow(row: DistrictCsvRow): DistrictSummary {
  if (!row.id || !row.name) {
    throw new Error("行政區資料缺少 id 或 name 欄位。");
  }

  return {
    id: row.id,
    name: row.name,
    youthPopulation: toNumber(row.youthPopulation, "youthPopulation"),
    opportunityIndex: toNumber(row.opportunityIndex, "opportunityIndex"),
    retentionRiskLevel: toRiskLevel(row.retentionRiskLevel),
    youthParticipationIndex: toNumber(
      row.youthParticipationIndex,
      "youthParticipationIndex",
    ),
    fertilityRate: toNumber(row.fertilityRate, "fertilityRate"),
    policySupportScore: toNumber(row.policySupportScore, "policySupportScore"),
  };
}

export async function fetchDistrictSummaries(): Promise<DistrictSummary[]> {
  const response = await fetch(districtsCsvUrl);
  if (!response.ok) {
    throw new Error(`行政區資料請求失敗（HTTP ${response.status}）`);
  }

  const csvText = await response.text();
  const { data, errors } = Papa.parse<DistrictCsvRow>(csvText, {
    header: true,
    skipEmptyLines: true,
  });

  if (errors.length > 0) {
    throw new Error(`行政區資料解析失敗：${errors[0].message}`);
  }

  return data.map(parseRow);
}
