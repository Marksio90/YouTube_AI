"use client";
import { Eye, DollarSign, Play, BarChart3 } from "lucide-react";
import { StatCard } from "@/components/shared/StatCard";
import { useOverviewAnalytics } from "@/lib/hooks/useAnalytics";
import { formatViews, formatRevenue } from "@/lib/utils/format";

export function MetricsGrid() {
  const { data, isLoading } = useOverviewAnalytics(30);

  const totals = data?.reduce(
    (acc, ch) => ({
      views: acc.views + ch.total_views,
      revenue: acc.revenue + ch.total_revenue_usd,
    }),
    { views: 0, revenue: 0 }
  );

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        label="Total Views (30d)"
        value={totals ? formatViews(totals.views) : "—"}
        loading={isLoading}
        icon={<Eye className="h-3.5 w-3.5" />}
      />
      <StatCard
        label="Revenue (30d)"
        value={totals ? formatRevenue(totals.revenue) : "—"}
        loading={isLoading}
        icon={<DollarSign className="h-3.5 w-3.5" />}
      />
      <StatCard
        label="Active Channels"
        value={data ? String(data.length) : "—"}
        loading={isLoading}
        icon={<Play className="h-3.5 w-3.5" />}
      />
      <StatCard
        label="Avg CTR"
        value={
          data && data.length
            ? `${(data.reduce((a, ch) => a + ch.avg_ctr, 0) / data.length * 100).toFixed(1)}%`
            : "—"
        }
        loading={isLoading}
        icon={<BarChart3 className="h-3.5 w-3.5" />}
      />
    </div>
  );
}
