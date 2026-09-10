import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// 佔位資料，數值皆為示意，待 Backend API 提供整理後結果。
// 每筆為一個行政區：x = 青年就業機會指數，y = 青年生育率（‰）。
const SAMPLE: { opportunity: number; fertility: number }[] = [
  { opportunity: 48, fertility: 7.2 },
  { opportunity: 52, fertility: 6.8 },
  { opportunity: 55, fertility: 8.1 },
  { opportunity: 58, fertility: 7.6 },
  { opportunity: 61, fertility: 9.0 },
  { opportunity: 64, fertility: 8.4 },
  { opportunity: 66, fertility: 10.1 },
  { opportunity: 69, fertility: 9.3 },
  { opportunity: 72, fertility: 9.8 },
  { opportunity: 74, fertility: 11.2 },
  { opportunity: 77, fertility: 10.4 },
  { opportunity: 80, fertility: 11.9 },
  { opportunity: 83, fertility: 11.1 },
  { opportunity: 86, fertility: 12.6 },
  { opportunity: 88, fertility: 12.0 },
  { opportunity: 92, fertility: 13.1 },
];

const VB_W = 520;
const VB_H = 240;
const PAD_L = 40;
const PAD_R = 16;
const PAD_T = 16;
const PAD_B = 34;

const PLOT_W = VB_W - PAD_L - PAD_R;
const PLOT_H = VB_H - PAD_T - PAD_B;

function extent(values: number[]): [number, number] {
  return [Math.min(...values), Math.max(...values)];
}

/** 最小平方法線性迴歸，回傳 y = slope * x + intercept。 */
function linearRegression(points: { x: number; y: number }[]) {
  const n = points.length;
  const sumX = points.reduce((acc, p) => acc + p.x, 0);
  const sumY = points.reduce((acc, p) => acc + p.y, 0);
  const sumXY = points.reduce((acc, p) => acc + p.x * p.y, 0);
  const sumXX = points.reduce((acc, p) => acc + p.x * p.x, 0);
  const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

function ScatterRegressionChart() {
  const [xMin, xMax] = extent(SAMPLE.map((d) => d.opportunity));
  const [yMin, yMax] = extent(SAMPLE.map((d) => d.fertility));

  const toX = (value: number) =>
    PAD_L + ((value - xMin) / (xMax - xMin)) * PLOT_W;
  const toY = (value: number) =>
    PAD_T + (1 - (value - yMin) / (yMax - yMin)) * PLOT_H;

  const { slope, intercept } = linearRegression(
    SAMPLE.map((d) => ({ x: d.opportunity, y: d.fertility })),
  );

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className="block h-auto w-full"
      role="img"
      aria-label="青年生育率對青年就業機會指數散佈圖與迴歸線佔位"
    >
      {/* 軸線 */}
      <line
        x1={PAD_L}
        y1={PAD_T}
        x2={PAD_L}
        y2={VB_H - PAD_B}
        className="stroke-slate-200"
        strokeWidth={1}
      />
      <line
        x1={PAD_L}
        y1={VB_H - PAD_B}
        x2={VB_W - PAD_R}
        y2={VB_H - PAD_B}
        className="stroke-slate-200"
        strokeWidth={1}
      />

      {/* 迴歸線 */}
      <line
        x1={toX(xMin)}
        y1={toY(slope * xMin + intercept)}
        x2={toX(xMax)}
        y2={toY(slope * xMax + intercept)}
        className="stroke-accent-teal"
        strokeWidth={2}
        strokeDasharray="6 4"
        strokeLinecap="round"
      />

      {/* 資料點 */}
      {SAMPLE.map((d, index) => (
        <circle
          key={index}
          cx={toX(d.opportunity)}
          cy={toY(d.fertility)}
          r={4}
          className="fill-primary/60 stroke-primary"
          strokeWidth={1.5}
        />
      ))}

      {/* 軸標題 */}
      <text
        x={PAD_L + PLOT_W / 2}
        y={VB_H - 6}
        textAnchor="middle"
        className="fill-slate-400"
        fontSize="10"
      >
        青年就業機會指數
      </text>
      <text
        x={12}
        y={PAD_T + PLOT_H / 2}
        textAnchor="middle"
        transform={`rotate(-90 12 ${PAD_T + PLOT_H / 2})`}
        className="fill-slate-400"
        fontSize="10"
      >
        青年生育率（‰）
      </text>
    </svg>
  );
}

export default function OverlayComparisonPanel() {
  return (
    <Card className="h-full">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Scatter Analysis
        </p>
        <CardTitle className="text-base font-bold text-slate-900">
          疊圖比較分析
        </CardTitle>
        <p className="mt-1 text-xs text-slate-500">
          青年生育率 vs. 青年就業機會指數（散佈圖＋迴歸線）
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <ScatterRegressionChart />
        </div>
        <div className="flex items-center gap-4 text-[11px] font-semibold text-accent-slate">
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full bg-primary"
              aria-hidden="true"
            />
            行政區（每點一區）
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-0 w-4 border-t-2 border-dashed border-accent-teal"
              aria-hidden="true"
            />
            線性迴歸線
          </span>
        </div>
        <p className="text-[11px] text-slate-400">佔位圖表，數值為示意。</p>
      </CardContent>
    </Card>
  );
}
