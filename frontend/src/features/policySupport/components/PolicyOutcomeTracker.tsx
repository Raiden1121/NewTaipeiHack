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

function LineChart({
  points,
  className,
}: {
  points: number[];
  className?: string;
}) {
  const width = 300;
  const height = 80;
  const pad = 6;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = (width - pad * 2) / (points.length - 1);
  const coords = points.map((point, index) => ({
    x: pad + index * step,
    y: pad + (height - pad * 2) * (1 - (point - min) / span),
  }));
  const line = coords
    .map((c, index) => `${index === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`)
    .join(" ");
  const first = coords[0];
  const last = coords[coords.length - 1];
  const area = `${line} L ${last.x.toFixed(1)} ${height - pad} L ${first.x.toFixed(1)} ${height - pad} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={cn("h-20 w-full sm:h-24", className)}
      aria-hidden="true"
    >
      <line
        x1={pad}
        y1={height - pad}
        x2={width - pad}
        y2={height - pad}
        stroke="currentColor"
        strokeWidth={1}
        strokeOpacity={0.2}
        vectorEffect="non-scaling-stroke"
      />
      <path d={area} fill="currentColor" fillOpacity={0.12} />
      <path
        d={line}
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function OutcomeCard({ outcome, index }: { outcome: PolicyOutcome; index: number }) {
  const TrendIcon = TREND_ICON[outcome.trend];
  const MetricIcon = outcome.icon;
  const color = trendColor(outcome.trend);
  const deltaSign = outcome.deltaPct > 0 ? "+" : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.35 }}
    >
      <Card className="h-full">
        <CardContent className="flex h-full flex-col gap-3 p-5">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <MetricIcon className="h-4 w-4" aria-hidden="true" />
            </span>
            <p className="text-sm font-semibold text-slate-600">
              {outcome.label}
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

          <span
            className={cn("flex items-center gap-1 text-sm font-bold", color)}
          >
            <TrendIcon className="h-4 w-4" aria-hidden="true" />
            {deltaSign}
            {outcome.deltaPct}%
          </span>

          <LineChart points={outcome.spark} className={cn("mt-auto", color)} />
        </CardContent>
      </Card>
    </motion.div>
  );
}

export default function PolicyOutcomeTracker() {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {POLICY_OUTCOMES.map((outcome, index) => (
          <OutcomeCard key={outcome.id} outcome={outcome} index={index} />
        ))}
      </div>
      <p className="text-[11px] text-slate-400">
        指標數值與走勢為佔位資料，待 Backend API 提供整理後結果。
      </p>
    </div>
  );
}
