import type { ChannelAnalytics, AnalyticsSnapshot } from "@/lib/types";
import { apiClient } from "./client";

export const analyticsApi = {
  channel: (channelId: string, days = 30) =>
    apiClient.get<ChannelAnalytics>(`/analytics/channels/${channelId}?days=${days}`),

  publication: (publicationId: string, days = 30) =>
    apiClient.get<AnalyticsSnapshot[]>(`/analytics/publications/${publicationId}?days=${days}`),

  overview: (days = 30) =>
    apiClient.get<ChannelAnalytics[]>(`/analytics/overview?days=${days}`),
};
