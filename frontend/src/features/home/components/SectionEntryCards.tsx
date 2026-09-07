import { Link } from "react-router-dom";
import { Briefcase, Vote, Baby, Sparkles } from "lucide-react";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import type { DistrictSummary } from "@/types/district";

function average(
  districts: DistrictSummary[],
  selector: (district: DistrictSummary) => number,
) {
  if (districts.length === 0) return 0;
  return (
    districts.reduce((total, district) => total + selector(district), 0) /
    districts.length
  );
}

const SECTIONS = [
  {
    key: "employment",
    title: "青年就業",
    to: "/employment",
    metricLabel: "平均機會指數",
    icon: Briefcase,
    selector: (district: DistrictSummary) => district.opportunityIndex,
    format: (value: number) => value.toFixed(1),
  },
  {
    key: "politics",
    title: "青年參政",
    to: "/politics",
    metricLabel: "平均參政指數",
    icon: Vote,
    selector: (district: DistrictSummary) => district.youthParticipationIndex,
    format: (value: number) => value.toFixed(1),
  },
  {
    key: "fertility",
    title: "青年生育",
    to: "/fertility",
    metricLabel: "平均生育率",
    icon: Baby,
    selector: (district: DistrictSummary) => district.fertilityRate,
    format: (value: number) => `${value.toFixed(1)}‰`,
  },
  {
    key: "policy-support",
    title: "施政協助",
    to: "/policy-support",
    metricLabel: "政策支持度分數",
    icon: Sparkles,
    selector: (district: DistrictSummary) => district.policySupportScore,
    format: (value: number) => value.toFixed(1),
  },
] as const;

export default function SectionEntryCards() {
  const {
    data: districts = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useDistrictSummary();

  if (isLoading) {
    return (
      <div
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
        data-testid="entry-cards-skeleton"
      >
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-28 w-full rounded-2xl" />
        ))}
      </div>
    );
  }

  if (isError) {
    const message =
      error instanceof Error
        ? error.message
        : "板塊入口資料載入失敗，請稍後再試。";

    return (
      <section
        role="alert"
        className="flex min-h-[140px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
        data-testid="entry-cards-error"
      >
        <h2 className="text-lg font-bold text-red-700">板塊入口資料載入失敗</h2>
        <p className="text-sm text-red-600">{message}</p>
        <Button variant="destructive" onClick={() => refetch()}>
          重新載入
        </Button>
      </section>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {SECTIONS.map((section) => {
        const value = average(districts, section.selector);
        const Icon = section.icon;
        return (
          <Link key={section.key} to={section.to} className="block">
            <Card className="h-full transition-shadow hover:shadow-md">
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-base font-bold text-slate-900">
                  {section.title}
                </CardTitle>
                <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <p className="text-xs font-semibold uppercase tracking-wide text-accent-slate">
                  {section.metricLabel}
                </p>
                <p className="mt-1 text-xl font-bold text-primary">
                  {section.format(value)}
                </p>
              </CardContent>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}
