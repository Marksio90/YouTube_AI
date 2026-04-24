"use client";
import Link from "next/link";
import { useWorkflow, useWorkflowAudit, useWorkflowAction } from "@/lib/hooks/useWorkflows";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import {
  ChevronLeft,
  Pause,
  Play,
  X,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  SkipForward,
} from "lucide-react";
import { formatRelative, formatDate } from "@/lib/utils/format";
import type { WorkflowJob } from "@/lib/types";
import { cn } from "@/lib/utils/cn";

const JOB_ICON: Record<string, React.ElementType> = {
  completed: CheckCircle2,
  failed: XCircle,
  running: Loader2,
  skipped: SkipForward,
  pending: Clock,
  scheduled: Clock,
  retrying: RotateCcw,
  cancelled: XCircle,
};

const JOB_COLOR: Record<string, string> = {
  completed: "text-success-text",
  failed: "text-danger-text",
  running: "text-brand-400 animate-spin",
  skipped: "text-gray-500",
  pending: "text-gray-600",
  scheduled: "text-warning-text",
  retrying: "text-warning-text",
  cancelled: "text-gray-600",
};

function JobRow({ job }: { job: WorkflowJob }) {
  const Icon = JOB_ICON[job.status] ?? Clock;
  return (
    <div className="flex items-start gap-3 py-3 border-b border-gray-800/60 last:border-0">
      <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", JOB_COLOR[job.status])} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-gray-200">{job.step_id}</p>
          <StatusBadge status={job.status} />
          {job.is_manual_result && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-muted/60 text-purple-text">manual</span>
          )}
        </div>
        <p className="text-xs text-gray-500 font-mono mt-0.5">{job.step_type}</p>
        {job.status === "failed" && job.attempt_history.length > 0 && (
          <p className="text-xs text-danger-text mt-1 truncate">
            {job.attempt_history[job.attempt_history.length - 1]?.error}
          </p>
        )}
        <div className="flex items-center gap-3 mt-1 text-[11px] text-gray-600">
          <span>Attempt {job.attempt}/{job.max_attempts}</span>
          {job.started_at && <span>Started {formatRelative(job.started_at)}</span>}
          {job.duration_ms && <span>{(job.duration_ms / 1000).toFixed(1)}s</span>}
        </div>
      </div>
    </div>
  );
}

function AuditTimeline({ runId }: { runId: string }) {
  const { data, isLoading } = useWorkflowAudit(runId);
  if (isLoading) return <SkeletonCard rows={3} />;
  if (!data?.length) return <p className="text-sm text-gray-600 py-4">No audit events yet.</p>;

  return (
    <div className="space-y-0">
      {data.map((evt) => (
        <div key={evt.id} className="flex items-start gap-3 py-2.5 border-b border-gray-800/40 last:border-0">
          <div className="w-1.5 h-1.5 rounded-full bg-gray-700 mt-2 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-brand-400">{evt.event_type}</span>
              <span className="text-[11px] text-gray-600">{evt.actor}</span>
            </div>
            <p className="text-[11px] text-gray-500 mt-0.5">{formatDate(evt.occurred_at)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export function WorkflowDetailView({ id }: { id: string }) {
  const { data: run, isLoading, isError, refetch } = useWorkflow(id);
  const { pause, resume, cancel, retry } = useWorkflowAction(id);

  if (isLoading) return <div className="p-6"><SkeletonCard rows={8} /></div>;
  if (isError || !run) return <ErrorState onRetry={refetch} />;

  const isActive = run.status === "running" || run.status === "pending";
  const isPaused = run.status === "paused";
  const isFailed = run.status === "failed";
  const isTerminal = run.status === "completed" || run.status === "cancelled";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Link href="/dashboard/workflows" className="mt-0.5">
          <Button size="xs" variant="ghost" icon={<ChevronLeft className="h-3.5 w-3.5" />}>Back</Button>
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-gray-100">{run.pipeline_name}</h1>
            <StatusBadge status={run.status} />
          </div>
          <p className="text-xs font-mono text-gray-600 mt-0.5">{run.id}</p>
        </div>
        <div className="flex items-center gap-2">
          {isActive && (
            <Button size="sm" variant="outline" icon={<Pause className="h-3.5 w-3.5" />} loading={pause.isPending} onClick={() => pause.mutate()}>
              Pause
            </Button>
          )}
          {isPaused && (
            <Button size="sm" variant="outline" icon={<Play className="h-3.5 w-3.5" />} loading={resume.isPending} onClick={() => resume.mutate()}>
              Resume
            </Button>
          )}
          {isFailed && (
            <Button size="sm" variant="outline" icon={<RotateCcw className="h-3.5 w-3.5" />} loading={retry.isPending} onClick={() => retry.mutate()}>
              Retry
            </Button>
          )}
          {!isTerminal && (
            <Button size="sm" variant="danger" icon={<X className="h-3.5 w-3.5" />} loading={cancel.isPending} onClick={() => cancel.mutate()}>
              Cancel
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Jobs */}
        <div className="lg:col-span-2 rounded-xl border border-gray-800 bg-surface-raised p-5">
          <h2 className="text-sm font-semibold text-gray-200 mb-3">Steps</h2>
          {run.jobs.length === 0 ? (
            <p className="text-sm text-gray-600 py-4">No steps loaded yet.</p>
          ) : (
            run.jobs.map((job) => <JobRow key={job.id} job={job} />)
          )}
        </div>

        {/* Sidebar: meta + audit */}
        <div className="space-y-4">
          {/* Meta */}
          <div className="rounded-xl border border-gray-800 bg-surface-raised p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-3">Details</h2>
            <dl className="space-y-2 text-xs">
              {[
                { label: "Pipeline", value: run.pipeline_name },
                { label: "Version", value: run.pipeline_version },
                { label: "Triggered by", value: run.triggered_by },
                { label: "Created", value: formatDate(run.created_at) },
                run.started_at ? { label: "Started", value: formatDate(run.started_at) } : null,
                run.completed_at ? { label: "Completed", value: formatDate(run.completed_at) } : null,
                run.paused_at ? { label: "Paused", value: formatDate(run.paused_at) } : null,
                run.error ? { label: "Error", value: run.error } : null,
              ]
                .filter(Boolean)
                .map((item) => (
                  <div key={item!.label} className="flex justify-between gap-2">
                    <dt className="text-gray-600">{item!.label}</dt>
                    <dd className="text-gray-300 text-right truncate max-w-[60%]">{item!.value}</dd>
                  </div>
                ))}
            </dl>
          </div>

          {/* Audit */}
          <div className="rounded-xl border border-gray-800 bg-surface-raised p-5">
            <h2 className="text-sm font-semibold text-gray-200 mb-3">Audit Trail</h2>
            <AuditTimeline runId={id} />
          </div>
        </div>
      </div>
    </div>
  );
}
