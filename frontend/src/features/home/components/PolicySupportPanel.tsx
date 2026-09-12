import { TrendingDown, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardOverview } from "@/lib/api/queries";
import { formatSignedPercent, formatThousandAsYi } from "@/lib/format";
import type { BudgetTrendPoint } from "@/lib/api/types";

const CHART_VB_W = 300;
const CHART_VB_H = 120;
const CHART_PAD_X = 22;

function BudgetTrendChart({ trend }: { trend: BudgetTrendPoint[] }) {
  const vbW = CHART_VB_W;
  const vbH = CHART_VB_H;
  const labelH = 22;
  const top = 10;
  const bottom = vbH - labelH;
  const plotH = bottom - top;
  const plotW = vbW - CHART_PAD_X * 2;
  const stepX = plotW / (trend.length - 1 || 1);

  const available = trend.filter(
    (item): item is { year_roc: number; value_thousand: number } => item.value_thousand !== null,
  );
  const amounts = available.map((item) => item.value_thousand);
  const max = Math.max(...amounts);
  const min = Math.min(...amounts);

  const points = trend
    .map((item, index) => ({ ...item, index }))
    .filter((item): item is typeof item & { value_thousand: number } => item.value_thousand !== null)
    .map((item) => {
      const x = CHART_PAD_X + item.index * stepX;
      const y = bottom - ((item.value_thousand - min) / (max - min || 1)) * plotH;
      return { x, y, year: item.year_roc };
    });

  const polylinePoints = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`);
  const firstX = points[0]?.x.toFixed(1) ?? "0";
  const lastX = points[points.length - 1]?.x.toFixed(1) ?? "0";

  const axisX = CHART_PAD_X;
  const axisTopY = top - 6;
  const axisRightX = vbW - CHART_PAD_X / 2;
  const yLabelX = axisX - 12;
  const yLabelY = (top + bottom) / 2;

  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      preserveAspectRatio="none"
      className="block h-full w-full"
      role="img"
      aria-label="年度總預算趨勢折線圖，近五年"
    >
      <defs>
        <marker
          id="budget-trend-arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 Z" className="fill-slate-300" />
        </marker>
      </defs>
      <line
        x1={axisX}
        y1={bottom}
        x2={axisRightX}
        y2={bottom}
        className="stroke-slate-300"
        strokeWidth={1}
        markerEnd="url(#budget-trend-arrow)"
      />
      <line
        x1={axisX}
        y1={bottom}
        x2={axisX}
        y2={axisTopY}
        className="stroke-slate-300"
        strokeWidth={1}
        markerEnd="url(#budget-trend-arrow)"
      />
      <text
        x={yLabelX}
        y={yLabelY}
        textAnchor="middle"
        transform={`rotate(-90 ${yLabelX} ${yLabelY})`}
        className="fill-slate-400"
        fontSize={11}
      >
        億元
      </text>
      {points.length > 1 && (
        <>
          <polyline
            points={`${firstX},${bottom} ${polylinePoints.join(" ")} ${lastX},${bottom}`}
            className="fill-primary/10 stroke-none"
          />
          <polyline
            points={polylinePoints.join(" ")}
            className="fill-none stroke-primary"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </>
      )}
      {points.map((point) => (
        <circle key={point.year} cx={point.x} cy={point.y} r={2.5} className="fill-primary" />
      ))}
      {trend.map((item, index) => (
        <text
          key={`${item.year_roc}-label`}
          x={CHART_PAD_X + index * stepX}
          y={bottom + 16}
          textAnchor="middle"
          className="fill-slate-400"
          fontSize={11}
        >
          {item.year_roc}
        </text>
      ))}
    </svg>
  );
}

export default function PolicySupportPanel() {
  const { data: overview, isLoading } = useDashboardOverview();

  if (isLoading || !overview) {
    return (
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Skeleton className="h-48 w-full rounded-2xl" />
        <Skeleton className="h-48 w-full rounded-2xl" />
      </section>
    );
  }

  const { policy } = overview;
  const TrendIcon = policy.budgetYoY >= 0 ? TrendingUp : TrendingDown;
  const missingYears = policy.budgetTrend
    .filter((item) => item.value_thousand === null)
    .map((item) => item.year_roc);

  return (
    <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card className="h-full">
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Annual Budget
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            青年總預算
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-end gap-2">
            <span className="text-3xl font-bold text-slate-900">
              {formatThousandAsYi(policy.currentBudget)}
            </span>
            <span
              className={`mb-1 inline-flex items-center gap-1 text-xs font-semibold ${policy.budgetYoY >= 0 ? "text-risk-high" : "text-risk-low"}`}
            >
              <TrendIcon className="h-3.5 w-3.5" aria-hidden="true" />
              較前年 {formatSignedPercent(policy.budgetYoY)}
            </span>
          </div>
          <p className="text-sm text-slate-500">
            民國 {overview.kpis.referenceYearRoc} 年度青年政策總預算
          </p>
          <div>
            <div className="mb-1 flex items-center justify-between text-xs font-semibold">
              <span className="text-slate-600">預算執行率</span>
              <span className="text-primary">
                {policy.executionRate === null ? "資料待補" : `${policy.executionRate}%`}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${policy.executionRate ?? 0}%` }}
              />
            </div>
            {policy.executionFailure && (
              <p className="mt-1 text-[11px] text-slate-400">
                {policy.executionFailure === "final_settlement_unavailable"
                  ? "決算尚未公告，暫無法計算執行率"
                  : policy.executionFailure}
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card className="flex h-full flex-col">
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Yearly Trend
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            青年預算變化
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col gap-2">
          <div className="min-h-[160px] flex-1 rounded-xl border border-slate-200 bg-slate-50 p-4">
            <BudgetTrendChart trend={policy.budgetTrend} />
          </div>
          <p className="text-[11px] text-slate-400">
            近 5 年年度總預算趨勢（億元）。
            {missingYears.length > 0 &&
              `民國 ${missingYears.join("、")} 年資料尚未發布，圖上未連線。`}
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
