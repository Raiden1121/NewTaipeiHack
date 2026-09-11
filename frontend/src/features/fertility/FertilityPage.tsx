import type { ReactNode } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import FertilityDistributionMap from "./components/FertilityDistributionMap";
import CoreFertilityKpiPanel from "./components/CoreFertilityKpiPanel";
import OverlayComparisonPanel from "./components/OverlayComparisonPanel";
import FamilyFriendlinessPanel from "./components/FamilyFriendlinessPanel";
import SectionErrorFallback from "@/components/shared/SectionErrorFallback";

interface SectionProps {
  eyebrow: string;
  title: string;
  description?: string;
  children: ReactNode;
}

function Section({ eyebrow, title, description, children }: SectionProps) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          {eyebrow}
        </p>
        <h2 className="text-xl font-bold text-slate-900">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm text-slate-500">{description}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export default function FertilityPage() {
  const { reset } = useQueryErrorResetBoundary();

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-8 px-4 py-6 md:px-6 md:py-8">
      <Section
        eyebrow="Fertility Report"
        title="青年生育分析報告"
        description="分析新北市 29 個行政區 18–35 歲青年人口生育趨勢與資源投入狀況，點選行政區切換右側核心指標"
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
              <FertilityDistributionMap />
            </ErrorBoundary>
          </div>
          <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
            <CoreFertilityKpiPanel />
          </ErrorBoundary>
        </div>
      </Section>

      <Section
        eyebrow="Overlay & Investment"
        title="機會疊圖與資源量化評估"
        description="生育率與就業機會之散佈迴歸分析，以及各行政區青年成家環境友善度"
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
              <OverlayComparisonPanel />
            </ErrorBoundary>
          </div>
          <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
            <FamilyFriendlinessPanel />
          </ErrorBoundary>
        </div>
      </Section>
    </div>
  );
}
