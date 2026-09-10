import { motion } from "motion/react";
import { ArrowRight, TrendingDown, TrendingUp } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  POLICY_OUTCOMES,
  type OutcomeTrend,
  type PolicyOutcome,
} from "../placeholderData";

const TREND_ICON = {
  up: TrendingUp,
  down: TrendingDown,
  flat: ArrowRight,
} as const;

function trendColor(trend: OutcomeTrend): string {
  if (trend === "up") return "text-risk-low";
  if (trend === "down") return "text-risk-high";
  return "text-accent-slate";
}

function Sparkline({ points }: { points: number[] }) {
  const width = 96;
  const height = 32;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const d = points
    .map((point, index) => {
      const x = index * step;
      const y = height - ((point - min) / span) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="shrink-0"
      aria-hidden="true"
    >
      <path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function OutcomeCard({ outcome, index }: { outcome: PolicyOutcome; index: number }) {
  const TrendIcon = TREND_ICON[outcome.trend];
  const ProjectIcon = outcome.icon;
  const color = trendColor(outcome.trend);
  const deltaSign = outcome.deltaPct > 0 ? "+" : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.35 }}
    >
      <Card className="h-full">
        <CardContent className="flex flex-col gap-3 p-5">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ProjectIcon className="h-4 w-4" aria-hidden="true" />
            </span>
            <p className="text-sm font-semibold text-slate-600">
              {outcome.project}
            </p>
          </div>

          <div className="flex items-end gap-2">
            <span className="text-4xl font-bold leading-none text-slate-900">
              {outcome.value}%
            </span>
            <span className="pb-1 text-xs font-semibold text-slate-500">
              {outcome.metricLabel}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span
              className={cn("flex items-center gap-1 text-sm font-bold", color)}
            >
              <TrendIcon className="h-4 w-4" aria-hidden="true" />
              {deltaSign}
              {outcome.deltaPct}%
            </span>
            <span className={color}>
              <Sparkline points={outcome.spark} />
            </span>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export default function PolicyOutcomeTracker() {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {POLICY_OUTCOMES.map((outcome, index) => (
          <OutcomeCard key={outcome.id} outcome={outcome} index={index} />
        ))}
      </div>
      <p className="text-[11px] text-slate-400">
        專案執行數值與走勢為佔位資料，待 Backend API 提供整理後結果。
      </p>
    </div>
  );
}
