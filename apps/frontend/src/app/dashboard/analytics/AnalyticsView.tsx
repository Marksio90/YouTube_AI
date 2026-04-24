"use client";
import { useState } from "react";
import { useOverviewAnalytics } from "@/lib/hooks/useAnalytics";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { SkeletonMetric } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { formatViews, formatRevenue, formatShortDate } from "@/lib/utils/format";
import { Eye, DollarSign, Clock, Users } from "lucide-react";

const PERIODS = [
  { label: "7d",  value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
];

const CHART_STYLE = {
  contentStyle: { background: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 12 },
  tickStyle: { fontSize: 10, fill: "#6b7280" },
};

export function AnalyticsView() {
  const [days, setDays] = useState(30);
  const { data, isLoading, isError, refetch } = useOverviewAnalytics(days);

  const totals = data?.reduce(
    (acc, ch) => ({
      views: acc.views + ch.total_views,
      revenue: acc.revenue + ch.total_revenue_usd,
      watchTime: acc.watchTime + ch.avg_view_duration_seconds * ch.total_views,
      subscribers: acc.subscribers + ch.subscribers_net,
    }),
    { views: 0, revenue: 0, watchTime: 0, subscribers: 0 }
  );

  // Merge snapshots by date
  const byDate: Record<string, { date: string; views: number; revenue: number; watchTime: number }> = {};
  data?.forEach((ch) =>
    ch.snapshots.forEach((s) => {
      if (!byDate[s.snapshot_date]) {
        byDate[s.snapshot_date] = { date: s.snapshot_date, views: 0, revenue: 0, watchTime: 0 };
      }
      byDate[s.snapshot_date].views     += s.views;
      byDate[s.snapshot_date].revenue   += s.revenue_usd;
      byDate[s.snapshot_date].watchTime += s.watch_time_hours;
    })
  );
  const chartData = Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date));

  if (isError) return <ErrorState onRetry={refetch} />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Cross-channel performance overview"
        actions={
          <div className="flex rounded-lg border border-gray-800 overflow-hidden">
            {PERIODS.map((p) => (
              <button
                key={p.value}
                onClick={() => setDays(p.value)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  days === p.value
                    ? "bg-brand-950 text-brand-300"
                    : "text-gray-500 hover:text-gray-200 hover:bg-gray-800"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        }
      />

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonMetric key={i} />)
        ) : (
          <>
            <StatCard label="Total Views" value={totals ? formatViews(totals.views) : "—"} icon={<Eye className="h-3.5 w-3.5" />} />
            <StatCard label="Revenue" value={totals ? formatRevenue(totals.revenue) : "—"} icon={<DollarSign className="h-3.5 w-3.5" />} />
            <StatCard
              label="Watch Time (h)"
              value={totals ? formatViews(Math.round(totals.watchTime / 3600)) : "—"}
              icon={<Clock className="h-3.5 w-3.5" />}
            />
            <StatCard
              label="Net Subscribers"
              value={totals ? (totals.subscribers >= 0 ? "+" : "") + formatViews(totals.subscribers) : "—"}
              icon={<Users className="h-3.5 w-3.5" />}
            />
          </>
        )}
      </div>

      {/* Views chart */}
      <div className="rounded-xl border border-gray-800 bg-surface-raised p-5">
        <h2 className="text-sm font-semibold text-gray-200 mb-4">Daily Views</h2>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="aViewsGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="date" tickFormatter={formatShortDate} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(v) => formatViews(v as number)} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
              <Tooltip {...CHART_STYLE} labelFormatter={(v) => formatShortDate(String(v))} formatter={(v: number) => [formatViews(v), "Views"]} />
              <Area type="monotone" dataKey="views" stroke="#6366f1" strokeWidth={2} fill="url(#aViewsGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-40 text-sm text-gray-600">No data for this period</div>
        )}
      </div>

      {/* Revenue chart */}
      <div className="rounded-xl border border-gray-800 bg-surface-raised p-5">
        <h2 className="text-sm font-semibold text-gray-200 mb-4">Daily Revenue</h2>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="date" tickFormatter={formatShortDate} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(v) => `$${v}`} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
              <Tooltip {...CHART_STYLE} labelFormatter={(v) => formatShortDate(String(v))} formatter={(v: number) => [formatRevenue(v), "Revenue"]} />
              <Bar dataKey="revenue" fill="#22c55e" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-40 text-sm text-gray-600">No data for this period</div>
        )}
      </div>
    </div>
  );
}
