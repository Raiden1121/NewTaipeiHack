import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface AnalysisTab {
  id: string;
  label: string;
  chartTitle: string;
  xLabel: string;
  yLabel: string;
}

// 佔位資料，待 Backend API 提供整理後結果。
const TABS: AnalysisTab[] = [
  {
    id: "salary-education",
    label: "起薪 x 教育水準",
    chartTitle: "起薪與教育水準相關性（各行政區）",
    xLabel: "高等教育普及率 (%)",
    yLabel: "青年平均起薪 (萬元)",
  },
  {
    id: "startup-shortage",
    label: "就業啟業 x 缺工",
    chartTitle: "青年創業活躍度與產業缺工關聯（各行政區）",
    xLabel: "產業缺工率 (%)",
    yLabel: "青年創業登記數",
  },
  {
    id: "housing-salary",
    label: "房價 x 平均薪資",
    chartTitle: "房價所得比與平均薪資關聯（各行政區）",
    xLabel: "青年平均月薪 (萬元)",
    yLabel: "房價所得比",
  },
  {
    id: "startup-demand",
    label: "啟業 x 職缺需求",
    chartTitle: "創業活躍度與職缺需求關聯（各行政區）",
    xLabel: "職缺需求指數",
    yLabel: "新設事業家數",
  },
  {
    id: "unemployment-age",
    label: "失業率 x 年齡層",
    chartTitle: "青年失業率與年齡分層關聯（各行政區）",
    xLabel: "年齡層 (歲)",
    yLabel: "失業率 (%)",
  },
];

// 佔位散佈點（0–100 標準化），待真實統計資料替換。
const SCATTER_POINTS = [
  { x: 14, y: 22, urban: false },
  { x: 24, y: 40, urban: true },
  { x: 33, y: 31, urban: false },
  { x: 41, y: 53, urban: true },
  { x: 47, y: 44, urban: false },
  { x: 54, y: 61, urban: true },
  { x: 61, y: 55, urban: true },
  { x: 67, y: 71, urban: false },
  { x: 73, y: 64, urban: true },
  { x: 81, y: 82, urban: true },
  { x: 88, y: 74, urban: false },
];

const VB_W = 480;
const VB_H = 260;
const PAD = { left: 46, right: 14, top: 14, bottom: 34 };
const PLOT_W = VB_W - PAD.left - PAD.right;
const PLOT_H = VB_H - PAD.top - PAD.bottom;

function scaleX(value: number) {
  return PAD.left + (value / 100) * PLOT_W;
}

function scaleY(value: number) {
  return PAD.top + (1 - value / 100) * PLOT_H;
}

export default function CrossAnalysisScatter() {
  const [activeId, setActiveId] = useState(TABS[0].id);
  const activeTab = TABS.find((tab) => tab.id === activeId) ?? TABS[0];

  return (
    <Card>
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Scatter Plot Analysis
        </p>
        <CardTitle className="text-lg font-bold text-slate-900">
          跨主題比對分析
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          {TABS.map((tab, index) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveId(tab.id)}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs font-semibold transition-colors",
                tab.id === activeId
                  ? "bg-primary text-primary-foreground"
                  : "bg-slate-100 text-slate-500 hover:text-slate-700",
              )}
            >
              {index + 1}. {tab.label}
            </button>
          ))}
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-bold text-slate-800">
              {activeTab.chartTitle}
            </p>
            <div className="flex items-center gap-3 text-[11px] font-semibold text-accent-slate">
              <span className="flex items-center gap-1">
                <span
                  className="h-2.5 w-2.5 rounded-full bg-primary"
                  aria-hidden="true"
                />
                都會區
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="h-2.5 w-2.5 rounded-full bg-accent-teal"
                  aria-hidden="true"
                />
                非都會區
              </span>
            </div>
          </div>

          <svg
            viewBox={`0 0 ${VB_W} ${VB_H}`}
            className="block h-auto w-full"
            role="img"
            aria-label={`${activeTab.chartTitle}散佈圖佔位`}
          >
            <line
              x1={PAD.left}
              y1={PAD.top}
              x2={PAD.left}
              y2={VB_H - PAD.bottom}
              className="stroke-slate-300"
              strokeWidth={1}
            />
            <line
              x1={PAD.left}
              y1={VB_H - PAD.bottom}
              x2={VB_W - PAD.right}
              y2={VB_H - PAD.bottom}
              className="stroke-slate-300"
              strokeWidth={1}
            />
            <line
              x1={scaleX(4)}
              y1={scaleY(14)}
              x2={scaleX(94)}
              y2={scaleY(88)}
              className="stroke-accent-slate"
              strokeWidth={1.5}
              strokeDasharray="5 4"
            />
            {SCATTER_POINTS.map((point) => (
              <circle
                key={`${point.x}-${point.y}`}
                cx={scaleX(point.x)}
                cy={scaleY(point.y)}
                r={5}
                className={point.urban ? "fill-primary" : "fill-accent-teal"}
                fillOpacity={0.85}
              />
            ))}
            <text
              x={PAD.left + PLOT_W / 2}
              y={VB_H - 6}
              textAnchor="middle"
              className="fill-slate-400"
              fontSize={11}
            >
              {activeTab.xLabel}
            </text>
            <text
              x={12}
              y={PAD.top + PLOT_H / 2}
              textAnchor="middle"
              transform={`rotate(-90 12 ${PAD.top + PLOT_H / 2})`}
              className="fill-slate-400"
              fontSize={11}
            >
              {activeTab.yLabel}
            </text>
          </svg>

          <p className="mt-2 text-[11px] text-slate-400">
            佔位散佈圖，數值為示意，待真實統計資料串接。
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
