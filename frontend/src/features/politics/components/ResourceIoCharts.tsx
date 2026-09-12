import { useState } from "react";
import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// 佔位圖表數值皆為示意，待真實統計資料串接。

interface DepartmentBudget {
  label: string;
  amount: number; // 千元
  share: number; // %
}

// 佔位：青年局各科別預算比例，待主計處資料串接。
const DEPARTMENT_BUDGET: DepartmentBudget[] = [
  { label: "綜合規劃", amount: 38960, share: 24.42 },
  { label: "職涯發展", amount: 37730, share: 23.65 },
  { label: "創業資源", amount: 70979, share: 44.49 },
  { label: "資本門設備與投資", amount: 11852, share: 7.43 },
];

const SORTED_DEPARTMENT_BUDGET = [...DEPARTMENT_BUDGET].sort(
  (a, b) => b.share - a.share,
);

// 長標籤（如「資本門設備與投資」）換行呈現，避免與相鄰長條的標籤重疊。
function splitLabel(label: string, maxCharsPerLine = 5): string[] {
  if (label.length <= maxCharsPerLine) return [label];
  return [label.slice(0, maxCharsPerLine), label.slice(maxCharsPerLine)];
}

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
  const labelH = 44;
  const barsTop = 14;
  const barsBottom = vbH - labelH;
  const plotH = barsBottom - barsTop;
  const gap = 14;
  const barWidth =
    (vbW - gap * (SORTED_DEPARTMENT_BUDGET.length + 1)) /
    SORTED_DEPARTMENT_BUDGET.length;
  const max = Math.max(...SORTED_DEPARTMENT_BUDGET.map((item) => item.share));

  const bars = SORTED_DEPARTMENT_BUDGET.map((item, index) => {
    const height = (item.share / max) * plotH;
    return {
      ...item,
      x: gap + index * (barWidth + gap),
      y: barsBottom - height,
      width: barWidth,
      height,
      lines: splitLabel(item.label),
    };
  });

  const hovered = hoveredIndex !== null ? bars[hoveredIndex] : null;
  const tooltipW = 88;
  const tooltipH = 34;
  const tooltipX = hovered
    ? clamp(hovered.x + hovered.width / 2 - tooltipW / 2, 2, vbW - tooltipW - 2)
    : 0;
  const tooltipY = hovered ? Math.max(2, hovered.y - tooltipH - 6) : 0;

  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      className="block h-auto w-full"
      role="img"
      aria-label="青年局各科別預算比例長條圖佔位"
    >
      {bars.map((bar, index) => (
        <rect
          key={bar.label}
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
          key={`${bar.label}-label`}
          textAnchor="middle"
          className="fill-slate-400"
          fontSize={11}
        >
          {bar.lines.map((line, lineIndex) => (
            <tspan
              key={line}
              x={bar.x + bar.width / 2}
              y={barsBottom + 16 + lineIndex * 13}
            >
              {line}
            </tspan>
          ))}
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
            y={tooltipY + 14}
            textAnchor="middle"
            dominantBaseline="central"
            fill="#ffffff"
            fontSize={12}
            fontWeight={700}
          >
            {hovered.share}%
          </text>
          <text
            x={tooltipX + tooltipW / 2}
            y={tooltipY + 26}
            textAnchor="middle"
            dominantBaseline="central"
            fill="#cbd5e1"
            fontSize={9.5}
          >
            {hovered.amount.toLocaleString("zh-Hant-TW")} 千元
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
  const leftPad = 16;
  const rightPad = 10;
  const amounts = YEARLY_BUDGET.map((item) => item.amount);
  const max = Math.max(...amounts);
  const min = Math.min(...amounts);
  const stepX = (vbW - leftPad - rightPad) / (YEARLY_BUDGET.length - 1);

  const points = YEARLY_BUDGET.map((item, index) => {
    const x = leftPad + index * stepX;
    const y = bottom - ((item.amount - min) / (max - min)) * plotH;
    return { x, y, year: item.year };
  });
  const polylinePoints = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`);
  const firstX = points[0].x.toFixed(1);
  const lastX = points[points.length - 1].x.toFixed(1);

  const axisTopY = top - 6;
  const axisRightX = vbW - rightPad / 2;
  const yLabelX = leftPad - 12;
  const yLabelY = (top + bottom) / 2;

  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      className="block h-auto w-full"
      role="img"
      aria-label="年度總預算趨勢折線圖佔位，近五年"
    >
      <defs>
        <marker
          id="resource-io-trend-arrow"
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
        x1={leftPad}
        y1={bottom}
        x2={axisRightX}
        y2={bottom}
        className="stroke-slate-300"
        strokeWidth={1}
        markerEnd="url(#resource-io-trend-arrow)"
      />
      <line
        x1={leftPad}
        y1={bottom}
        x2={leftPad}
        y2={axisTopY}
        className="stroke-slate-300"
        strokeWidth={1}
        markerEnd="url(#resource-io-trend-arrow)"
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
      <ChartCard eyebrow="By Department" title="青年局各科別預算比例">
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
