"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";

interface StatCard {
  label: string;
  value: string;
  delta?: string;
  positive?: boolean;
}

// Placeholder stats — will be replaced with real analytics endpoint
const PLACEHOLDER: StatCard[] = [
  { label: "Total Views", value: "—", delta: "+0%", positive: true },
  { label: "Revenue (MTD)", value: "—", delta: "+0%", positive: true },
  { label: "Active Pipelines", value: "—" },
  { label: "Published Videos", value: "—" },
];

export function StatsGrid() {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {PLACEHOLDER.map((stat) => (
        <div key={stat.label} className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <p className="text-xs text-gray-400 uppercase tracking-wider">{stat.label}</p>
          <p className="mt-2 text-2xl font-bold tabular-nums">{stat.value}</p>
          {stat.delta && (
            <p className={`mt-1 text-xs ${stat.positive ? "text-green-400" : "text-red-400"}`}>
              {stat.delta} vs last period
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
