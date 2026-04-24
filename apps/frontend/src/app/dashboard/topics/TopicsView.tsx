"use client";
import { useState } from "react";
import { useTopics } from "@/lib/hooks/useTopics";
import { PageHeader } from "@/components/shared/PageHeader";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { ScoreBar } from "@/components/ui/Progress";
import { Plus, Lightbulb } from "lucide-react";
import { formatRelative } from "@/lib/utils/format";
import type { Topic } from "@/lib/types";

const COLUMNS: Column<Topic>[] = [
  {
    key: "title",
    header: "Topic",
    render: (t) => (
      <div>
        <p className="font-medium text-gray-200 truncate max-w-xs">{t.title}</p>
        {t.keywords.length > 0 && (
          <div className="flex gap-1 mt-1 flex-wrap">
            {t.keywords.slice(0, 3).map((k) => (
              <span key={k} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-500">{k}</span>
            ))}
          </div>
        )}
      </div>
    ),
  },
  {
    key: "source",
    header: "Source",
    render: (t) => <Badge variant="outline">{t.source}</Badge>,
  },
  {
    key: "trend_score",
    header: "Trend",
    render: (t) =>
      t.trend_score !== null ? (
        <div className="w-24">
          <ScoreBar score={t.trend_score} max={10} />
        </div>
      ) : (
        <span className="text-gray-600">—</span>
      ),
  },
  {
    key: "status",
    header: "Status",
    render: (t) => <StatusBadge status={t.status} />,
  },
  {
    key: "created_at",
    header: "Added",
    render: (t) => <span className="text-xs text-gray-500">{formatRelative(t.created_at)}</span>,
  },
];

export function TopicsView() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = useTopics({ page });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Topics"
        description="AI-suggested and manually added content ideas"
        actions={
          <Button size="sm" icon={<Plus className="h-3.5 w-3.5" />}>
            Add Topic
          </Button>
        }
      />
      <div className="rounded-xl border border-gray-800 bg-surface-raised overflow-hidden">
        {isLoading ? (
          <div className="p-5"><SkeletonCard rows={6} /></div>
        ) : isError ? (
          <ErrorState onRetry={refetch} />
        ) : !data?.items.length ? (
          <EmptyState
            icon={<Lightbulb className="h-5 w-5" />}
            title="No topics yet"
            description="Add your first content idea or let AI suggest trending topics."
            action={<Button size="sm" icon={<Plus className="h-3.5 w-3.5" />}>Add Topic</Button>}
          />
        ) : (
          <>
            <DataTable columns={COLUMNS} data={data.items} keyFn={(t) => t.id} />
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
