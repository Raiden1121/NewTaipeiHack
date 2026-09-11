import { useState } from "react";
import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// 佔位圖表數值皆為示意，待真實統計資料串接。

interface AreaGrant {
  area: string;
  amount: number;
}

// 佔位：全部行政區補助金額，圖表僅取前七名降冪呈現。
const GRANT_BY_AREA: AreaGrant[] = [
  { area: "板橋區", amount: 186 },
  { area: "三重區", amount: 172 },
  { area: "中和區", amount: 165 },
  { area: "新莊區", amount: 158 },
  { area: "永和區", amount: 141 },
  { area: "土城區", amount: 133 },
  { area: "林口區", amount: 120 },
  { area: "淡水區", amount: 108 },
  { area: "新店區", amount: 96 },
];

const TOP_AREA_GRANTS = [...GRANT_BY_AREA]
  .sort((a, b) => b.amount - a.amount)
  .slice(0, 7);

interface YearlyBudget {
  year: number;
  amount: number;
}

// 佔位：近五年（民國年）年度總預算。
const YEARLY_BUDGET: YearlyBudget[] = [
  { year: 110, amount: 52 },
  { year: 111, amount: 60 },
  { year: 112, amount: 68 },
  { year: 113, amount: 82 },
  { year: 114, amount: 96 },
];

const BUDGET_EXECUTION = 92;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

// 三張圖共用同一 viewBox 比例（寬滿版、依比例縮放），確保滿版寬螢幕時文字等比放大，
// 且三卡在等寬欄位下會自然等高，不需額外固定高度。
const CHART_VB_W = 280;
const CHART_VB_H = 190;

function BarChart() {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const vbW = CHART_VB_W;
  const vbH = CHART_VB_H;
  const labelH = 34;
  const barsTop = 14;
  const barsBottom = vbH - labelH;
  const plotH = barsBottom - barsTop;
  const gap = 8;
  const barWidth =
    (vbW - gap * (TOP_AREA_GRANTS.length + 1)) / TOP_AREA_GRANTS.length;
  const max = Math.max(...TOP_AREA_GRANTS.map((item) => item.amount));

  const bars = TOP_AREA_GRANTS.map((item, index) => {
    const height = (item.amount / max) * plotH;
    return {
      ...item,
      x: gap + index * (barWidth + gap),
      y: barsBottom - height,
      width: barWidth,
      height,
    };
  });

  const hovered = hoveredIndex !== null ? bars[hoveredIndex] : null;
  const tooltipW = 62;
  const tooltipH = 24;
  const tooltipX = hovered
    ? clamp(hovered.x + hovered.width / 2 - tooltipW / 2, 2, vbW - tooltipW - 2)
    : 0;
  const tooltipY = hovered ? Math.max(2, hovered.y - tooltipH - 6) : 0;

  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      className="block h-auto w-full"
      role="img"
      aria-label="補助地區分布長條圖佔位，僅列出前七名"
    >
      {bars.map((bar, index) => (
        <rect
          key={bar.area}
          x={bar.x}
          y={bar.y}
          width={bar.width}
          height={bar.height}
          rx={3}
          className={
            index === hoveredIndex ? "fill-primary" : "fill-primary/30"
          }
          onMouseEnter={() => setHoveredIndex(index)}
          onMouseLeave={() => setHoveredIndex(null)}
        />
      ))}
      <line
        x1={0}
        y1={barsBottom}
        x2={vbW}
        y2={barsBottom}
        className="stroke-slate-200"
        strokeWidth={1}
      />
      {bars.map((bar) => (
        <text
          key={`${bar.area}-label`}
          x={bar.x + bar.width / 2}
          y={barsBottom + 16}
          textAnchor="middle"
          className="fill-slate-400"
          fontSize={11}
        >
          {bar.area}
        </text>
      ))}
      {hovered && (
        <g pointerEvents="none">
          <rect
            x={tooltipX}
            y={tooltipY}
            width={tooltipW}
            height={tooltipH}
            rx={6}
            fill="#10233f"
          />
          <text
            x={tooltipX + tooltipW / 2}
            y={tooltipY + tooltipH / 2 + 1}
            textAnchor="middle"
            dominantBaseline="central"
            fill="#ffffff"
            fontSize={11}
            fontWeight={700}
          >
            {hovered.amount} 萬元
          </text>
        </g>
      )}
    </svg>
  );
}

function LineChart() {
  const vbW = CHART_VB_W;
  const vbH = CHART_VB_H;
  const labelH = 26;
  const top = 14;
  const bottom = vbH - labelH;
  const plotH = bottom - top;
  const amounts = YEARLY_BUDGET.map((item) => item.amount);
  const max = Math.max(...amounts);
  const min = Math.min(...amounts);
  const stepX = vbW / (YEARLY_BUDGET.length - 1);

  const points = YEARLY_BUDGET.map((item, index) => {
    const x = index * stepX;
    const y = bottom - ((item.amount - min) / (max - min)) * plotH;
    return { x, y, year: item.year };
  });
  const polylinePoints = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`);

  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      className="block h-auto w-full"
      role="img"
      aria-label="年度總預算趨勢折線圖佔位，近五年"
    >
      <polyline
        points={`0,${bottom} ${polylinePoints.join(" ")} ${vbW},${bottom}`}
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
        <circle
          key={point.year}
          cx={point.x}
          cy={point.y}
          r={2.5}
          className="fill-primary"
        />
      ))}
      {points.map((point) => (
        <text
          key={`${point.year}-label`}
          x={point.x}
          y={bottom + 18}
          textAnchor="middle"
          className="fill-slate-400"
          fontSize={11}
        >
          {point.year} 年
        </text>
      ))}
    </svg>
  );
}

function DonutChart() {
  // 沿用與長條／折線圖相同的 viewBox 比例，讓三張卡在同寬欄位下自然等高、
  // 文字也隨欄寬等比放大（滿版寬螢幕時不再被固定高度侵限）。
  const vbW = CHART_VB_W;
  const vbH = CHART_VB_H;
  const cx = vbW / 2;
  const cy = vbH / 2;
  const stroke = 18;
  const radius = 68;
  const circumference = 2 * Math.PI * radius;
  const dash = (BUDGET_EXECUTION / 100) * circumference;
  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      className="block h-auto w-full"
      role="img"
      aria-label={`青年局預算執行率 ${BUDGET_EXECUTION}% 環圈圖佔位`}
    >
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        className="fill-none stroke-slate-100"
        strokeWidth={stroke}
      />
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        className="fill-none stroke-accent-teal"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${dash} ${circumference - dash}`}
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        className="fill-slate-900"
        fontSize={30}
        fontWeight={700}
      >
        {BUDGET_EXECUTION}%
      </text>
    </svg>
  );
}

interface ChartCardProps {
  eyebrow: string;
  title: string;
  note?: string;
  children: ReactNode;
}

function ChartCard({ eyebrow, title, note, children }: ChartCardProps) {
  return (
    <Card className="h-full">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          {eyebrow}
        </p>
        <div className="flex items-baseline gap-1.5">
          <CardTitle className="text-base font-bold text-slate-900">
            {title}
          </CardTitle>
          {note ? (
            <span className="text-xs font-medium text-slate-400">{note}</span>
          ) : null}
        </div>
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
      <ChartCard eyebrow="By Area" title="補助地區分布" note="（僅列出前七）">
        <BarChart />
      </ChartCard>
      <ChartCard eyebrow="Yearly Trend" title="年度總預算趨勢">
        <LineChart />
      </ChartCard>
      <ChartCard eyebrow="Budget" title="青年局預算執行率">
        <DonutChart />
      </ChartCard>
    </div>
  );
}
