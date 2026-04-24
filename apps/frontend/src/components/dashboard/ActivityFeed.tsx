"use client";
import { useWorkflows } from "@/lib/hooks/useWorkflows";
import { StatusBadge } from "@/components/ui/Badge";
import { SkeletonRow } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { GitBranch } from "lucide-react";
import { formatRelative } from "@/lib/utils/format";

export function ActivityFeed() {
  const { data, isLoading } = useWorkflows({ pageSize: 8 });

  return (
    <div className="card p-5">
      <h2 className="t-section mb-4">Recent Workflows</h2>
      {isLoading ? (
        <div className="space-y-0">
          {Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
        </div>
      ) : !data?.items.length ? (
        <EmptyState
          icon={<GitBranch className="h-5 w-5" />}
          title="No workflow runs yet"
          description="Trigger a pipeline to see activity here."
          className="py-8"
        />
      ) : (
        <div className="divide-y divide-gray-800/60">
          {data.items.map((run) => (
            <div key={run.id} className="flex items-center gap-3 py-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gray-800 text-gray-500 shrink-0">
                <GitBranch className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-200 truncate">{run.pipeline_name}</p>
                <p className="text-xs text-gray-600">{formatRelative(run.created_at)}</p>
              </div>
              <StatusBadge status={run.status} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
