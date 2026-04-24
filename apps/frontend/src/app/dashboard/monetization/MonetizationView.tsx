"use client";
import { useState, type ReactNode } from "react";
import {
  useChannelRevenue,
  useChannelRoi,
  useAffiliateLinks,
  useUpdateAffiliateLink,
} from "@/lib/hooks/useMonetization";
import { useChannels } from "@/lib/hooks/useChannels";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { SkeletonMetric, SkeletonRow } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import type {
  RevenueBySource,
  RevenueSourceType,
  AffiliateLink,
} from "@/lib/types";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  DollarSign,
  TrendingUp,
  ShoppingBag,
  Link2,
  ExternalLink,
  Plus,
  ToggleLeft,
  ToggleRight,
  Trophy,
  AlertTriangle,
} from "lucide-react";
import { formatRevenue } from "@/lib/utils/format";

// ── Constants ─────────────────────────────────────────────────────────────────

const PERIODS = [
  { label: "7d",  value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
];

const SOURCE_COLOR: Record<RevenueSourceType, string> = {
  ads:         "#6366f1",
  affiliate:   "#22c55e",
  products:    "#f59e0b",
  sponsorship: "#ec4899",
};

const SOURCE_ICON: Record<RevenueSourceType, ReactNode> = {
  ads:         <DollarSign className="h-3.5 w-3.5" />,
  affiliate:   <Link2 className="h-3.5 w-3.5" />,
  products:    <ShoppingBag className="h-3.5 w-3.5" />,
  sponsorship: <TrendingUp className="h-3.5 w-3.5" />,
};

const CHART_STYLE = {
  contentStyle: {
    background: "#18181b",
    border: "1px solid #27272a",
    borderRadius: 8,
    fontSize: 12,
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function RoiBadge({ roi }: { roi: number | null }) {
  if (roi === null) return <span className="t-muted">—</span>;
  const color = roi >= 200 ? "text-green-400" : roi >= 100 ? "text-yellow-400" : "text-red-400";
  return <span className={`text-sm font-bold tabular-nums ${color}`}>{roi.toFixed(0)}%</span>;
}

function SourceRow({ entry }: { entry: RevenueBySource }) {
  return (
    <div className="flex items-center gap-3 py-3">
      <div
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
        style={{ background: `${SOURCE_COLOR[entry.source]}22`, color: SOURCE_COLOR[entry.source] }}
      >
        {SOURCE_ICON[entry.source]}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-200 capitalize">{entry.source}</p>
        <div className="mt-1 h-1.5 rounded-full bg-gray-800 overflow-hidden" style={{ width: "100%" }}>
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${entry.share_pct}%`,
              background: SOURCE_COLOR[entry.source],
            }}
          />
        </div>
      </div>
      <div className="flex flex-col items-end shrink-0">
        <span className="text-sm font-semibold tabular-nums text-gray-100">
          {formatRevenue(entry.revenue_usd)}
        </span>
        <span className="t-muted tabular-nums">{entry.share_pct.toFixed(1)}%</span>
      </div>
      <div className="w-16 text-right">
        <RoiBadge roi={entry.roi_pct} />
      </div>
    </div>
  );
}

// ── Overview tab ──────────────────────────────────────────────────────────────

function OverviewTab({
  channelId,
  days,
}: {
  channelId: string;
  days: number;
}) {
  const { data, isLoading } = useChannelRevenue(channelId, days);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonMetric key={i} />)}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <EmptyState
        icon={<DollarSign className="h-6 w-6" />}
        title="No revenue data"
        description="Connect a channel and sync analytics to see revenue breakdown."
        className="py-20"
      />
    );
  }

  const pieData = data.by_source.map((s) => ({
    name: s.source,
    value: s.revenue_usd,
  }));

  const barData = data.by_source.map((s) => ({
    name: s.source,
    revenue: s.revenue_usd,
    roi: s.roi_pct ?? 0,
  }));

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Revenue"
          value={formatRevenue(data.total_revenue_usd)}
          icon={<DollarSign className="h-3.5 w-3.5" />}
         
        />
        <StatCard
          label="Total Cost"
          value={formatRevenue(data.total_cost_usd)}
          icon={<ShoppingBag className="h-3.5 w-3.5" />}
        />
        <StatCard
          label="Overall ROI"
          value={data.overall_roi_pct !== null ? `${data.overall_roi_pct.toFixed(0)}%` : "—"}
          icon={<TrendingUp className="h-3.5 w-3.5" />}
         
        />
        <StatCard
          label="Revenue Sources"
          value={String(data.by_source.length)}
          icon={<Link2 className="h-3.5 w-3.5" />}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pie */}
        <div className="card p-5">
          <h2 className="t-section mb-4">Revenue Mix</h2>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {pieData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={SOURCE_COLOR[entry.name as RevenueSourceType]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  {...CHART_STYLE}
                  formatter={(v: number) => [formatRevenue(v), "Revenue"]}
                />
                <Legend
                  formatter={(value) => (
                    <span className="text-xs text-gray-400 capitalize">{value}</span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[220px] t-muted">No data</div>
          )}
        </div>

        {/* Bar */}
        <div className="card p-5">
          <h2 className="t-section mb-4">Revenue vs ROI by Source</h2>
          {barData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={barData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "#6b7280" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => v.charAt(0).toUpperCase() + v.slice(1)}
                />
                <YAxis
                  yAxisId="rev"
                  tickFormatter={(v) => `$${v}`}
                  tick={{ fontSize: 10, fill: "#6b7280" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="roi"
                  orientation="right"
                  tickFormatter={(v) => `${v}%`}
                  tick={{ fontSize: 10, fill: "#6b7280" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  {...CHART_STYLE}
                  formatter={(v: number, name: string) =>
                    name === "roi"
                      ? [`${v.toFixed(0)}%`, "ROI"]
                      : [formatRevenue(v), "Revenue"]
                  }
                />
                <Bar yAxisId="rev" dataKey="revenue" radius={[3, 3, 0, 0]}>
                  {barData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={SOURCE_COLOR[entry.name as RevenueSourceType]}
                    />
                  ))}
                </Bar>
                <Bar yAxisId="roi" dataKey="roi" fill="#4b5563" radius={[3, 3, 0, 0]} opacity={0.6} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[220px] t-muted">No data</div>
          )}
        </div>
      </div>

      {/* Source breakdown table */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="t-section">Breakdown by Source</h2>
          <div className="flex gap-6 text-xs text-gray-500 pr-1">
            <span className="w-20 text-right">Revenue</span>
            <span className="w-16 text-right">ROI</span>
          </div>
        </div>
        <div className="divide-y divide-gray-800/60">
          {data.by_source.map((entry) => (
            <SourceRow key={entry.source} entry={entry} />
          ))}
        </div>
      </div>
    </div>
  );
}

// ── ROI tab ───────────────────────────────────────────────────────────────────

function RoiTab({ channelId, days }: { channelId: string; days: number }) {
  const { data, isLoading } = useChannelRoi(channelId, days);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => <SkeletonMetric key={i} />)}
      </div>
    );
  }

  if (!data) {
    return (
      <EmptyState
        icon={<TrendingUp className="h-6 w-6" />}
        title="No ROI data"
        className="py-20"
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard label="Total Revenue"      value={formatRevenue(data.total_revenue_usd)} icon={<DollarSign className="h-3.5 w-3.5" />} />
        <StatCard label="Total Cost"         value={formatRevenue(data.total_cost_usd)}    icon={<ShoppingBag className="h-3.5 w-3.5" />} />
        <StatCard
          label="Overall ROI"
          value={data.roi_pct !== null ? `${data.roi_pct.toFixed(0)}%` : "—"}
          icon={<TrendingUp className="h-3.5 w-3.5" />}
         
        />
        <StatCard label="Revenue / Video" value={formatRevenue(data.revenue_per_video)} icon={<DollarSign className="h-3.5 w-3.5" />} />
        <StatCard label="Cost / Video"    value={formatRevenue(data.cost_per_video)}    icon={<ShoppingBag className="h-3.5 w-3.5" />} />
      </div>

      {/* Best / Worst */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Trophy className="h-4 w-4 text-yellow-400" />
            <h2 className="t-section">Best Performing Video</h2>
          </div>
          {data.best_publication_id ? (
            <div>
              <p className="t-mono">{data.best_publication_id}</p>
              <p className="text-2xl font-bold text-green-400 mt-2 tabular-nums">
                {data.best_publication_roi?.toFixed(0)}% ROI
              </p>
            </div>
          ) : (
            <p className="t-muted">Not enough per-video data yet</p>
          )}
        </div>

        <div className="card p-5 space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400" />
            <h2 className="t-section">Worst Performing Video</h2>
          </div>
          {data.worst_publication_id ? (
            <div>
              <p className="t-mono">{data.worst_publication_id}</p>
              <p className="text-2xl font-bold text-red-400 mt-2 tabular-nums">
                {data.worst_publication_roi?.toFixed(0)}% ROI
              </p>
            </div>
          ) : (
            <p className="t-muted">Not enough per-video data yet</p>
          )}
        </div>
      </div>

      {data.roi_pct !== null && (
        <div className="card p-5">
          <h2 className="t-section mb-3">ROI Interpretation</h2>
          <div className="space-y-2">
            {[
              { label: "Break even", threshold: 100, desc: "Revenue covers production cost" },
              { label: "Profitable", threshold: 200, desc: ">2× return on investment" },
              { label: "Exceptional", threshold: 500, desc: ">5× return on investment" },
            ].map(({ label, threshold, desc }) => (
              <div key={label} className="flex items-center gap-3">
                <div
                  className={`h-2 w-2 rounded-full shrink-0 ${
                    data.roi_pct! >= threshold ? "bg-green-400" : "bg-gray-700"
                  }`}
                />
                <span className={`text-sm font-medium ${data.roi_pct! >= threshold ? "text-gray-200" : "text-gray-600"}`}>
                  {label}
                </span>
                <span className="t-muted">{desc}</span>
                <span className="ml-auto text-xs text-gray-500 tabular-nums">{threshold}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Affiliate links tab ───────────────────────────────────────────────────────

const PLATFORM_COLOR: Record<string, string> = {
  amazon:     "text-orange-400 bg-orange-950/60",
  impact:     "text-blue-400 bg-blue-950/60",
  shareasale: "text-purple-text bg-purple-muted/60",
  cj:         "text-cyan-400 bg-cyan-950/60",
  custom:     "text-gray-400 bg-gray-800",
};

function AffiliateTab({ channelId }: { channelId: string }) {
  const { data, isLoading } = useAffiliateLinks(channelId);
  const update = useUpdateAffiliateLink(channelId);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="t-muted">{data?.length ?? 0} active links</p>
        <button className="flex items-center gap-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 px-3 py-1.5 text-xs font-medium text-white transition-colors">
          <Plus className="h-3.5 w-3.5" /> Add Link
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-0">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}
        </div>
      ) : !data?.length ? (
        <EmptyState
          icon={<Link2 className="h-5 w-5" />}
          title="No affiliate links"
          description="Add trackable affiliate links to monitor clicks, conversions, and commissions."
          className="py-16"
        />
      ) : (
        <div className="card divide-y divide-gray-800/60">
          {data.map((link: AffiliateLink) => {
            const cvr =
              link.total_clicks > 0
                ? ((link.total_conversions / link.total_clicks) * 100).toFixed(1)
                : "—";
            return (
              <div key={link.id} className="flex items-start gap-4 p-4">
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold capitalize ${PLATFORM_COLOR[link.platform] ?? PLATFORM_COLOR.custom}`}>
                  {link.platform.slice(0, 2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-gray-100">{link.name}</p>
                    <a
                      href={link.destination_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-gray-600 hover:text-gray-400 transition-colors"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                  <div className="flex flex-wrap gap-4 text-xs text-gray-500">
                    <span><span className="text-gray-400 font-medium">{link.total_clicks.toLocaleString()}</span> clicks</span>
                    <span><span className="text-gray-400 font-medium">{link.total_conversions}</span> conv</span>
                    <span><span className="text-gray-400 font-medium">{cvr}%</span> CVR</span>
                    <span className="text-green-400 font-semibold">{formatRevenue(link.total_revenue_usd)}</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-gray-600">
                    <span className="capitalize">{link.commission_type}</span>
                    <span>·</span>
                    <span>
                      {link.commission_type === "percentage"
                        ? `${link.commission_value}%`
                        : formatRevenue(link.commission_value)}
                    </span>
                    {link.slug && (
                      <>
                        <span>·</span>
                        <span className="t-mono">/go/{link.slug}</span>
                      </>
                    )}
                  </div>
                </div>
                <button
                  onClick={() =>
                    update.mutate({ id: link.id, data: { is_active: !link.is_active } })
                  }
                  disabled={update.isPending}
                  className="shrink-0 text-gray-500 hover:text-gray-300 transition-colors disabled:opacity-40"
                  title={link.is_active ? "Deactivate" : "Activate"}
                >
                  {link.is_active ? (
                    <ToggleRight className="h-5 w-5 text-green-400" />
                  ) : (
                    <ToggleLeft className="h-5 w-5" />
                  )}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function MonetizationView() {
  const [tab, setTab] = useState("overview");
  const [days, setDays] = useState(30);
  const { data: channels } = useChannels(1);
  const channelId = channels?.items[0]?.id ?? "";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Monetization"
        description="Revenue breakdown, ROI, and affiliate link tracking"
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

      <Tabs value={tab} onChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="roi">ROI</TabsTrigger>
          <TabsTrigger value="affiliate">Affiliate Links</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab channelId={channelId} days={days} />
        </TabsContent>
        <TabsContent value="roi">
          <RoiTab channelId={channelId} days={days} />
        </TabsContent>
        <TabsContent value="affiliate">
          <AffiliateTab channelId={channelId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
