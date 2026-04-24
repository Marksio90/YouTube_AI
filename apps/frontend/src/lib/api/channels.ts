import type { Channel, PaginatedResponse } from "@/lib/types";
import { apiClient } from "./client";

export const channelsApi = {
  list: (page = 1, pageSize = 20) =>
    apiClient.get<PaginatedResponse<Channel>>(`/channels?page=${page}&page_size=${pageSize}`),

  get: (id: string) =>
    apiClient.get<Channel>(`/channels/${id}`),

  create: (data: { name: string; niche: string; handle?: string }) =>
    apiClient.post<Channel>("/channels", data),

  update: (id: string, data: Partial<{ name: string; niche: string; handle: string }>) =>
    apiClient.patch<Channel>(`/channels/${id}`, data),

  delete: (id: string) =>
    apiClient.delete<void>(`/channels/${id}`),
};
