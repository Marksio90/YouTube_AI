import { cn } from "@/lib/utils/cn";

interface ProgressProps {
  value: number;   // 0–100
  className?: string;
  size?: "xs" | "sm" | "md";
  color?: "brand" | "success" | "warning" | "danger";
  showLabel?: boolean;
}

const heights = { xs: "h-1", sm: "h-1.5", md: "h-2" };

const colors = {
  brand:   "bg-brand-500",
  success: "bg-success",
  warning: "bg-warning",
  danger:  "bg-danger",
};

export function Progress({ value, className, size = "sm", color = "brand", showLabel }: ProgressProps) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className={cn("flex-1 rounded-full bg-gray-800 overflow-hidden", heights[size])}>
        <div
          className={cn("h-full rounded-full transition-all duration-500", colors[color])}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs tabular-nums text-gray-400 shrink-0 w-8 text-right">
          {Math.round(clamped)}%
        </span>
      )}
    </div>
  );
}

export function ScoreBar({ score, max = 10 }: { score: number; max?: number }) {
  const pct = (score / max) * 100;
  const color = pct >= 75 ? "success" : pct >= 50 ? "brand" : pct >= 30 ? "warning" : "danger";
  return (
    <div className="flex items-center gap-2">
      <Progress value={pct} size="xs" color={color} className="flex-1" />
      <span className="text-xs tabular-nums text-gray-400 w-6 text-right shrink-0">
        {score.toFixed(1)}
      </span>
    </div>
  );
}
