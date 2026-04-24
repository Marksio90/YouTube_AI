"use client";
import { useState } from "react";
import { useChannels } from "@/lib/hooks/useChannels";
import { PageHeader } from "@/components/shared/PageHeader";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Plus, Tv2 } from "lucide-react";
import { formatNumber } from "@/lib/utils/format";
import type { Channel } from "@/lib/types";

const COLUMNS: Column<Channel>[] = [
  {
    key: "name",
    header: "Channel",
    render: (ch) => (
      <div className="flex items-center gap-3">
        {ch.thumbnail_url ? (
          <img src={ch.thumbnail_url} alt="" className="h-8 w-8 rounded-full object-cover" />
        ) : (
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-800 text-gray-500">
            <Tv2 className="h-4 w-4" />
          </div>
        )}
        <div>
          <p className="font-medium text-gray-200">{ch.name}</p>
          <p className="text-xs text-gray-500">{ch.niche}</p>
        </div>
      </div>
    ),
  },
  {
    key: "subscribers",
    header: "Subscribers",
    render: (ch) => <span className="tabular-nums">{formatNumber(ch.subscriber_count)}</span>,
    className: "text-right",
    headerClassName: "text-right",
  },
  {
    key: "avg_views",
    header: "Avg Views",
    render: (ch) => <span className="tabular-nums">{formatNumber(ch.avg_views)}</span>,
    className: "text-right",
    headerClassName: "text-right",
  },
  {
    key: "monetization",
    header: "Monetized",
    render: (ch) => (
      <span className={ch.monetization_enabled ? "text-success-text" : "text-gray-600"}>
        {ch.monetization_enabled ? "Yes" : "No"}
      </span>
    ),
  },
  {
    key: "status",
    header: "Status",
    render: (ch) => <StatusBadge status={ch.status} />,
  },
];

export function ChannelsView() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch } = useChannels(page);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Channels"
        description="Manage your YouTube channels"
        actions={
          <Button size="sm" icon={<Plus className="h-3.5 w-3.5" />}>
            Add Channel
          </Button>
        }
      />
      <div className="rounded-xl border border-gray-800 bg-surface-raised overflow-hidden">
        {isLoading ? (
          <div className="p-5"><SkeletonCard rows={5} /></div>
        ) : isError ? (
          <ErrorState onRetry={refetch} />
        ) : !data?.items.length ? (
          <EmptyState
            icon={<Tv2 className="h-5 w-5" />}
            title="No channels yet"
            description="Connect your first YouTube channel to get started."
            action={<Button size="sm" icon={<Plus className="h-3.5 w-3.5" />}>Add Channel</Button>}
          />
        ) : (
          <>
            <DataTable columns={COLUMNS} data={data.items} keyFn={(ch) => ch.id} />
            {(data.has_prev || data.has_next) && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800">
                <span className="text-xs text-gray-500">{data.total} total</span>
                <div className="flex gap-2">
                  <Button size="xs" variant="outline" disabled={!data.has_prev} onClick={() => setPage((p) => p - 1)}>
                    Previous
                  </Button>
                  <Button size="xs" variant="outline" disabled={!data.has_next} onClick={() => setPage((p) => p + 1)}>
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
