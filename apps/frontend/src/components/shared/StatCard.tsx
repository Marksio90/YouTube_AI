import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { Skeleton } from "@/components/ui/Skeleton";

interface StatCardProps {
  label: string;
  value: string;
  delta?: number;
  deltaLabel?: string;
  icon?: React.ReactNode;
  loading?: boolean;
  className?: string;
}

export function StatCard({
  label,
  value,
  delta,
  deltaLabel,
  icon,
  loading,
  className,
}: StatCardProps) {
  const trend =
    delta === undefined ? null : delta > 0 ? "up" : delta < 0 ? "down" : "flat";

  return (
    <div className={cn("card p-5", className)}>
      {/* Label row */}
      <div className="flex items-center justify-between mb-3">
        <p className="t-label">{label}</p>
        {icon && (
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gray-800 text-gray-400">
            {icon}
          </span>
        )}
      </div>

      {/* Value */}
      {loading ? (
        <>
          <Skeleton className="h-8 w-28 mb-1.5" />
          <Skeleton className="h-3 w-16" />
        </>
      ) : (
        <>
          <p className="t-metric">{value}</p>

          {trend !== null && (
            <div
              className={cn(
                "flex items-center gap-1 mt-1.5 text-xs font-medium",
                trend === "up"   ? "text-success-text" :
                trend === "down" ? "text-danger-text"  : "text-gray-500"
              )}
            >
              {trend === "up"   ? <TrendingUp   className="h-3 w-3" /> :
               trend === "down" ? <TrendingDown className="h-3 w-3" /> :
                                  <Minus        className="h-3 w-3" />}
              <span>
                {delta !== undefined && delta > 0 ? "+" : ""}
                {delta?.toFixed(1)}%
                {deltaLabel && (
                  <span className="text-gray-600 font-normal ml-1">{deltaLabel}</span>
                )}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
