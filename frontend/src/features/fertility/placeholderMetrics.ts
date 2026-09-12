// 佔位指標產生器：以行政區 id 為種子產生 deterministic 數值，
// 讓切換行政區時核心生育指標會明顯變動。真實資料待 Backend API 提供。

function hashSeed(seed: string): number {
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 0xffffffff;
}

/** 依 seed 在 [min, max] 之間取一個 deterministic 值，四捨五入到 decimals 位。 */
function seededValue(
  seed: string,
  min: number,
  max: number,
  decimals = 1,
): number {
  const ratio = hashSeed(seed);
  const raw = min + ratio * (max - min);
  const factor = 10 ** decimals;
  return Math.round(raw * factor) / factor;
}

export interface FertilityKpi {
  id: string;
  label: string;
  caption: string;
  format: (value: number) => string;
  range: [number, number];
  decimals: number;
  /** 是否附帶一個相對去年的增減百分比。 */
  trend?: boolean;
}

export const FERTILITY_KPIS: FertilityKpi[] = [
  {
    id: "total-births",
    label: "青年總生育數",
    caption: "18–35 歲婦女年度生育數",
    format: (v) => Math.round(v).toLocaleString("en-US"),
    range: [6000, 15000],
    decimals: 0,
    trend: true,
  },
  {
    id: "avg-fertility-rate",
    label: "育齡青年生育率",
    caption: "每千名 18–35 歲育齡人口之年度生育數",
    format: (v) => `${v}‰`,
    range: [25, 55],
    decimals: 1,
    trend: true,
  },
  {
    id: "youth-population-share",
    label: "青年人口占比",
    caption: "18–35 歲占該區總人口比例",
    format: (v) => `${v}%`,
    range: [22, 32],
    decimals: 1,
    trend: true,
  },
  {
    id: "childcare-coverage",
    label: "托育資源覆蓋率",
    caption: "公共托育需求滿足率",
    format: (v) => `${Math.round(v)}%`,
    range: [55, 85],
    decimals: 0,
    trend: true,
  },
];

export interface FertilityMetric extends FertilityKpi {
  value: number;
  /** 相對去年的增減百分比，僅 trend 指標會有。 */
  deltaPct?: number;
}

/** 產生某行政區（或全市）的核心生育指標佔位值。 */
export function buildFertilityMetrics(seedKey: string): FertilityMetric[] {
  return FERTILITY_KPIS.map((kpi) => ({
    ...kpi,
    value: seededValue(
      `${seedKey}:${kpi.id}`,
      kpi.range[0],
      kpi.range[1],
      kpi.decimals,
    ),
    deltaPct: kpi.trend
      ? seededValue(`${seedKey}:${kpi.id}:delta`, -4, 8, 1)
      : undefined,
  }));
}
