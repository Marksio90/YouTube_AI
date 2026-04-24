import type {
  ChannelAnalytics,
  AnalyticsSnapshot,
  PerformanceScore,
  TopicRankingResponse,
  ChannelRankingResponse,
  Recommendation,
} from "@/lib/types";
import { apiClient } from "./client";

export const analyticsApi = {
  channel: (channelId: string, days = 30) =>
    apiClient.get<ChannelAnalytics>(`/analytics/channels/${channelId}?days=${days}`),

  publication: (publicationId: string, days = 30) =>
    apiClient.get<AnalyticsSnapshot[]>(`/analytics/publications/${publicationId}?days=${days}`),

  overview: (days = 30) =>
    apiClient.get<ChannelAnalytics[]>(`/analytics/overview?days=${days}`),

  // ── Scores ──────────────────────────────────────────────────────────────────

  channelScore: (channelId: string, period = 28) =>
    apiClient.get<PerformanceScore>(`/analytics/scores/channels/${channelId}?period=${period}`),

  publicationScore: (publicationId: string, period = 28) =>
    apiClient.get<PerformanceScore>(`/analytics/scores/publications/${publicationId}?period=${period}`),

  // ── Rankings ─────────────────────────────────────────────────────────────────

  topicRanking: (period = 28) =>
    apiClient.get<TopicRankingResponse>(`/analytics/rankings/topics?period=${period}`),

  channelRanking: (period = 28) =>
    apiClient.get<ChannelRankingResponse>(`/analytics/rankings/channels?period=${period}`),

  // ── Recommendations ──────────────────────────────────────────────────────────

  recommendations: (channelId: string, status = "pending", limit = 50) =>
    apiClient.get<Recommendation[]>(
      `/analytics/recommendations/${channelId}?status=${status}&limit=${limit}`
    ),

  generateRecommendations: (channelId: string, period = 28) =>
    apiClient.post<Recommendation[]>(
      `/analytics/recommendations/${channelId}/generate-sync?period=${period}`,
      {}
    ),

  applyRecommendation: (recId: string) =>
    apiClient.post<Recommendation>(`/analytics/recommendations/action/${recId}/apply`, {}),

  dismissRecommendation: (recId: string) =>
    apiClient.post<Recommendation>(`/analytics/recommendations/action/${recId}/dismiss`, {}),

  snoozeRecommendation: (recId: string) =>
    apiClient.post<Recommendation>(`/analytics/recommendations/action/${recId}/snooze`, {}),
};
