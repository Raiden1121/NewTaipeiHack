import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// 佔位圖表數值皆為示意，待真實統計資料串接。
const GRANT_BY_AREA = [40, 62, 34, 78, 52, 46, 58];
const GRANT_TREND = [28, 34, 31, 45, 52, 60, 71, 66];
const BUDGET_EXECUTION = 92;

const VB_W = 260;
const VB_H = 140;

function BarChart() {
  const max = Math.max(...GRANT_BY_AREA);
  const gap = 10;
  const barWidth = (VB_W - gap * (GRANT_BY_AREA.length + 1)) / GRANT_BY_AREA.length;
  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className="block h-auto w-full"
      role="img"
      aria-label="補助地區分布長條圖佔位"
    >
      {GRANT_BY_AREA.map((value, index) => {
        const height = (value / max) * (VB_H - 24);
        const x = gap + index * (barWidth + gap);
        return (
          <rect
            key={index}
            x={x}
            y={VB_H - 16 - height}
            width={barWidth}
            height={height}
            rx={3}
            className={index === 3 ? "fill-primary" : "fill-primary/30"}
          />
        );
      })}
      <line
        x1={0}
        y1={VB_H - 16}
        x2={VB_W}
        y2={VB_H - 16}
        className="stroke-slate-200"
        strokeWidth={1}
      />
    </svg>
  );
}

function LineChart() {
  const max = Math.max(...GRANT_TREND);
  const min = Math.min(...GRANT_TREND);
  const stepX = VB_W / (GRANT_TREND.length - 1);
  const points = GRANT_TREND.map((value, index) => {
    const x = index * stepX;
    const y = VB_H - 12 - ((value - min) / (max - min)) * (VB_H - 28);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className="block h-auto w-full"
      role="img"
      aria-label="補助金額年度趨勢折線圖佔位"
    >
      <polyline
        points={`0,${VB_H - 12} ${points.join(" ")} ${VB_W},${VB_H - 12}`}
        className="fill-primary/10 stroke-none"
      />
      <polyline
        points={points.join(" ")}
        className="fill-none stroke-primary"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {points.map((point) => {
        const [x, y] = point.split(",");
        return (
          <circle key={point} cx={x} cy={y} r={2.5} className="fill-primary" />
        );
      })}
    </svg>
  );
}

function DonutChart() {
  const size = 140;
  const stroke = 16;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = (BUDGET_EXECUTION / 100) * circumference;
  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className="mx-auto block h-auto w-[140px]"
      role="img"
      aria-label={`青年局預算執行率 ${BUDGET_EXECUTION}% 環圈圖佔位`}
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        className="fill-none stroke-slate-100"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        className="fill-none stroke-accent-teal"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${dash} ${circumference - dash}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x="50%"
        y="50%"
        textAnchor="middle"
        dominantBaseline="central"
        className="fill-slate-900"
        fontSize="24"
        fontWeight="700"
      >
        {BUDGET_EXECUTION}%
      </text>
    </svg>
  );
}

interface ChartCardProps {
  eyebrow: string;
  title: string;
  children: ReactNode;
}

function ChartCard({ eyebrow, title, children }: ChartCardProps) {
  return (
    <Card className="h-full">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          {eyebrow}
        </p>
        <CardTitle className="text-base font-bold text-slate-900">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          {children}
        </div>
        <p className="text-[11px] text-slate-400">佔位圖表，數值為示意。</p>
      </CardContent>
    </Card>
  );
}

export default function ResourceIoCharts() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <ChartCard eyebrow="By Area" title="補助地區分布">
        <BarChart />
      </ChartCard>
      <ChartCard eyebrow="Yearly Trend" title="補助金額年度趨勢">
        <LineChart />
      </ChartCard>
      <ChartCard eyebrow="Budget" title="青年局預算執行率">
        <DonutChart />
      </ChartCard>
    </div>
  );
}
