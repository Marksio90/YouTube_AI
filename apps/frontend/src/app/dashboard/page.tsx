import type { Metadata } from "next";
import { MetricsGrid } from "@/components/dashboard/MetricCard";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import { RecommendationPanel } from "@/components/dashboard/RecommendationPanel";
import { OverviewChart } from "@/components/charts/OverviewChart";
import { PageHeader } from "@/components/shared/PageHeader";

export const metadata: Metadata = { title: "Overview — AI Media OS" };

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="AI Media OS — production snapshot"
      />
      <MetricsGrid />
      <OverviewChart />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ActivityFeed />
        <RecommendationPanel />
      </div>
    </div>
  );
}
