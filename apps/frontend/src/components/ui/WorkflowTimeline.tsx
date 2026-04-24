import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  SkipForward,
  RotateCcw,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";
import type { JobStatus } from "@/lib/types";

export interface TimelineStep {
  id: string;
  label: string;
  type?: string;
  status: JobStatus;
  attempt?: number;
  maxAttempts?: number;
  durationMs?: number | null;
  error?: string | null;
  startedAt?: string | null;
}

const STATUS_META: Record<
  JobStatus,
  { icon: React.ElementType; iconClass: string; lineClass: string }
> = {
  completed: { icon: CheckCircle2, iconClass: "text-success-text",  lineClass: "bg-success" },
  failed:    { icon: XCircle,      iconClass: "text-danger-text",   lineClass: "bg-danger" },
  running:   { icon: Loader2,      iconClass: "text-brand-400 animate-spin", lineClass: "bg-brand-500" },
  retrying:  { icon: RotateCcw,    iconClass: "text-warning-text",  lineClass: "bg-warning" },
  skipped:   { icon: SkipForward,  iconClass: "text-gray-500",      lineClass: "bg-gray-700" },
  scheduled: { icon: Clock,        iconClass: "text-warning-text",  lineClass: "bg-gray-800" },
  pending:   { icon: Clock,        iconClass: "text-gray-600",      lineClass: "bg-gray-800" },
  cancelled: { icon: AlertCircle,  iconClass: "text-gray-500",      lineClass: "bg-gray-700" },
};

interface WorkflowTimelineProps {
  steps: TimelineStep[];
  className?: string;
}

export function WorkflowTimeline({ steps, className }: WorkflowTimelineProps) {
  return (
    <ol className={cn("space-y-0", className)}>
      {steps.map((step, i) => {
        const { icon: Icon, iconClass, lineClass } = STATUS_META[step.status] ?? STATUS_META.pending;
        const isLast = i === steps.length - 1;

        return (
          <li key={step.id} className="flex gap-3">
            {/* Icon + connector */}
            <div className="flex flex-col items-center shrink-0">
              <div className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full border-2 bg-[#18181b] z-10",
                step.status === "completed" ? "border-success" :
                step.status === "failed"    ? "border-danger" :
                step.status === "running"   ? "border-brand-500" :
                step.status === "retrying"  ? "border-warning" :
                "border-gray-700"
              )}>
                <Icon className={cn("h-3.5 w-3.5", iconClass)} />
              </div>
              {!isLast && (
                <div className={cn("w-0.5 flex-1 mt-1 mb-1 min-h-[20px] rounded-full", lineClass)} />
              )}
            </div>

            {/* Content */}
            <div className={cn("pb-5 flex-1 min-w-0", isLast && "pb-0")}>
              <div className="flex items-center gap-2 pt-0.5">
                <p className={cn(
                  "text-sm font-medium",
                  step.status === "pending" || step.status === "cancelled"
                    ? "text-gray-500"
                    : "text-gray-200"
                )}>
                  {step.label}
                </p>
                {step.attempt !== undefined && step.maxAttempts !== undefined && step.attempt > 1 && (
                  <span className="text-2xs text-warning-text bg-warning-muted/40 px-1.5 py-0.5 rounded-full">
                    attempt {step.attempt}/{step.maxAttempts}
                  </span>
                )}
              </div>

              {step.type && (
                <p className="t-mono mt-0.5">{step.type}</p>
              )}

              {step.durationMs != null && step.status === "completed" && (
                <p className="t-muted mt-0.5">{(step.durationMs / 1000).toFixed(1)}s</p>
              )}

              {step.error && step.status === "failed" && (
                <p className="text-xs text-danger-text mt-1 bg-danger-muted/20 rounded-md px-2 py-1 truncate-2">
                  {step.error}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
