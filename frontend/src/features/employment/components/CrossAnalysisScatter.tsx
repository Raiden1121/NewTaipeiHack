import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useEmploymentScatter } from "@/lib/api/queries";
import type { EmploymentScatterAnalysis, Regression, ScatterPoint } from "@/lib/api/types";

const VB_W = 480;
const VB_H = 260;
const PAD = { left: 46, right: 14, top: 14, bottom: 34 };
const PLOT_W = VB_W - PAD.left - PAD.right;
const PLOT_H = VB_H - PAD.top - PAD.bottom;

function extent(values: number[]): [number, number] {
  if (values.length === 0) return [0, 1];
  return [Math.min(...values), Math.max(...values)];
}

function ScatterPanel({ plot }: { plot: EmploymentScatterAnalysis["plots"][number] }) {
  const [xMin, xMax] = extent(plot.points.map((p) => p.x));
  const [yMin, yMax] = extent(plot.points.map((p) => p.y));
  const scaleX = (value: number) =>
    PAD.left + ((value - xMin) / (xMax - xMin || 1)) * PLOT_W;
  const scaleY = (value: number) =>
    PAD.top + (1 - (value - yMin) / (yMax - yMin || 1)) * PLOT_H;

  const regression: Regression = plot.regression;
  const regressionStart = { x: xMin, y: regression.slope * xMin + regression.intercept };
  const regressionEnd = { x: xMax, y: regression.slope * xMax + regression.intercept };

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="mb-2 text-sm font-bold text-slate-800">{plot.title}</p>

      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        className="block h-auto w-full"
        role="img"
        aria-label={`${plot.title}散佈圖`}
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
          x1={scaleX(regressionStart.x)}
          y1={scaleY(regressionStart.y)}
          x2={scaleX(regressionEnd.x)}
          y2={scaleY(regressionEnd.y)}
          className="stroke-accent-slate"
          strokeWidth={1.5}
          strokeDasharray="5 4"
        />
        {plot.points.map((point: ScatterPoint) => (
          <circle
            key={point.district_id}
            cx={scaleX(point.x)}
            cy={scaleY(point.y)}
            r={5}
            className="fill-primary"
            fillOpacity={0.85}
          >
            <title>{`${point.district_name}：${point.x} / ${point.y}`}</title>
          </circle>
        ))}
        <text
          x={PAD.left + PLOT_W / 2}
          y={VB_H - 6}
          textAnchor="middle"
          className="fill-slate-400"
          fontSize={11}
        >
          {plot.x_label}
        </text>
        <text
          x={12}
          y={PAD.top + PLOT_H / 2}
          textAnchor="middle"
          transform={`rotate(-90 12 ${PAD.top + PLOT_H / 2})`}
          className="fill-slate-400"
          fontSize={11}
        >
          {plot.y_label}
        </text>
      </svg>

      <p className="mt-2 text-[11px] text-slate-400">
        R² = {regression.r_squared.toFixed(2)}・{plot.note}
      </p>
    </div>
  );
}

export default function CrossAnalysisScatter() {
  const { data: analysis, isLoading, isError, error, refetch } = useEmploymentScatter();

  if (isLoading) {
    return <Skeleton className="h-[360px] w-full rounded-2xl" />;
  }

  if (isError || !analysis) {
    return (
      <section
        role="alert"
        className="flex min-h-[220px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
      >
        <h2 className="text-lg font-bold text-red-700">跨主題比對分析載入失敗</h2>
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
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {analysis.plots.map((plot) => (
            <ScatterPanel key={plot.id} plot={plot} />
          ))}
        </div>
        {analysis.limitations.length > 0 && (
          <p className="mt-3 text-[11px] text-slate-400">
            限制：{analysis.limitations.join("；")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
