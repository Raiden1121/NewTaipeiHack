import type { ReactNode } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import ParticipationHotspotMap from "./components/ParticipationHotspotMap";
import ParticipationHotspotList from "./components/ParticipationHotspotList";
import ParticipationKpiGrid from "./components/ParticipationKpiGrid";
import ResourceIoCharts from "./components/ResourceIoCharts";
import YouthTopicWordCloud from "./components/YouthTopicWordCloud";
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

export default function PoliticsPage() {
  const { reset } = useQueryErrorResetBoundary();

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-8 px-4 py-6 md:px-6 md:py-8">
      <Section
        eyebrow="Participation Index"
        title="青年參政指數核心總覽"
        description="新北市 29 個行政區之青年參政熱點，點選行政區切換下方三大指標"
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 lg:items-start">
          <div className="lg:col-span-2">
            <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
              <ParticipationHotspotMap />
            </ErrorBoundary>
          </div>
          <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
            <ParticipationHotspotList />
          </ErrorBoundary>
        </div>
        <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
          <ParticipationKpiGrid />
        </ErrorBoundary>
      </Section>

      <Section
        eyebrow="Service Accessibility"
        title="青年政策與服務易達性分析"
        description="服務易達性與資源配置"
      >
        <div>
          <p className="mb-3 text-sm font-bold text-slate-700">資源投入與產出</p>
          <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
            <ResourceIoCharts />
          </ErrorBoundary>
        </div>
      </Section>

      <Section
        eyebrow="Youth Voice"
        title="青年需求與聲音"
        description="各年度青年關注議題之重要程度分布"
      >
        <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
          <YouthTopicWordCloud />
        </ErrorBoundary>
      </Section>
    </div>
  );
}
