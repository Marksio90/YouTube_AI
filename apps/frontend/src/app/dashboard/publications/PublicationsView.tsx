"use client";
import { useState } from "react";
import { usePublications } from "@/lib/hooks/usePublications";
import { PageHeader } from "@/components/shared/PageHeader";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Youtube, ExternalLink } from "lucide-react";
import { formatViews, formatRevenue, formatRelative } from "@/lib/utils/format";
import type { Publication } from "@/lib/types";

const COLUMNS: Column<Publication>[] = [
  {
    key: "title",
    header: "Video",
    render: (p) => (
      <div className="flex items-center gap-3">
        {p.thumbnail_url ? (
          <img src={p.thumbnail_url} alt="" className="h-9 w-16 rounded object-cover flex-shrink-0" />
        ) : (
          <div className="flex h-9 w-16 items-center justify-center rounded bg-gray-800 text-gray-600 flex-shrink-0">
            <Youtube className="h-4 w-4" />
          </div>
        )}
        <div className="min-w-0">
          <p className="font-medium text-gray-200 truncate max-w-xs">{p.title}</p>
          {p.youtube_video_id && (
            <a
              href={`https://youtube.com/watch?v=${p.youtube_video_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-brand-400 hover:text-brand-300 flex items-center gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink className="h-3 w-3" /> Watch
            </a>
          )}
        </div>
      </div>
    ),
  },
  {
    key: "views",
    header: "Views",
    render: (p) => <span className="tabular-nums">{formatViews(p.view_count)}</span>,
    className: "text-right",
    headerClassName: "text-right",
  },
  {
    key: "revenue",
    header: "Revenue",
    render: (p) => <span className="tabular-nums">{formatRevenue(p.revenue_usd)}</span>,
    className: "text-right",
    headerClassName: "text-right",
  },
  {
    key: "status",
    header: "Status",
    render: (p) => <StatusBadge status={p.status} />,
  },
  {
    key: "published_at",
    header: "Published",
    render: (p) => (
      <span className="text-xs text-gray-500">
        {p.published_at ? formatRelative(p.published_at) : p.scheduled_at ? `Scheduled ${formatRelative(p.scheduled_at)}` : "—"}
      </span>
    ),
  },
];

export function PublicationsView() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = usePublications({ page });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Publications"
        description="Published and scheduled YouTube videos"
      />
      <div className="rounded-xl border border-gray-800 bg-surface-raised overflow-hidden">
        {isLoading ? (
          <div className="p-5"><SkeletonCard rows={5} /></div>
        ) : isError ? (
          <ErrorState onRetry={refetch} />
        ) : !data?.items.length ? (
          <EmptyState
            icon={<Youtube className="h-5 w-5" />}
            title="No publications yet"
            description="Run a workflow pipeline to publish your first video."
          />
        ) : (
          <>
            <DataTable columns={COLUMNS} data={data.items} keyFn={(p) => p.id} />
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
