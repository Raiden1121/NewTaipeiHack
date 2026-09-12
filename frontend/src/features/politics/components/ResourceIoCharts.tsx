import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { usePoliticsResourceIo } from "@/lib/api/queries";
import type { BudgetTrendPoint } from "@/lib/api/types";

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

// 長標籤（如「資本門設備與投資」）換行呈現，避免與相鄰長條的標籤重疊。
function splitLabel(label: string, maxCharsPerLine = 5): string[] {
  if (label.length <= maxCharsPerLine) return [label];
  return [label.slice(0, maxCharsPerLine), label.slice(maxCharsPerLine)];
}

const CHART_VB_W = 280;
const CHART_VB_H = 190;

function DepartmentBarChart({
  departments,
}: {
  departments: { label: string; amount_thousand: number; share_percent: number }[];
}) {
  const vbW = CHART_VB_W;
  const vbH = CHART_VB_H;
  const labelH = 44;
  const barsTop = 14;
  const barsBottom = vbH - labelH;
  const plotH = barsBottom - barsTop;
  const gap = 14;
  const barWidth = (vbW - gap * (departments.length + 1)) / departments.length;
  const max = Math.max(...departments.map((item) => item.share_percent));

  const bars = departments.map((item, index) => {
    const height = (item.share_percent / max) * plotH;
    return {
      ...item,
      x: gap + index * (barWidth + gap),
      y: barsBottom - height,
      width: barWidth,
      height,
      lines: splitLabel(item.label),
    };
  });

  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      className="block h-auto w-full"
      role="img"
      aria-label="青年局各科別預算比例長條圖"
    >
      {bars.map((bar) => (
        <rect
          key={bar.label}
          x={bar.x}
          y={bar.y}
          width={bar.width}
          height={bar.height}
          rx={3}
          className="fill-primary/60"
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
          key={`${bar.label}-value`}
          x={bar.x + bar.width / 2}
          y={bar.y - 4}
          textAnchor="middle"
          className="fill-slate-600"
          fontSize={10}
          fontWeight={700}
        >
          {bar.share_percent.toFixed(1)}%
        </text>
      ))}
      {bars.map((bar) => (
        <text
          key={`${bar.label}-label`}
          textAnchor="middle"
          className="fill-slate-400"
          fontSize={10}
        >
          {bar.lines.map((line, lineIndex) => (
            <tspan key={line} x={bar.x + bar.width / 2} y={barsBottom + 16 + lineIndex * 12}>
              {line}
            </tspan>
          ))}
        </text>
      ))}
    </svg>
  );
}

function LineChart({ trend }: { trend: BudgetTrendPoint[] }) {
  const vbW = CHART_VB_W;
  const vbH = CHART_VB_H;
  const labelH = 26;
  const top = 14;
  const bottom = vbH - labelH;
  const plotH = bottom - top;
  const leftPad = 16;
  const rightPad = 10;
  const stepX = (vbW - leftPad - rightPad) / (trend.length - 1 || 1);

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
      const x = leftPad + item.index * stepX;
      const y = bottom - ((item.value_thousand - min) / (max - min || 1)) * plotH;
      return { x, y, year: item.year_roc };
    });

  const polylinePoints = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`);
  const firstX = points[0]?.x.toFixed(1) ?? "0";
  const lastX = points[points.length - 1]?.x.toFixed(1) ?? "0";

  const axisTopY = top - 6;
  const axisRightX = vbW - rightPad / 2;
  const yLabelX = leftPad - 12;
  const yLabelY = (top + bottom) / 2;

  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      className="block h-auto w-full"
      role="img"
      aria-label="年度總預算趨勢折線圖，近五年"
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
          x={leftPad + index * stepX}
          y={bottom + 18}
          textAnchor="middle"
          className="fill-slate-400"
          fontSize={11}
        >
          {item.year_roc} 年
        </text>
      ))}
    </svg>
  );
}

function DonutChart({ executionRate }: { executionRate: number }) {
  const vbW = CHART_VB_W;
  const vbH = CHART_VB_H;
  const cx = vbW / 2;
  const cy = vbH / 2;
  const stroke = 18;
  const radius = 68;
  const circumference = 2 * Math.PI * radius;
  const dash = (clamp(executionRate, 0, 100) / 100) * circumference;
  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      className="block h-auto w-full"
      role="img"
      aria-label={`青年局預算執行率 ${executionRate}% 環圈圖`}
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
        {executionRate}%
      </text>
    </svg>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-[190px] flex-col items-center justify-center gap-1 text-center">
      <p className="text-sm font-semibold text-slate-400">資料待補</p>
      <p className="text-xs text-slate-400">{message}</p>
    </div>
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
      </CardContent>
    </Card>
  );
}

export default function ResourceIoCharts() {
  const { data: analysis, isLoading, isError, error, refetch } = usePoliticsResourceIo();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-64 w-full rounded-2xl" />
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
        <h2 className="text-lg font-bold text-red-700">資源投入與產出載入失敗</h2>
        <p className="text-sm text-red-600">
          {error instanceof Error ? error.message : "請稍後再試。"}
        </p>
        <Button variant="destructive" onClick={() => refetch()}>
          重新載入
        </Button>
      </section>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <ChartCard eyebrow="By Department" title="青年局各科別預算比例">
        {analysis.budget_by_department && analysis.budget_by_department.length > 0 ? (
          <DepartmentBarChart departments={analysis.budget_by_department} />
        ) : (
          <EmptyState message="青年局決算科別拆分尚未提供，見 api_contract.md §6.3" />
        )}
      </ChartCard>
      <ChartCard eyebrow="Yearly Trend" title="年度總預算趨勢">
        <LineChart trend={analysis.budgetTrend} />
      </ChartCard>
      <ChartCard eyebrow="Budget" title="青年局預算執行率">
        {analysis.executionRate === null ? (
          <EmptyState message="決算尚未公告，暫無法計算執行率" />
        ) : (
          <DonutChart executionRate={analysis.executionRate} />
        )}
      </ChartCard>
    </div>
  );
}
