"use client";
import type { ReactNode } from "react";
import { useRecommendations, useRecommendationAction } from "@/lib/hooks/useAnalytics";
import { useChannels } from "@/lib/hooks/useChannels";
import { Badge } from "@/components/ui/Badge";
import { SkeletonRow } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import type { Recommendation, RecommendationType, RecommendationPriority } from "@/lib/types";
import {
  Lightbulb,
  Image as ImageIcon,
  Mic2,
  Repeat2,
  TrendingDown,
  TrendingUp,
  Globe2,
  Check,
  X,
  Clock,
} from "lucide-react";

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

function RecCard({
  rec,
  channelId,
}: {
  rec: Recommendation;
  channelId: string;
}) {
  const { apply, dismiss, snooze } = useRecommendationAction(channelId);
  const meta = TYPE_META[rec.rec_type];
  const busy = apply.isPending || dismiss.isPending || snooze.isPending;

  return (
    <div className="rounded-xl border bg-gray-900/40 p-4 space-y-2.5" style={{ borderColor: "var(--border)" }}>
      {/* Header */}
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

      {/* Body */}
      <p className="t-muted leading-relaxed">{rec.body}</p>

      {/* Metric evidence */}
      {rec.metric_key && rec.metric_current !== null && (
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="font-medium text-gray-400">{rec.metric_key}:</span>
          <span className="tabular-nums text-gray-300">
            {(rec.metric_current * 100).toFixed(1)}%
          </span>
          {rec.metric_target !== null && (
            <>
              <span>→</span>
              <span className="tabular-nums text-green-400">
                {(rec.metric_target * 100).toFixed(1)}%
              </span>
            </>
          )}
          {rec.impact_label && (
            <span className="ml-auto text-brand-400 font-medium">{rec.impact_label}</span>
          )}
        </div>
      )}

      {/* Actions */}
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
          <Clock className="h-3 w-3" /> Snooze
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

export function RecommendationPanel({ channelId }: { channelId?: string }) {
  const { data: channels } = useChannels(1);
  const effectiveChannelId = channelId ?? channels?.items[0]?.id ?? "";

  const { data, isLoading, isError } = useRecommendations(effectiveChannelId);

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="t-section">Growth Recommendations</h2>
        <Badge variant="info" className="text-[10px]">
          {data?.length ?? 0} pending
        </Badge>
      </div>

      {isLoading ? (
        <div className="space-y-0">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)}
        </div>
      ) : isError ? (
        <ErrorState message="Failed to load recommendations. Please try again." />
      ) : !data?.length ? (
        <EmptyState
          icon={<Lightbulb className="h-5 w-5" />}
          title="No recommendations"
          description="Connect a channel and sync analytics to generate growth recommendations."
          className="py-8"
        />
      ) : (
        <div className="space-y-3">
          {data.slice(0, 5).map((rec) => (
            <RecCard key={rec.id} rec={rec} channelId={effectiveChannelId} />
          ))}
        </div>
      )}
    </div>
  );
}
