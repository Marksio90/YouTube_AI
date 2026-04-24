import type {
  ChannelRevenueOverview,
  PublicationRevenueOverview,
  ROISummary,
  RevenueStream,
  AffiliateLink,
} from "@/lib/types";
import { apiClient } from "./client";

export const monetizationApi = {
  // ── Channel revenue ────────────────────────────────────────────────────────
  channelOverview: (channelId: string, days = 30) =>
    apiClient.get<ChannelRevenueOverview>(
      `/monetization/channels/${channelId}/overview?days=${days}`
    ),

  channelRoi: (channelId: string, days = 30) =>
    apiClient.get<ROISummary>(
      `/monetization/channels/${channelId}/roi?days=${days}`
    ),

  channelStreams: (channelId: string, days = 30, source?: string) =>
    apiClient.get<RevenueStream[]>(
      `/monetization/channels/${channelId}/streams?days=${days}${source ? `&source=${source}` : ""}`
    ),

  upsertStream: (channelId: string, data: Record<string, unknown>) =>
    apiClient.post<RevenueStream>(
      `/monetization/channels/${channelId}/streams`,
      data
    ),

  // ── Publication revenue ────────────────────────────────────────────────────
  publicationOverview: (publicationId: string) =>
    apiClient.get<PublicationRevenueOverview>(
      `/monetization/publications/${publicationId}/overview`
    ),

  // ── Affiliate links ────────────────────────────────────────────────────────
  affiliateLinks: (channelId: string, activeOnly = true) =>
    apiClient.get<AffiliateLink[]>(
      `/monetization/channels/${channelId}/affiliate-links?active_only=${activeOnly}`
    ),

  createAffiliateLink: (channelId: string, data: Record<string, unknown>) =>
    apiClient.post<AffiliateLink>(
      `/monetization/channels/${channelId}/affiliate-links`,
      data
    ),

  updateAffiliateLink: (linkId: string, data: Record<string, unknown>) =>
    apiClient.patch<AffiliateLink>(`/monetization/affiliate-links/${linkId}`, data),

  recordClick: (linkId: string) =>
    apiClient.post<AffiliateLink>(`/monetization/affiliate-links/${linkId}/click`, {}),
};
