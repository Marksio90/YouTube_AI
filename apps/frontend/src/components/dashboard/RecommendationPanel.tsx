"use client";
import { useTopics } from "@/lib/hooks/useTopics";
import { Badge } from "@/components/ui/Badge";
import { SkeletonRow } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { Lightbulb, TrendingUp } from "lucide-react";
import { formatScore } from "@/lib/utils/format";

export function RecommendationPanel() {
  const { data, isLoading } = useTopics({ status: "new", pageSize: 5 });

  return (
    <div className="rounded-xl border border-gray-800 bg-surface-raised p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-gray-200">Top Topics</h2>
        <Badge variant="info" className="text-[10px]">AI picks</Badge>
      </div>
      {isLoading ? (
        <div className="space-y-0">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}
        </div>
      ) : !data?.items.length ? (
        <EmptyState
          icon={<Lightbulb className="h-5 w-5" />}
          title="No topics yet"
          description="Topics will appear here once your channels are connected."
          className="py-8"
        />
      ) : (
        <div className="divide-y divide-gray-800/60">
          {data.items.map((topic) => (
            <div key={topic.id} className="flex items-center gap-3 py-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-muted/60 text-purple-text shrink-0">
                <TrendingUp className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-200 truncate-2">{topic.title}</p>
                <p className="text-xs text-gray-600 mt-0.5">{topic.source}</p>
              </div>
              {topic.trend_score !== null && (
                <span className="text-xs tabular-nums text-purple-text shrink-0">
                  {formatScore(topic.trend_score)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
