"use client";
import { useMemo } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { useOverviewAnalytics } from "@/lib/hooks/useAnalytics";
import { formatShortDate, formatViews } from "@/lib/utils/format";
import { SkeletonCard } from "@/components/ui/Skeleton";

export function OverviewChart() {
  const { data, isLoading } = useOverviewAnalytics(30);

  const chartData = useMemo(() => {
    const byDate: Record<string, { date: string; views: number; revenue: number }> = {};
    data?.forEach((ch) =>
      ch.daily_snapshots?.forEach((s) => {
        if (!byDate[s.snapshot_date]) {
          byDate[s.snapshot_date] = { date: s.snapshot_date, views: 0, revenue: 0 };
        }
        byDate[s.snapshot_date].views   += s.views;
        byDate[s.snapshot_date].revenue += s.revenue_usd;
      })
    );
    return Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date));
  }, [data]);

  if (isLoading) return <SkeletonCard rows={4} />;

  if (!chartData.length) {
    return (
      <div className="card p-5 flex items-center justify-center h-48 text-sm text-gray-600">
        No analytics data yet
      </div>
    );
  }

  return (
    <div className="card p-5">
      <h2 className="t-section mb-4">Views — Last 30 days</h2>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="viewsGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => formatShortDate(v)}
            tick={{ fontSize: 10, fill: "#6b7280" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v) => formatViews(v as number)}
            tick={{ fontSize: 10, fill: "#6b7280" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{ background: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 12 }}
            labelFormatter={(v) => formatShortDate(String(v))}
            formatter={(v: number) => [formatViews(v), "Views"]}
          />
          <Area type="monotone" dataKey="views" stroke="#6366f1" strokeWidth={2} fill="url(#viewsGrad)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
