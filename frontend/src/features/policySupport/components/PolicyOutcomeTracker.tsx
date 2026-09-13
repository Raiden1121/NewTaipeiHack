import { motion } from "motion/react";
import { ArrowRight, TrendingDown, TrendingUp, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { usePolicyOutcomes } from "@/lib/api/queries";
import { formatSignedPercent } from "@/lib/format";

type Direction = "up" | "down";

interface Outcome {
  id: string;
  label: string;
  metricLabel: string;
  icon: LucideIcon;
  value: number | null;
  desired: Direction;
}

function trendIsGood(value: number, desired: Direction): boolean {
  return desired === "up" ? value >= 0 : value <= 0;
}

// 紅漲綠跌（台灣慣例）：顏色只看數值本身正負，跟是否「符合期望方向」無關。
function signColor(value: number): string {
  if (value > 0) return "text-risk-high";
  if (value < 0) return "text-risk-low";
  return "text-accent-slate";
}

function OutcomeCard({ outcome, index }: { outcome: Outcome; index: number }) {
  const MetricIcon = outcome.icon;

  if (outcome.value === null) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.08, duration: 0.35 }}
      >
        <Card className="h-full">
          <CardContent className="flex h-full flex-col items-center justify-center gap-2 p-5 text-center">
            <MetricIcon className="h-6 w-6 text-slate-300" aria-hidden="true" />
            <p className="text-sm font-semibold text-slate-500">{outcome.label}</p>
            <p className="text-xs text-slate-400">資料待補</p>
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  const isGood = trendIsGood(outcome.value, outcome.desired);
  const color = signColor(outcome.value);
  const TrendIcon = outcome.value > 0 ? TrendingUp : outcome.value < 0 ? TrendingDown : ArrowRight;

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
              {formatSignedPercent(outcome.value)}
            </span>
            <span className="pb-1 text-xs font-semibold text-slate-500">
              {outcome.metricLabel}
            </span>
          </div>

          <span className={cn("flex items-center gap-1 text-sm font-bold", color)}>
            <TrendIcon className="h-4 w-4" aria-hidden="true" />
            {isGood ? "符合期望方向" : "偏離期望方向"}
          </span>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export default function PolicyOutcomeTracker() {
  const { data: analysis, isLoading, isError, error, refetch } = usePolicyOutcomes();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Array.from({ length: 2 }).map((_, index) => (
          <Skeleton key={index} className="h-48 w-full rounded-2xl" />
        ))}
      </div>
    );
  }

  if (isError || !analysis) {
    return (
      <section
        role="alert"
        className="flex min-h-[220px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
      >
        <h2 className="text-lg font-bold text-red-700">政策成效追蹤載入失敗</h2>
        <p className="text-sm text-red-600">
          {error instanceof Error ? error.message : "請稍後再試。"}
        </p>
        <Button variant="destructive" onClick={() => refetch()}>
          重新載入
        </Button>
      </section>
    );
  }

  const outcomes: Outcome[] = [
    {
      id: "wage-growth",
      label: "薪資成長率",
      metricLabel: "青年平均月薪年增",
      icon: TrendingUp,
      value: analysis.currentWageGrowth,
      desired: analysis.desiredDirection.wageGrowth,
    },
    {
      id: "youth-generation-change",
      label: "青年人口世代變化率",
      metricLabel: "18–35 歲人口近五年變化",
      icon: Users,
      value: analysis.currentPopGrowth,
      desired: analysis.desiredDirection.populationChange,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {outcomes.map((outcome, index) => (
        <OutcomeCard key={outcome.id} outcome={outcome} index={index} />
      ))}
    </div>
  );
}
