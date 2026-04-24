"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { monetizationApi } from "@/lib/api/monetization";

// ── Channel overview ──────────────────────────────────────────────────────────

export function useChannelRevenue(channelId: string, days = 30) {
  return useQuery({
    queryKey: ["monetization", "overview", channelId, days],
    queryFn:  () => monetizationApi.channelOverview(channelId, days),
    enabled:  !!channelId,
    staleTime: 5 * 60_000,
  });
}

export function useChannelRoi(channelId: string, days = 30) {
  return useQuery({
    queryKey: ["monetization", "roi", channelId, days],
    queryFn:  () => monetizationApi.channelRoi(channelId, days),
    enabled:  !!channelId,
    staleTime: 5 * 60_000,
  });
}

export function useChannelStreams(
  channelId: string,
  days = 30,
  source?: string
) {
  return useQuery({
    queryKey: ["monetization", "streams", channelId, days, source],
    queryFn:  () => monetizationApi.channelStreams(channelId, days, source),
    enabled:  !!channelId,
    staleTime: 5 * 60_000,
  });
}

// ── Publication ───────────────────────────────────────────────────────────────

export function usePublicationRevenue(publicationId: string) {
  return useQuery({
    queryKey: ["monetization", "publication", publicationId],
    queryFn:  () => monetizationApi.publicationOverview(publicationId),
    enabled:  !!publicationId,
    staleTime: 5 * 60_000,
  });
}

// ── Affiliate links ───────────────────────────────────────────────────────────

export function useAffiliateLinks(channelId: string, activeOnly = true) {
  return useQuery({
    queryKey: ["monetization", "affiliate", channelId, activeOnly],
    queryFn:  () => monetizationApi.affiliateLinks(channelId, activeOnly),
    enabled:  !!channelId,
    staleTime: 60_000,
  });
}

export function useCreateAffiliateLink(channelId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      monetizationApi.createAffiliateLink(channelId, { ...data, channel_id: channelId }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["monetization", "affiliate", channelId] }),
  });
}

export function useUpdateAffiliateLink(channelId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      monetizationApi.updateAffiliateLink(id, data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["monetization", "affiliate", channelId] }),
  });
}
