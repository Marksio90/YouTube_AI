import { cn } from "@/lib/utils/cn";
import { Skeleton } from "./Skeleton";

interface ChartContainerProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  height?: number;
  children: React.ReactNode;
  className?: string;
}

export function ChartContainer({
  title,
  description,
  actions,
  loading,
  empty,
  emptyMessage = "No data for this period",
  height = 220,
  children,
  className,
}: ChartContainerProps) {
  return (
    <div className={cn("card p-5", className)}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-5">
        <div>
          <p className="t-section">{title}</p>
          {description && <p className="t-muted mt-0.5">{description}</p>}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>

      {/* Body */}
      {loading ? (
        <div style={{ height }} className="flex flex-col gap-2 justify-end">
          <div className="flex items-end gap-1 h-full">
            {Array.from({ length: 12 }).map((_, i) => (
              <Skeleton
                key={i}
                className="flex-1 rounded-sm"
                style={{ height: `${30 + Math.random() * 60}%` } as React.CSSProperties}
              />
            ))}
          </div>
        </div>
      ) : empty ? (
        <div
          style={{ height }}
          className="flex items-center justify-center text-sm text-gray-600"
        >
          {emptyMessage}
        </div>
      ) : (
        <div style={{ height }}>{children}</div>
      )}
    </div>
  );
}
