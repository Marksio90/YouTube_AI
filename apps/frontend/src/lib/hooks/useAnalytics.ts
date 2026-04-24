"use client";
import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "@/lib/api/analytics";

export function useChannelAnalytics(channelId: string, days = 30) {
  return useQuery({
    queryKey: ["analytics", "channel", channelId, days],
    queryFn: () => analyticsApi.channel(channelId, days),
    enabled: !!channelId,
    staleTime: 60_000,
  });
}

export function useOverviewAnalytics(days = 30) {
  return useQuery({
    queryKey: ["analytics", "overview", days],
    queryFn: () => analyticsApi.overview(days),
    staleTime: 60_000,
  });
}
