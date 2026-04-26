"use client";
import Link from "next/link";
import { useWorkflow, useWorkflowAudit, useWorkflowAction } from "@/lib/hooks/useWorkflows";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { WorkflowTimeline } from "@/components/ui/WorkflowTimeline";
import type { TimelineStep } from "@/components/ui/WorkflowTimeline";
import { ChevronLeft, Pause, Play, X, RotateCcw } from "lucide-react";
import { formatDate } from "@/lib/utils/format";

function AuditTrail({ runId }: { runId: string }) {
  const { data: auditResponse, isLoading } = useWorkflowAudit(runId);
  const events = auditResponse?.events ?? [];

  if (isLoading) return <SkeletonCard rows={3} />;
  if (events.length === 0) return <p className="t-muted py-4">No audit events yet.</p>;

  return (
    <ol className="space-y-0">
      {events.map((evt) => (
        <li key={evt.id} className="flex items-start gap-3 py-2.5 border-b border-[var(--border)] last:border-0">
          <span className="w-1.5 h-1.5 rounded-full bg-gray-700 mt-2 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="t-mono text-brand-400">{evt.event_type}</span>
              <span className="t-muted">{evt.actor}</span>
            </div>
            <p className="t-muted mt-0.5">{formatDate(evt.occurred_at)}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

const META_ROWS = (run: ReturnType<typeof useWorkflow>["data"]) =>
  [
    { label: "Pipeline",     value: run?.pipeline_name },
    { label: "Version",      value: run?.pipeline_version },
    { label: "Triggered by", value: run?.triggered_by },
    { label: "Created",      value: run?.created_at    ? formatDate(run.created_at)    : null },
    { label: "Started",      value: run?.started_at    ? formatDate(run.started_at)    : null },
    { label: "Completed",    value: run?.completed_at  ? formatDate(run.completed_at)  : null },
    { label: "Paused",       value: run?.paused_at     ? formatDate(run.paused_at)     : null },
    { label: "Error",        value: run?.error ?? null },
  ].filter((r) => r.value != null);

export function WorkflowDetailView({ id }: { id: string }) {
  const { data: run, isLoading, isError, refetch } = useWorkflow(id);
  const { pause, resume, cancel, retry } = useWorkflowAction(id);

  if (isLoading) return <div className="p-6"><SkeletonCard rows={8} /></div>;
  if (isError || !run)  return <ErrorState onRetry={refetch} />;

  const isActive   = run.status === "running" || run.status === "pending";
  const isPaused   = run.status === "paused";
  const isFailed   = run.status === "failed";
  const isTerminal = run.status === "completed" || run.status === "cancelled";

  const steps: TimelineStep[] = run.jobs.map((job) => ({
    id:          job.id,
    label:       job.step_id,
    type:        job.step_type,
    status:      job.status,
    attempt:     job.attempt,
    maxAttempts: job.max_attempts,
    durationMs:  job.duration_ms,
    error:       job.attempt_history.at(-1)?.error ?? null,
    startedAt:   job.started_at,
  }));

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-start gap-3">
        <Link href="/dashboard/workflows">
          <Button size="xs" variant="ghost" icon={<ChevronLeft className="h-3.5 w-3.5" />}>
            Back
          </Button>
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="t-page">{run.pipeline_name}</h1>
            <StatusBadge status={run.status} />
          </div>
          <p className="t-mono mt-0.5">{run.id}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isActive && (
            <Button size="sm" variant="outline" icon={<Pause className="h-3.5 w-3.5" />}
              loading={pause.isPending} onClick={() => pause.mutate()}>
              Pause
            </Button>
          )}
          {isPaused && (
            <Button size="sm" variant="outline" icon={<Play className="h-3.5 w-3.5" />}
              loading={resume.isPending} onClick={() => resume.mutate()}>
              Resume
            </Button>
          )}
          {isFailed && (
            <Button size="sm" variant="outline" icon={<RotateCcw className="h-3.5 w-3.5" />}
              loading={retry.isPending} onClick={() => retry.mutate()}>
              Retry
            </Button>
          )}
          {!isTerminal && (
            <Button size="sm" variant="danger" icon={<X className="h-3.5 w-3.5" />}
              loading={cancel.isPending} onClick={() => cancel.mutate()}>
              Cancel
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Timeline */}
        <div className="lg:col-span-2 card p-5">
          <p className="t-section mb-5">Steps</p>
          {steps.length === 0
            ? <p className="t-muted py-4">No steps loaded yet.</p>
            : <WorkflowTimeline steps={steps} />
          }
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Details */}
          <div className="card p-5">
            <p className="t-section mb-3">Details</p>
            <dl className="space-y-2">
              {META_ROWS(run).map((row) => (
                <div key={row.label} className="flex justify-between gap-2">
                  <dt className="t-muted shrink-0">{row.label}</dt>
                  <dd className="text-xs text-gray-300 text-right truncate max-w-[60%]">
                    {row.value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Audit */}
          <div className="card p-5">
            <p className="t-section mb-3">Audit Trail</p>
            <AuditTrail runId={id} />
          </div>
        </div>
      </div>
    </div>
  );
}
