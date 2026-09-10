import { useState } from "react";
import type { ReactNode } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import OpportunityIndexMap from "./components/OpportunityIndexMap";
import DistrictDetailCard from "./components/DistrictDetailCard";
import CrossAnalysisScatter from "./components/CrossAnalysisScatter";
import SectionErrorFallback from "@/components/shared/SectionErrorFallback";
import { cn } from "@/lib/utils";

interface SectionProps {
  eyebrow: string;
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}

function Section({ eyebrow, title, description, action, children }: SectionProps) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            {eyebrow}
          </p>
          <h2 className="text-xl font-bold text-slate-900">{title}</h2>
          {description ? (
            <p className="mt-1 text-sm text-slate-500">{description}</p>
          ) : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

const TIMEFRAME_OPTIONS = [
  { id: "decade", label: "近十年綜合" },
  { id: "recent", label: "近三年平均" },
] as const;

function TimeframeToggle() {
  // 佔位互動：切換尚未影響資料，待 Backend API 串接。
  const [value, setValue] =
    useState<(typeof TIMEFRAME_OPTIONS)[number]["id"]>("decade");

  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
      {TIMEFRAME_OPTIONS.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => setValue(option.id)}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
            value === option.id
              ? "bg-primary text-primary-foreground"
              : "text-slate-500 hover:text-slate-700",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export default function EmploymentPage() {
  const { reset } = useQueryErrorResetBoundary();

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-8 px-4 py-6 md:px-6 md:py-8">
      <Section
        eyebrow="Opportunity Index"
        title="青年機會指數"
        description="分析新北市 29 個行政區之綜合發展潛力與民生負擔"
        action={<TimeframeToggle />}
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
              <OpportunityIndexMap />
            </ErrorBoundary>
          </div>
          <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
            <DistrictDetailCard />
          </ErrorBoundary>
        </div>
      </Section>

      <Section
        eyebrow="Scatter Analysis"
        title="跨主題比對分析"
        description="探索地域變數間的關聯性與分布集群（Scatter Plot Analysis）"
      >
        <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
          <CrossAnalysisScatter />
        </ErrorBoundary>
      </Section>
    </div>
  );
}
