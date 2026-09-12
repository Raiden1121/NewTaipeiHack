import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricInfoTooltipProps {
  formula: string;
  className?: string;
}

// 指標旁的小型資訊 icon，滑鼠移入／鍵盤聚焦時顯示計算公式；純說明用途，不影響版面配色邏輯。
export default function MetricInfoTooltip({
  formula,
  className,
}: MetricInfoTooltipProps) {
  return (
    <span className={cn("group relative inline-flex", className)}>
      <button
        type="button"
        tabIndex={0}
        aria-label="計算公式說明"
        className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full text-slate-400 transition-colors hover:text-primary focus:text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <Info className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-[min(16rem,calc(100vw-2rem))] -translate-x-1/2 rounded-lg bg-slate-900 px-3 py-2 text-[11px] font-normal normal-case leading-relaxed text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {formula}
        <span className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 border-4 border-transparent border-t-slate-900" />
      </span>
    </span>
  );
}
