"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

// ── Performance Scores ────────────────────────────────────────────────────────

export function useChannelScore(channelId: string, period = 28) {
  return useQuery({
    queryKey: ["scores", "channel", channelId, period],
    queryFn: () => analyticsApi.channelScore(channelId, period),
    enabled: !!channelId,
    staleTime: 5 * 60_000,
  });
}

export function usePublicationScore(publicationId: string, period = 28) {
  return useQuery({
    queryKey: ["scores", "publication", publicationId, period],
    queryFn: () => analyticsApi.publicationScore(publicationId, period),
    enabled: !!publicationId,
    staleTime: 5 * 60_000,
  });
}

// ── Rankings ──────────────────────────────────────────────────────────────────

export function useTopicRanking(period = 28) {
  return useQuery({
    queryKey: ["rankings", "topics", period],
    queryFn: () => analyticsApi.topicRanking(period),
    staleTime: 5 * 60_000,
  });
}

export function useChannelRanking(period = 28) {
  return useQuery({
    queryKey: ["rankings", "channels", period],
    queryFn: () => analyticsApi.channelRanking(period),
    staleTime: 5 * 60_000,
  });
}

// ── Recommendations ───────────────────────────────────────────────────────────

export function useRecommendations(
  channelId: string,
  status = "pending",
  limit = 50
) {
  return useQuery({
    queryKey: ["recommendations", channelId, status, limit],
    queryFn: () => analyticsApi.recommendations(channelId, status, limit),
    enabled: !!channelId,
    staleTime: 60_000,
  });
}

export function useGenerateRecommendations(channelId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (period?: number) =>
      analyticsApi.generateRecommendations(channelId, period),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recommendations", channelId] });
    },
  });
}

export function useRecommendationAction(channelId: string) {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["recommendations", channelId] });

  const apply = useMutation({
    mutationFn: (recId: string) => analyticsApi.applyRecommendation(recId),
    onSuccess: invalidate,
  });

  const dismiss = useMutation({
    mutationFn: (recId: string) => analyticsApi.dismissRecommendation(recId),
    onSuccess: invalidate,
  });

  const snooze = useMutation({
    mutationFn: (recId: string) => analyticsApi.snoozeRecommendation(recId),
    onSuccess: invalidate,
  });

  return { apply, dismiss, snooze };
}
