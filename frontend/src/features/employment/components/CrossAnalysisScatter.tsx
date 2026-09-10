import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ScatterPoint {
  x: number;
  y: number;
  urban: boolean;
}

interface ScatterChart {
  id: string;
  chartTitle: string;
  xLabel: string;
  yLabel: string;
  trend: { x1: number; y1: number; x2: number; y2: number };
  points: ScatterPoint[];
}

// 佔位資料，待 Backend API 提供整理後結果。散佈點為 0–100 標準化示意值。
const CHARTS: ScatterChart[] = [
  {
    id: "salary-education",
    chartTitle: "起薪與教育水準相關性（各行政區）",
    xLabel: "高等教育普及率 (%)",
    yLabel: "青年平均起薪 (萬元)",
    trend: { x1: 4, y1: 14, x2: 94, y2: 88 },
    points: [
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
    ],
  },
  {
    id: "housing-salary",
    chartTitle: "房價所得比與平均薪資關聯（各行政區）",
    xLabel: "青年平均月薪 (萬元)",
    yLabel: "房價所得比（倍）",
    trend: { x1: 6, y1: 80, x2: 92, y2: 30 },
    points: [
      { x: 12, y: 74, urban: false },
      { x: 21, y: 83, urban: true },
      { x: 30, y: 66, urban: false },
      { x: 38, y: 72, urban: true },
      { x: 45, y: 58, urban: false },
      { x: 52, y: 64, urban: true },
      { x: 59, y: 47, urban: true },
      { x: 66, y: 52, urban: false },
      { x: 74, y: 39, urban: true },
      { x: 82, y: 44, urban: true },
      { x: 89, y: 31, urban: false },
    ],
  },
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

function ScatterPanel({ chart }: { chart: ScatterChart }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="mb-2 text-sm font-bold text-slate-800">{chart.chartTitle}</p>

      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        className="block h-auto w-full"
        role="img"
        aria-label={`${chart.chartTitle}散佈圖佔位`}
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
          x1={scaleX(chart.trend.x1)}
          y1={scaleY(chart.trend.y1)}
          x2={scaleX(chart.trend.x2)}
          y2={scaleY(chart.trend.y2)}
          className="stroke-accent-slate"
          strokeWidth={1.5}
          strokeDasharray="5 4"
        />
        {chart.points.map((point) => (
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
          {chart.xLabel}
        </text>
        <text
          x={12}
          y={PAD.top + PLOT_H / 2}
          textAnchor="middle"
          transform={`rotate(-90 12 ${PAD.top + PLOT_H / 2})`}
          className="fill-slate-400"
          fontSize={11}
        >
          {chart.yLabel}
        </text>
      </svg>

      <p className="mt-2 text-[11px] text-slate-400">
        佔位散佈圖，數值為示意，待真實統計資料串接。
      </p>
    </div>
  );
}

export default function CrossAnalysisScatter() {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
              Scatter Plot Analysis
            </p>
            <CardTitle className="text-lg font-bold text-slate-900">
              跨主題比對分析
            </CardTitle>
          </div>
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
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {CHARTS.map((chart) => (
            <ScatterPanel key={chart.id} chart={chart} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
