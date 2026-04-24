import type { Topic, PaginatedResponse } from "@/lib/types";
import { apiClient } from "./client";

export const topicsApi = {
  list: (params: { page?: number; pageSize?: number; channelId?: string; status?: string } = {}) => {
    const { page = 1, pageSize = 20, channelId, status } = params;
    const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (channelId) qs.set("channel_id", channelId);
    if (status) qs.set("status", status);
    return apiClient.get<PaginatedResponse<Topic>>(`/topics?${qs}`);
  },

  get: (id: string) => apiClient.get<Topic>(`/topics/${id}`),

  create: (data: { channel_id: string; title: string; description?: string; keywords?: string[]; source?: string }) =>
    apiClient.post<Topic>("/topics", data),

  update: (id: string, data: Partial<Pick<Topic, "title" | "description" | "keywords" | "status">>) =>
    apiClient.patch<Topic>(`/topics/${id}`, data),

  delete: (id: string) => apiClient.delete<void>(`/topics/${id}`),
};
