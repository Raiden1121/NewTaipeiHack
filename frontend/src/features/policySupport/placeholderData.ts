// 佔位資料，待施政協助板塊與 Backend / AI Service API 提供整理後結果。

import { TrendingUp, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type OutcomeTrend = "up" | "down" | "flat";

export interface PolicyOutcome {
  id: string;
  label: string;
  /** 主要百分比數值。 */
  value: number;
  metricLabel: string;
  /** 相對上期的增減百分點。 */
  deltaPct: number;
  trend: OutcomeTrend;
  /** 迷你走勢圖的資料點。 */
  spark: number[];
  icon: LucideIcon;
}

export const POLICY_OUTCOMES: PolicyOutcome[] = [
  {
    id: "wage-growth",
    label: "薪資成長率",
    value: 2.8,
    metricLabel: "青年平均月薪年增",
    deltaPct: 0.6,
    trend: "up",
    spark: [1.6, 1.9, 2.1, 2.0, 2.4, 2.6, 2.8],
    icon: TrendingUp,
  },
  {
    id: "youth-generation-change",
    label: "青年人口世代變化率",
    value: -3.5,
    metricLabel: "20–35 歲人口近五年變化",
    deltaPct: -1.2,
    trend: "down",
    spark: [-0.8, -1.4, -1.9, -2.3, -2.8, -3.1, -3.5],
    icon: Users,
  },
];
