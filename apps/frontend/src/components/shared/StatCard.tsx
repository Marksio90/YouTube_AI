import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils/cn";

interface StatCardProps {
  label: string;
  value: string;
  delta?: number;
  deltaLabel?: string;
  icon?: React.ReactNode;
  loading?: boolean;
}

export function StatCard({ label, value, delta, deltaLabel, icon, loading }: StatCardProps) {
  const trend = delta === undefined ? null : delta > 0 ? "up" : delta < 0 ? "down" : "flat";

  return (
    <div className="rounded-xl border border-gray-800 bg-surface-raised p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium uppercase tracking-wider text-gray-500">{label}</p>
        {icon && (
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gray-800 text-gray-400">
            {icon}
          </div>
        )}
      </div>
      {loading ? (
        <div className="h-8 w-28 animate-pulse rounded bg-gray-800 mb-1" />
      ) : (
        <p className="metric-value">{value}</p>
      )}
      {trend !== null && (
        <div className={cn("flex items-center gap-1 mt-1 text-xs",
          trend === "up" ? "text-success-text" : trend === "down" ? "text-danger-text" : "text-gray-500"
        )}>
          {trend === "up" ? <TrendingUp className="h-3 w-3" /> :
           trend === "down" ? <TrendingDown className="h-3 w-3" /> :
           <Minus className="h-3 w-3" />}
          <span>
            {delta !== undefined && delta > 0 ? "+" : ""}{delta?.toFixed(1)}%
            {deltaLabel && <span className="text-gray-600 ml-1">{deltaLabel}</span>}
          </span>
        </div>
      )}
    </div>
  );
}
