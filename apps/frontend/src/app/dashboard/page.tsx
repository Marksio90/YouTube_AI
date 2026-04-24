import type { Metadata } from "next";
import { StatsGrid } from "@/components/charts/StatsGrid";
import { RecentVideos } from "@/components/charts/RecentVideos";
import { PipelineActivity } from "@/components/charts/PipelineActivity";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-gray-400 mt-1">AI Media OS — Production overview</p>
      </div>
      <StatsGrid />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RecentVideos />
        <PipelineActivity />
      </div>
    </div>
  );
}
