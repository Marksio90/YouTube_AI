import { formatDistanceToNow, format as fnsFormat } from "date-fns";

export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

export function formatViews(n: number): string {
  return formatNumber(n);
}

export function formatRevenue(usd: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: 0, maximumFractionDigits: 2,
  }).format(usd);
}

export function formatPercent(n: number, decimals = 1): string {
  return `${n.toFixed(decimals)}%`;
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function formatRelative(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true });
}

export function formatDate(date: string | Date, fmt = "MMM d, yyyy"): string {
  return fnsFormat(new Date(date), fmt);
}

export function formatShortDate(date: string | Date): string {
  return fnsFormat(new Date(date), "MMM d");
}

export function formatScore(score: number): string {
  return score.toFixed(1);
}

/** Truncate a UUID to 8 chars for display */
export function shortId(id: string): string {
  return id.slice(0, 8);
}
