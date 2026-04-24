import { cn } from "@/lib/utils/cn";

type Variant = "default" | "success" | "warning" | "danger" | "info" | "purple" | "outline";

const variants: Record<Variant, string> = {
  default:  "bg-gray-800 text-gray-300",
  success:  "bg-success-muted text-success-text",
  warning:  "bg-warning-muted text-warning-text",
  danger:   "bg-danger-muted  text-danger-text",
  info:     "bg-info-muted    text-info-text",
  purple:   "bg-purple-muted  text-purple-text",
  outline:  "border border-gray-700 text-gray-400 bg-transparent",
};

interface BadgeProps {
  variant?: Variant;
  dot?: boolean;
  className?: string;
  children: React.ReactNode;
}

const dotColor: Record<Variant, string> = {
  default: "bg-gray-400",
  success: "bg-success",
  warning: "bg-warning",
  danger:  "bg-danger",
  info:    "bg-info",
  purple:  "bg-purple",
  outline: "bg-gray-400",
};

export function Badge({ variant = "default", dot, className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        variants[variant],
        className
      )}
    >
      {dot && (
        <span className={cn("h-1.5 w-1.5 rounded-full flex-shrink-0 animate-pulse-slow", dotColor[variant])} />
      )}
      {children}
    </span>
  );
}

// Status-aware badge for common entity statuses
const STATUS_MAP: Record<string, Variant> = {
  // Run statuses
  running:   "info",
  completed: "success",
  failed:    "danger",
  paused:    "warning",
  cancelled: "outline",
  pending:   "outline",
  // Job statuses
  scheduled: "info",
  retrying:  "warning",
  skipped:   "purple",
  // Content statuses
  active:    "success",
  approved:  "success",
  published: "success",
  review:    "warning",
  draft:     "outline",
  rejected:  "danger",
  archived:  "outline",
  briefed:   "info",
  researching: "info",
  new:       "outline",
  inactive:  "outline",
  suspended: "danger",
  rendering: "info",
  scheduled_pub: "warning",
};

export function StatusBadge({ status, dot = true }: { status: string; dot?: boolean }) {
  const variant = STATUS_MAP[status] ?? "default";
  const label = status.replace(/_/g, " ");
  return (
    <Badge variant={variant} dot={dot} className="capitalize">
      {label}
    </Badge>
  );
}
