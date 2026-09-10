// 佔位指標產生器：以行政區 id 為種子產生 deterministic 數值，
// 讓切換行政區時六大參政指標會明顯變動。真實資料待 Backend API 提供。

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

export interface ParticipationKpi {
  id: string;
  label: string;
  caption: string;
  format: (value: number) => string;
  range: [number, number];
  decimals: number;
  /** 落差型指標為負向，數值越低越差。 */
  negative?: boolean;
}

export const PARTICIPATION_KPIS: ParticipationKpi[] = [
  {
    id: "candidate-density",
    label: "青年參選密度",
    caption: "18–35 歲候選人比例",
    format: (v) => `${v}%`,
    range: [8, 16],
    decimals: 1,
  },
  {
    id: "youth-borough-chief",
    label: "里長青年占比",
    caption: "青年當選里長之比例",
    format: (v) => `${v}%`,
    range: [4, 12],
    decimals: 1,
  },
  {
    id: "lean-ratio",
    label: "參選傾向比",
    caption: "與全體選民傾向之對照",
    format: (v) => v.toFixed(2),
    range: [0.6, 1.1],
    decimals: 2,
  },
  {
    id: "yrr",
    label: "YRR (Youth Rep. Ratio)",
    caption: "席次與青年人口占比之比值",
    format: (v) => v.toFixed(2),
    range: [0.45, 0.85],
    decimals: 2,
  },
  {
    id: "elected-gap",
    label: "青年當選率落差",
    caption: "與全體當選率之差值",
    format: (v) => `${v > 0 ? "+" : ""}${v}%`,
    range: [-6, 1],
    decimals: 1,
    negative: true,
  },
  {
    id: "generation-gap",
    label: "世代斷層指數",
    caption: "里層間世代參政落差",
    format: (v) => `${v}`,
    range: [60, 88],
    decimals: 1,
  },
];

/** 產生某行政區（或全市）的六大參政指標佔位值。 */
export function buildParticipationMetrics(seedKey: string) {
  return PARTICIPATION_KPIS.map((kpi) => ({
    ...kpi,
    value: seededValue(
      `${seedKey}:${kpi.id}`,
      kpi.range[0],
      kpi.range[1],
      kpi.decimals,
    ),
  }));
}
