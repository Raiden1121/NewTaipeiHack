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

export interface AssistantSuggestion {
  title: string;
  body: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  suggestions?: AssistantSuggestion[];
  /** 助理回覆引用的即時資料來源說明。 */
  sourceNote?: string;
}

// 展示用的對話種子內容，未來由 AI agent 產生。
export const SEED_CHAT: ChatMessage[] = [
  {
    id: "u-1",
    role: "user",
    content: "針對三重區青年就業率偏低的問題，AI 有什麼政策建議？",
  },
  {
    id: "a-1",
    role: "assistant",
    content:
      "針對三重區青年就業率偏低的現象，根據最新（2023 Q3）的勞動部公開數據與新北市青發處資料，三重區的傳統製造業正處於轉型期，而服務業職缺多為部分工時。建議採取以下策略：",
    suggestions: [
      {
        title: "推動「在地微型創新聚落」計畫",
        body: "利用三重閒置的輕工業廠房空間，提供低租金的青創基地，吸引數位內容與輕型電商進駐，創造符合現代青年的職缺性質。",
      },
      {
        title: "產學媒合：傳統產業數位轉型補助",
        body: "針對三重既有製造業提供專案補助，條件為需聘用在地青年進行「數位行銷」或「自動化系統建置」，同時解決產業轉型與青年就業需求。",
      },
    ],
    sourceNote: "已啟用網路授權，引用即時外部資料（來源：勞動部統計網、新北市經發局）",
  },
];
