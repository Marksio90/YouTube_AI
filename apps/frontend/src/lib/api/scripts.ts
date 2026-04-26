import type { PaginatedResponse, Script } from "@/lib/types";
import type { components } from "@/lib/contracts/openapi";
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

  generate: (data: components["schemas"]["ScriptGenerateRequest"]) =>
    apiClient.post<components["schemas"]["TaskResponse"]>("/scripts/generate", data),

  update: (id: string, data: Partial<Pick<Script, "title" | "hook" | "body" | "cta" | "keywords" | "status">>) =>
    apiClient.patch<Script>(`/scripts/${id}`, data),
};
