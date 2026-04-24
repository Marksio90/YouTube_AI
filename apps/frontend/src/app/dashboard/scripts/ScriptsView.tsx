"use client";
import { useState } from "react";
import { useScripts } from "@/lib/hooks/useScripts";
import { PageHeader } from "@/components/shared/PageHeader";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { ScoreBar } from "@/components/ui/Progress";
import { Wand2, FileText } from "lucide-react";
import { formatRelative, formatDuration } from "@/lib/utils/format";
import type { Script } from "@/lib/types";

const COLUMNS: Column<Script>[] = [
  {
    key: "title",
    header: "Script",
    render: (s) => (
      <div>
        <p className="font-medium text-gray-200 truncate max-w-xs">{s.title}</p>
        {s.hook && <p className="text-xs text-gray-500 truncate max-w-xs mt-0.5">{s.hook}</p>}
      </div>
    ),
  },
  {
    key: "duration",
    header: "Duration",
    render: (s) =>
      s.duration_seconds ? (
        <span className="tabular-nums text-xs">{formatDuration(s.duration_seconds)}</span>
      ) : (
        <span className="text-gray-600">—</span>
      ),
  },
  {
    key: "seo",
    header: "SEO Score",
    render: (s) =>
      s.seo_score !== null ? (
        <div className="w-20"><ScoreBar score={s.seo_score} /></div>
      ) : (
        <span className="text-gray-600">—</span>
      ),
  },
  {
    key: "compliance",
    header: "Compliance",
    render: (s) =>
      s.compliance_score !== null ? (
        <div className="w-20"><ScoreBar score={s.compliance_score} /></div>
      ) : (
        <span className="text-gray-600">—</span>
      ),
  },
  {
    key: "version",
    header: "Ver",
    render: (s) => <span className="text-xs text-gray-500">v{s.version}</span>,
  },
  {
    key: "status",
    header: "Status",
    render: (s) => <StatusBadge status={s.status} />,
  },
  {
    key: "created_at",
    header: "Created",
    render: (s) => <span className="text-xs text-gray-500">{formatRelative(s.created_at)}</span>,
  },
];

export function ScriptsView() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = useScripts({ page });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Scripts"
        description="AI-generated and edited video scripts"
        actions={
          <Button size="sm" icon={<Wand2 className="h-3.5 w-3.5" />}>
            Generate Script
          </Button>
        }
      />
      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-5"><SkeletonCard rows={6} /></div>
        ) : isError ? (
          <ErrorState onRetry={refetch} />
        ) : !data?.items.length ? (
          <EmptyState
            icon={<FileText className="h-5 w-5" />}
            title="No scripts yet"
            description="Generate your first AI script or import an existing one."
            action={<Button size="sm" icon={<Wand2 className="h-3.5 w-3.5" />}>Generate Script</Button>}
          />
        ) : (
          <>
            <DataTable columns={COLUMNS} data={data.items} keyFn={(s) => s.id} />
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
