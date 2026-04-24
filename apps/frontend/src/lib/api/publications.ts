import type { Publication, PaginatedResponse } from "@/lib/types";
import { apiClient } from "./client";

export const publicationsApi = {
  list: (params: { page?: number; pageSize?: number; channelId?: string; status?: string } = {}) => {
    const { page = 1, pageSize = 20, channelId, status } = params;
    const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (channelId) qs.set("channel_id", channelId);
    if (status) qs.set("status", status);
    return apiClient.get<PaginatedResponse<Publication>>(`/publications?${qs}`);
  },

  get: (id: string) => apiClient.get<Publication>(`/publications/${id}`),

  update: (id: string, data: Partial<Pick<Publication, "title" | "description" | "tags" | "status" | "scheduled_at">>) =>
    apiClient.patch<Publication>(`/publications/${id}`, data),
};
