"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useWorkflows, useTriggerWorkflow } from "@/lib/hooks/useWorkflows";
import { PageHeader } from "@/components/shared/PageHeader";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Play, GitBranch, ChevronRight } from "lucide-react";
import { formatRelative } from "@/lib/utils/format";
import type { WorkflowRunSummary } from "@/lib/types";

const COLUMNS: Column<WorkflowRunSummary>[] = [
  {
    key: "pipeline",
    header: "Pipeline",
    render: (r) => (
      <div>
        <p className="font-medium text-gray-200">{r.pipeline_name}</p>
        <p className="text-xs text-gray-500 font-mono">{r.id.slice(0, 8)}…</p>
      </div>
    ),
  },
  {
    key: "progress",
    header: "Progress",
    render: () => <span className="text-xs text-gray-600">—</span>,
  },
  {
    key: "triggered_by",
    header: "Trigger",
    render: (r) => <span className="text-xs text-gray-500">{r.triggered_by}</span>,
  },
  {
    key: "status",
    header: "Status",
    render: (r) => <StatusBadge status={r.status} />,
  },
  {
    key: "created_at",
    header: "Started",
    render: (r) => <span className="text-xs text-gray-500">{formatRelative(r.created_at)}</span>,
  },
  {
    key: "actions",
    header: "",
    render: () => <ChevronRight className="h-4 w-4 text-gray-600" />,
    className: "text-right",
  },
];

export function WorkflowsView() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = useWorkflows({ page });
  const trigger = useTriggerWorkflow();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workflows"
        description="Pipeline execution runs and their status"
        actions={
          <Button
            size="sm"
            icon={<Play className="h-3.5 w-3.5" />}
            loading={trigger.isPending}
            onClick={() => trigger.mutate({ pipeline_name: "youtube_video" })}
          >
            New Run
          </Button>
        }
      />
      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-5"><SkeletonCard rows={5} /></div>
        ) : isError ? (
          <ErrorState onRetry={refetch} />
        ) : !data?.items.length ? (
          <EmptyState
            icon={<GitBranch className="h-5 w-5" />}
            title="No workflow runs"
            description="Trigger your first pipeline run to generate content end-to-end."
            action={
              <Button size="sm" icon={<Play className="h-3.5 w-3.5" />} onClick={() => trigger.mutate({ pipeline_name: "youtube_video" })}>
                New Run
              </Button>
            }
          />
        ) : (
          <>
            <DataTable
              columns={COLUMNS}
              data={data.items}
              keyFn={(r) => r.id}
              onRowClick={(r) => router.push(`/dashboard/workflows/${r.id}`)}
            />
            {(data.has_prev || data.has_next) && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800">
                <span className="text-xs text-gray-500">{data.total} total</span>
                <div className="flex gap-2">
                  <Button size="xs" variant="outline" disabled={!data.has_prev} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                  <Button size="xs" variant="outline" disabled={!data.has_next} onClick={() => setPage((p) => p + 1)}>Next</Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
