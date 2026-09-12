import { TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// 佔位資料，待施政協助板塊與 Backend API 提供。
const TOTAL_BUDGET = "NT$ 3.24 億";
const BUDGET_YOY = "+8.5%";
const BUDGET_EXECUTION_RATE = 72;

interface YearlyBudget {
  year: number;
  amount: number;
}

// 佔位：近 5 年年度總預算（億元），終點對齊上方「青年總預算」卡的 3.24 億。
const YEARLY_BUDGET: YearlyBudget[] = [
  { year: 2022, amount: 2.62 },
  { year: 2023, amount: 2.79 },
  { year: 2024, amount: 2.87 },
  { year: 2025, amount: 2.99 },
  { year: 2026, amount: 3.24 },
];

// 折線圖手刻 SVG：面積填色＋折線＋端點，做法沿用 PolicyOutcomeTracker 既有的
// preserveAspectRatio="none"，讓圖表隨卡片實際高度撐滿，避免固定比例撐不滿卡片留白。
const CHART_VB_W = 300;
const CHART_VB_H = 120;
const CHART_PAD_X = 22;

function BudgetTrendChart() {
  const vbW = CHART_VB_W;
  const vbH = CHART_VB_H;
  const labelH = 22;
  const top = 10;
  const bottom = vbH - labelH;
  const plotH = bottom - top;
  const amounts = YEARLY_BUDGET.map((item) => item.amount);
  const max = Math.max(...amounts);
  const min = Math.min(...amounts);
  const plotW = vbW - CHART_PAD_X * 2;
  const stepX = plotW / (YEARLY_BUDGET.length - 1);

  const points = YEARLY_BUDGET.map((item, index) => {
    const x = CHART_PAD_X + index * stepX;
    const y = bottom - ((item.amount - min) / (max - min || 1)) * plotH;
    return { x, y, year: item.year };
  });
  const polylinePoints = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`);
  const firstX = points[0].x.toFixed(1);
  const lastX = points[points.length - 1].x.toFixed(1);

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
      aria-label="年度總預算趨勢折線圖佔位，近五年"
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
      {points.map((point) => (
        <circle key={point.year} cx={point.x} cy={point.y} r={2.5} className="fill-primary" />
      ))}
      {points.map((point) => (
        <text
          key={`${point.year}-label`}
          x={point.x}
          y={bottom + 16}
          textAnchor="middle"
          className="fill-slate-400"
          fontSize={11}
        >
          {point.year}
        </text>
      ))}
    </svg>
  );
}

export default function PolicySupportPanel() {
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
              {TOTAL_BUDGET}
            </span>
            <span className="mb-1 inline-flex items-center gap-1 text-xs font-semibold text-risk-high">
              <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
              較前年 {BUDGET_YOY}
            </span>
          </div>
          <p className="text-sm text-slate-500">2026 年度青年政策總預算</p>
          <div>
            <div className="mb-1 flex items-center justify-between text-xs font-semibold">
              <span className="text-slate-600">預算執行率</span>
              <span className="text-primary">{BUDGET_EXECUTION_RATE}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${BUDGET_EXECUTION_RATE}%` }}
              />
            </div>
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
            <BudgetTrendChart />
          </div>
          <p className="text-[11px] text-slate-400">
            近 5 年年度總預算趨勢（億元），佔位圖表，數值為示意。
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
