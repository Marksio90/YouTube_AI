import type { AsyncTask, PaginatedResponse, Script } from "@ai-media-os/shared";
import { apiClient } from "./client";

export const scriptsApi = {
  list: (params: { page?: number; pageSize?: number; channelId?: string } = {}) => {
    const { page = 1, pageSize = 20, channelId } = params;
    const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (channelId) qs.set("channel_id", channelId);
    return apiClient.get<PaginatedResponse<Script>>(`/scripts?${qs}`);
  },

  get: (id: string) =>
    apiClient.get<Script>(`/scripts/${id}`),

  generate: (data: {
    channel_id: string;
    topic: string;
    tone: string;
    target_duration_seconds?: number;
    keywords?: string[];
    additional_context?: string;
  }) => apiClient.post<AsyncTask>("/scripts/generate", data),

  update: (id: string, data: Partial<Pick<Script, "title" | "hook" | "body" | "cta" | "keywords" | "status">>) =>
    apiClient.patch<Script>(`/scripts/${id}`, data),
};
