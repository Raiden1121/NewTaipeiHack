import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useFertilityOverlay } from "@/lib/api/queries";
import type { FertilityOverlayAnalysis } from "@/lib/api/types";

const VB_W = 520;
const VB_H = 240;
const PAD_L = 40;
const PAD_R = 16;
const PAD_T = 16;
const PAD_B = 34;

const PLOT_W = VB_W - PAD_L - PAD_R;
const PLOT_H = VB_H - PAD_T - PAD_B;

function extent(values: number[]): [number, number] {
  if (values.length === 0) return [0, 1];
  return [Math.min(...values), Math.max(...values)];
}

function ScatterRegressionChart({ analysis }: { analysis: FertilityOverlayAnalysis }) {
  const [xMin, xMax] = extent(analysis.points.map((d) => d.x));
  const [yMin, yMax] = extent(analysis.points.map((d) => d.y));

  const toX = (value: number) =>
    PAD_L + ((value - xMin) / (xMax - xMin || 1)) * PLOT_W;
  const toY = (value: number) =>
    PAD_T + (1 - (value - yMin) / (yMax - yMin || 1)) * PLOT_H;

  const { slope, intercept } = analysis.regression;

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className="block h-auto w-full"
      role="img"
      aria-label="青年生育率對青年就業機會指數散佈圖與迴歸線"
    >
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

      {analysis.points.map((point) => (
        <circle
          key={point.district_id}
          cx={toX(point.x)}
          cy={toY(point.y)}
          r={4}
          className="fill-primary/60 stroke-primary"
          strokeWidth={1.5}
        >
          <title>{`${point.district_name}：${point.x} / ${point.y}`}</title>
        </circle>
      ))}

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
  const { data: analysis, isLoading, isError, error, refetch } = useFertilityOverlay();

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
        {isLoading ? (
          <Skeleton className="h-[200px] w-full rounded-xl" />
        ) : isError || !analysis ? (
          <section
            role="alert"
            className="flex min-h-[200px] flex-col items-center justify-center gap-3 rounded-xl border border-red-200 bg-red-50 p-6 text-center"
          >
            <p className="text-sm text-red-600">
              {error instanceof Error ? error.message : "疊圖比較分析載入失敗，請稍後再試。"}
            </p>
            <Button variant="destructive" onClick={() => refetch()}>
              重新載入
            </Button>
          </section>
        ) : (
          <>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <ScatterRegressionChart analysis={analysis} />
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
                線性迴歸線（R² = {analysis.regression.r_squared.toFixed(2)}）
              </span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
