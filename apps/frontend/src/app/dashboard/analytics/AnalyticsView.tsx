"use client";
import { useState, type ReactNode } from "react";
import {
  useOverviewAnalytics,
  useChannelScore,
  useTopicRanking,
  useChannelRanking,
  useRecommendations,
  useRecommendationAction,
  useGenerateRecommendations,
} from "@/lib/hooks/useAnalytics";
import { useChannels } from "@/lib/hooks/useChannels";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { SkeletonMetric, SkeletonRow } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import type {
  Recommendation,
  RecommendationType,
  RecommendationPriority,
  TopicRankEntry,
  ChannelRankEntry,
  DimensionalScores,
  TopicRecommendation,
} from "@/lib/types";
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
} from "recharts";
import {
  Eye,
  DollarSign,
  Clock,
  Users,
  Lightbulb,
  RefreshCw,
  Image as ImageIcon,
  Mic2,
  Repeat2,
  TrendingDown,
  TrendingUp,
  Globe2,
  Check,
  X,
  Clock as ClockIcon,
  Trophy,
  Zap,
} from "lucide-react";
import { formatViews, formatRevenue, formatShortDate } from "@/lib/utils/format";

// ── Constants ─────────────────────────────────────────────────────────────────

const PERIODS = [
  { label: "7d",  value: 7 },
  { label: "28d", value: 28 },
  { label: "90d", value: 90 },
];

const CHART_STYLE = {
  contentStyle: { background: "#18181b", border: "1px solid #27272a", borderRadius: 8, fontSize: 12 },
  tickStyle: { fontSize: 10, fill: "#6b7280" },
};

const TYPE_META: Record<RecommendationType, { icon: ReactNode; label: string; color: string }> = {
  improve_thumbnail: { icon: <ImageIcon className="h-3.5 w-3.5" />, label: "Thumbnail", color: "text-orange-400 bg-orange-950/60" },
  improve_hook:      { icon: <Mic2 className="h-3.5 w-3.5" />,      label: "Hook",      color: "text-yellow-400 bg-yellow-950/60" },
  repeat_format:     { icon: <Repeat2 className="h-3.5 w-3.5" />,   label: "Repeat",    color: "text-green-400 bg-green-950/60" },
  kill_topic:        { icon: <TrendingDown className="h-3.5 w-3.5" />, label: "Kill",   color: "text-red-400 bg-red-950/60" },
  scale_topic:       { icon: <TrendingUp className="h-3.5 w-3.5" />, label: "Scale",    color: "text-brand-400 bg-brand-950/60" },
  localize:          { icon: <Globe2 className="h-3.5 w-3.5" />,     label: "Localize", color: "text-purple-text bg-purple-muted/60" },
};

const PRIORITY_BADGE: Record<RecommendationPriority, string> = {
  critical: "bg-red-950 text-red-400 border-red-800",
  high:     "bg-orange-950 text-orange-400 border-orange-800",
  medium:   "bg-yellow-950 text-yellow-500 border-yellow-800",
  low:      "bg-gray-800 text-gray-400 border-gray-700",
};

const TOPIC_REC_COLOR: Record<TopicRecommendation, string> = {
  pursue:  "text-green-400 bg-green-950/60",
  consider: "text-brand-400 bg-brand-950/60",
  monitor: "text-yellow-400 bg-yellow-950/60",
  kill:    "text-red-400 bg-red-950/60",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function ScoreRing({ score }: { score: number }) {
  const pct = Math.round(score);
  const color =
    pct >= 70 ? "#22c55e" :
    pct >= 45 ? "#f59e0b" :
    "#ef4444";

  const radius = 30;
  const circumference = 2 * Math.PI * radius;
  const dash = (pct / 100) * circumference;

  return (
    <div className="relative flex items-center justify-center" style={{ width: 88, height: 88 }}>
      <svg width="88" height="88" viewBox="0 0 88 88" className="-rotate-90">
        <circle cx="44" cy="44" r={radius} fill="none" strokeWidth="6" stroke="#27272a" />
        <circle
          cx="44" cy="44" r={radius} fill="none" strokeWidth="6"
          stroke={color}
          strokeDasharray={`${dash} ${circumference}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
      </svg>
      <span className="absolute text-xl font-bold tabular-nums" style={{ color }}>
        {pct}
      </span>
    </div>
  );
}

function DimBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-500">{label}</span>
        <span className="text-gray-300 tabular-nums">{Math.round(value)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-gray-800 overflow-hidden">
        <div
          className="h-full rounded-full bg-brand-500 transition-all duration-500"
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
    </div>
  );
}

// ── Sub-views ─────────────────────────────────────────────────────────────────

function OverviewTab({ days }: { days: number }) {
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

  const byDate: Record<string, { date: string; views: number; revenue: number }> = {};
  data?.forEach((ch) =>
    ch.snapshots?.forEach((s) => {
      if (!byDate[s.snapshot_date]) {
        byDate[s.snapshot_date] = { date: s.snapshot_date, views: 0, revenue: 0 };
      }
      byDate[s.snapshot_date].views   += s.views;
      byDate[s.snapshot_date].revenue += s.revenue_usd;
    })
  );
  const chartData = Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date));

  if (isError) return <ErrorState onRetry={refetch} />;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonMetric key={i} />)
        ) : (
          <>
            <StatCard label="Total Views"     value={totals ? formatViews(totals.views)     : "—"} icon={<Eye className="h-3.5 w-3.5" />} />
            <StatCard label="Revenue"         value={totals ? formatRevenue(totals.revenue) : "—"} icon={<DollarSign className="h-3.5 w-3.5" />} />
            <StatCard label="Watch Time (h)"  value={totals ? formatViews(Math.round(totals.watchTime / 3600)) : "—"} icon={<Clock className="h-3.5 w-3.5" />} />
            <StatCard
              label="Net Subscribers"
              value={totals ? (totals.subscribers >= 0 ? "+" : "") + formatViews(totals.subscribers) : "—"}
              icon={<Users className="h-3.5 w-3.5" />}
            />
          </>
        )}
      </div>

      <div className="card p-5">
        <h2 className="t-section mb-4">Daily Views</h2>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="viewsGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="date" tickFormatter={formatShortDate} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(v) => formatViews(v as number)} tick={CHART_STYLE.tickStyle} axisLine={false} tickLine={false} />
              <Tooltip {...CHART_STYLE} labelFormatter={(v) => formatShortDate(String(v))} formatter={(v: number) => [formatViews(v), "Views"]} />
              <Area type="monotone" dataKey="views" stroke="#6366f1" strokeWidth={2} fill="url(#viewsGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-40 text-sm text-gray-600">No data for this period</div>
        )}
      </div>

      <div className="card p-5">
        <h2 className="t-section mb-4">Daily Revenue</h2>
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

function ScoresTab({ period }: { period: number }) {
  const { data: channels, isLoading: channelsLoading } = useChannels(1);
  const firstChannel = channels?.items[0];
  const { data: score, isLoading: scoreLoading } = useChannelScore(firstChannel?.id ?? "", period);

  const loading = channelsLoading || scoreLoading;

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="card p-6 animate-pulse h-48" />
        ))}
      </div>
    );
  }

  if (!score) {
    return (
      <EmptyState
        icon={<Zap className="h-6 w-6" />}
        title="No performance scores"
        description="Connect a channel and sync analytics to compute performance scores."
        className="py-20"
      />
    );
  }

  const dims: { key: keyof DimensionalScores; label: string }[] = [
    { key: "view_score",      label: "Views" },
    { key: "ctr_score",       label: "CTR" },
    { key: "retention_score", label: "Retention" },
    { key: "revenue_score",   label: "Revenue" },
    { key: "growth_score",    label: "Growth" },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Composite score */}
        <div className="card p-6 flex items-center gap-6">
          <ScoreRing score={score.score} />
          <div className="flex-1 space-y-1">
            <p className="t-section">Channel Score</p>
            <p className="t-muted">{period}d composite performance</p>
            {score.rank_overall !== null && (
              <div className="flex items-center gap-1.5 mt-2">
                <Trophy className="h-3.5 w-3.5 text-yellow-500" />
                <span className="text-xs text-gray-400">Rank #{score.rank_overall} overall</span>
              </div>
            )}
          </div>
        </div>

        {/* Raw metrics */}
        <div className="card p-6 space-y-3">
          <p className="t-section">Raw Metrics</p>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="t-label">Views</p>
              <p className="text-sm font-semibold text-gray-100 tabular-nums">{formatViews(score.raw_views)}</p>
            </div>
            <div>
              <p className="t-label">CTR</p>
              <p className="text-sm font-semibold text-gray-100 tabular-nums">{(score.raw_ctr * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="t-label">Retention</p>
              <p className="text-sm font-semibold text-gray-100 tabular-nums">{(score.raw_retention * 100).toFixed(0)}%</p>
            </div>
            <div>
              <p className="t-label">RPM</p>
              <p className="text-sm font-semibold text-gray-100 tabular-nums">${score.raw_rpm.toFixed(2)}</p>
            </div>
            <div>
              <p className="t-label">Revenue</p>
              <p className="text-sm font-semibold text-gray-100 tabular-nums">{formatRevenue(score.raw_revenue)}</p>
            </div>
            <div>
              <p className="t-label">Subs Net</p>
              <p className="text-sm font-semibold text-gray-100 tabular-nums">
                {score.raw_subs_net >= 0 ? "+" : ""}{score.raw_subs_net.toLocaleString()}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Dimensional breakdown */}
      <div className="card p-6 space-y-4">
        <p className="t-section">Score Breakdown</p>
        <div className="space-y-3">
          {dims.map(({ key, label }) => (
            <DimBar key={key} label={label} value={score.dimensions[key]} />
          ))}
        </div>
      </div>
    </div>
  );
}

function RankingsTab({ period }: { period: number }) {
  const { data: topicData, isLoading: topicsLoading } = useTopicRanking(period);
  const { data: channelData, isLoading: channelsLoading } = useChannelRanking(period);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Topic Rankings */}
      <div className="card p-5">
        <h2 className="t-section mb-4">Topic Performance</h2>
        {topicsLoading ? (
          <div className="space-y-0">{Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}</div>
        ) : !topicData?.entries.length ? (
          <EmptyState icon={<Lightbulb className="h-4 w-4" />} title="No topic data" className="py-10" />
        ) : (
          <div className="divide-y divide-gray-800/60">
            {topicData.entries.map((entry: TopicRankEntry, idx: number) => (
              <div key={entry.topic_id} className="flex items-center gap-3 py-3">
                <span className="w-5 text-xs font-bold text-gray-600 tabular-nums">{idx + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-200 truncate">{entry.title}</p>
                  <p className="t-muted mt-0.5">
                    {entry.publication_count} vids · {formatViews(Math.round(entry.avg_views))} avg views
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className="text-sm font-bold tabular-nums text-gray-100">{Math.round(entry.score)}</span>
                  <span className={`inline-flex items-center rounded-md px-1.5 py-0 text-[10px] font-semibold capitalize ${TOPIC_REC_COLOR[entry.recommendation]}`}>
                    {entry.recommendation}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Channel Rankings */}
      <div className="card p-5">
        <h2 className="t-section mb-4">Channel Ranking</h2>
        {channelsLoading ? (
          <div className="space-y-0">{Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}</div>
        ) : !channelData?.entries.length ? (
          <EmptyState icon={<Trophy className="h-4 w-4" />} title="No channel data" className="py-10" />
        ) : (
          <div className="divide-y divide-gray-800/60">
            {channelData.entries.map((entry: ChannelRankEntry) => (
              <div key={entry.channel_id} className="flex items-center gap-3 py-3">
                <span className="w-5 text-xs font-bold text-gray-600 tabular-nums">{entry.rank}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-200 truncate">{entry.name}</p>
                  <p className="t-muted mt-0.5 capitalize">{entry.niche}</p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className="text-sm font-bold tabular-nums text-gray-100">{Math.round(entry.score)}</span>
                  <span className="t-muted tabular-nums">{(entry.avg_ctr * 100).toFixed(1)}% CTR</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RecCard({ rec, channelId }: { rec: Recommendation; channelId: string }) {
  const { apply, dismiss, snooze } = useRecommendationAction(channelId);
  const meta = TYPE_META[rec.rec_type];
  const busy = apply.isPending || dismiss.isPending || snooze.isPending;

  return (
    <div className="rounded-xl border bg-gray-900/40 p-4 space-y-2.5" style={{ borderColor: "var(--border)" }}>
      <div className="flex items-start gap-2.5">
        <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${meta.color}`}>
          {meta.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-gray-400">{meta.label}</span>
            <span className={`inline-flex items-center rounded border px-1.5 py-0 text-[10px] font-semibold uppercase tracking-wider ${PRIORITY_BADGE[rec.priority]}`}>
              {rec.priority}
            </span>
          </div>
          <p className="text-sm font-medium text-gray-100 mt-0.5 leading-snug">{rec.title}</p>
        </div>
      </div>

      <p className="t-muted leading-relaxed">{rec.body}</p>

      {rec.metric_key && rec.metric_current !== null && (
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="font-medium text-gray-400">{rec.metric_key}:</span>
          <span className="tabular-nums text-gray-300">{(rec.metric_current * 100).toFixed(1)}%</span>
          {rec.metric_target !== null && (
            <>
              <span>→</span>
              <span className="tabular-nums text-green-400">{(rec.metric_target * 100).toFixed(1)}%</span>
            </>
          )}
          {rec.impact_label && (
            <span className="ml-auto text-brand-400 font-medium">{rec.impact_label}</span>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 pt-0.5">
        <button
          disabled={busy}
          onClick={() => apply.mutate(rec.id)}
          className="flex items-center gap-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 px-3 py-1.5 text-xs font-medium text-white transition-colors disabled:opacity-50"
        >
          <Check className="h-3 w-3" /> Apply
        </button>
        <button
          disabled={busy}
          onClick={() => snooze.mutate(rec.id)}
          className="flex items-center gap-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300 transition-colors disabled:opacity-50"
        >
          <ClockIcon className="h-3 w-3" /> Snooze
        </button>
        <button
          disabled={busy}
          onClick={() => dismiss.mutate(rec.id)}
          className="ml-auto flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-gray-600 hover:text-gray-400 transition-colors disabled:opacity-50"
        >
          <X className="h-3 w-3" /> Dismiss
        </button>
      </div>
    </div>
  );
}

function RecommendationsTab({ period }: { period: number }) {
  const { data: channels } = useChannels(1);
  const channelId = channels?.items[0]?.id ?? "";
  const { data, isLoading, isError } = useRecommendations(channelId);
  const generate = useGenerateRecommendations(channelId);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="t-muted">{data?.length ?? 0} pending recommendations</p>
        <button
          disabled={generate.isPending || !channelId}
          onClick={() => generate.mutate(period)}
          className="flex items-center gap-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 ${generate.isPending ? "animate-spin" : ""}`} />
          Regenerate
        </button>
      </div>

      {generate.isError && (
        <p className="text-xs text-red-400 px-1">Failed to regenerate recommendations. Please try again.</p>
      )}

      {isLoading ? (
        <div className="space-y-0">{Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)}</div>
      ) : isError ? (
        <ErrorState message="Failed to load recommendations." />
      ) : !data?.length ? (
        <EmptyState
          icon={<Lightbulb className="h-5 w-5" />}
          title="No recommendations"
          description="Click Regenerate to run the recommendation engine for your channel."
          className="py-16"
        />
      ) : (
        <div className="space-y-3">
          {data.map((rec) => (
            <RecCard key={rec.id} rec={rec} channelId={channelId} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function AnalyticsView() {
  const [tab, setTab] = useState("overview");
  const [period, setPeriod] = useState(28);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Performance scores, rankings, and growth recommendations"
        actions={
          <div className="flex rounded-lg border border-gray-800 overflow-hidden">
            {PERIODS.map((p) => (
              <button
                key={p.value}
                onClick={() => setPeriod(p.value)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  period === p.value
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
          <TabsTrigger value="scores">Score</TabsTrigger>
          <TabsTrigger value="rankings">Rankings</TabsTrigger>
          <TabsTrigger value="recommendations">Recommendations</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab days={period} />
        </TabsContent>
        <TabsContent value="scores">
          <ScoresTab period={period} />
        </TabsContent>
        <TabsContent value="rankings">
          <RankingsTab period={period} />
        </TabsContent>
        <TabsContent value="recommendations">
          <RecommendationsTab period={period} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
