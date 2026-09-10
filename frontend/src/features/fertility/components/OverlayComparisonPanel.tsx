import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// 佔位資料，數值皆為示意，待 Backend API 提供整理後結果。
const FERTILITY_SERIES = [8.6, 8.9, 9.4, 10.8, 11.2, 10.9, 10.4];
const OPPORTUNITY_SERIES = [72, 74, 78, 83, 88, 90, 92];
const AXIS_LABELS = ["林口區", "淡水區", "板橋區", "新莊區", "中和區", "三重區", "永和區"];

const VIEW_OPTIONS = [
  { id: "dual-axis", label: "雙軸折線圖" },
  { id: "scatter", label: "散佈圖" },
] as const;

type ViewId = (typeof VIEW_OPTIONS)[number]["id"];

const VB_W = 520;
const VB_H = 220;
const PAD_X = 28;
const PAD_Y = 24;

function scaleSeries(series: number[]) {
  const max = Math.max(...series);
  const min = Math.min(...series);
  return series.map((value) => (value - min) / (max - min || 1));
}

function DualAxisChart() {
  const fertility = scaleSeries(FERTILITY_SERIES);
  const opportunity = scaleSeries(OPPORTUNITY_SERIES);
  const stepX = (VB_W - PAD_X * 2) / (FERTILITY_SERIES.length - 1);

  const toPoints = (ratios: number[]) =>
    ratios
      .map((ratio, index) => {
        const x = PAD_X + index * stepX;
        const y = VB_H - PAD_Y - ratio * (VB_H - PAD_Y * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className="block h-auto w-full"
      role="img"
      aria-label="青年生育率與青年就業機會指數雙軸折線圖佔位"
    >
      <line
        x1={PAD_X}
        y1={VB_H - PAD_Y}
        x2={VB_W - PAD_X}
        y2={VB_H - PAD_Y}
        className="stroke-slate-200"
        strokeWidth={1}
      />
      <polyline
        points={toPoints(opportunity)}
        className="fill-none stroke-accent-teal"
        strokeWidth={2}
        strokeDasharray="5 4"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <polyline
        points={toPoints(fertility)}
        className="fill-none stroke-primary"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {fertility.map((ratio, index) => {
        const x = PAD_X + index * stepX;
        const y = VB_H - PAD_Y - ratio * (VB_H - PAD_Y * 2);
        return (
          <circle key={index} cx={x} cy={y} r={3} className="fill-primary" />
        );
      })}
      {AXIS_LABELS.map((label, index) => (
        <text
          key={label}
          x={PAD_X + index * stepX}
          y={VB_H - 6}
          textAnchor="middle"
          className="fill-slate-400"
          fontSize="9"
        >
          {label}
        </text>
      ))}
    </svg>
  );
}

function ScatterChart() {
  const fertility = scaleSeries(FERTILITY_SERIES);
  const opportunity = scaleSeries(OPPORTUNITY_SERIES);

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className="block h-auto w-full"
      role="img"
      aria-label="青年生育率與青年就業機會指數散佈圖佔位"
    >
      <line
        x1={PAD_X}
        y1={VB_H - PAD_Y}
        x2={VB_W - PAD_X}
        y2={VB_H - PAD_Y}
        className="stroke-slate-200"
        strokeWidth={1}
      />
      <line
        x1={PAD_X}
        y1={PAD_Y}
        x2={PAD_X}
        y2={VB_H - PAD_Y}
        className="stroke-slate-200"
        strokeWidth={1}
      />
      {FERTILITY_SERIES.map((_, index) => {
        const x = PAD_X + opportunity[index] * (VB_W - PAD_X * 2);
        const y = VB_H - PAD_Y - fertility[index] * (VB_H - PAD_Y * 2);
        return (
          <circle
            key={index}
            cx={x}
            cy={y}
            r={5}
            className="fill-primary/60 stroke-primary"
            strokeWidth={1.5}
          />
        );
      })}
    </svg>
  );
}

export default function OverlayComparisonPanel() {
  // 佔位互動：切換僅改變佔位圖表樣式，尚未影響資料，待 Backend API 串接。
  const [view, setView] = useState<ViewId>("dual-axis");

  return (
    <Card className="h-full">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
              Overlay Analysis
            </p>
            <CardTitle className="text-base font-bold text-slate-900">
              疊圖比較分析
            </CardTitle>
            <p className="mt-1 text-xs text-slate-500">
              青年生育率 vs. 青年就業機會指數
            </p>
          </div>
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
            {VIEW_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => setView(option.id)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                  view === option.id
                    ? "bg-primary text-primary-foreground"
                    : "text-slate-500 hover:text-slate-700",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          {view === "dual-axis" ? <DualAxisChart /> : <ScatterChart />}
        </div>
        <div className="flex items-center gap-4 text-[11px] font-semibold text-accent-slate">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-4 rounded-sm bg-primary" aria-hidden="true" />
            生育率（‰）
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-4 rounded-sm bg-accent-teal"
              aria-hidden="true"
            />
            就業機會指數
          </span>
        </div>
        <p className="text-[11px] text-slate-400">佔位圖表，數值為示意。</p>
      </CardContent>
    </Card>
  );
}
