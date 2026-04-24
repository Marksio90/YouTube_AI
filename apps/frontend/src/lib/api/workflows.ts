import type { WorkflowRun, WorkflowJob, WorkflowAuditEvent, PaginatedResponse } from "@/lib/types";
import { apiClient } from "./client";

export const workflowsApi = {
  list: (params: { page?: number; pageSize?: number; status?: string; channelId?: string } = {}) => {
    const { page = 1, pageSize = 20, status, channelId } = params;
    const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) qs.set("status", status);
    if (channelId) qs.set("channel_id", channelId);
    return apiClient.get<PaginatedResponse<WorkflowRun>>(`/workflows?${qs}`);
  },

  get: (id: string) => apiClient.get<WorkflowRun>(`/workflows/${id}`),

  trigger: (data: { channel_id?: string; topic_id?: string; pipeline_name?: string; context?: Record<string, unknown> }) =>
    apiClient.post<WorkflowRun>("/workflows", data),

  audit: (id: string) => apiClient.get<WorkflowAuditEvent[]>(`/workflows/${id}/audit`),

  pause:   (id: string) => apiClient.post<void>(`/workflows/${id}/pause`, {}),
  resume:  (id: string) => apiClient.post<void>(`/workflows/${id}/resume`, {}),
  cancel:  (id: string) => apiClient.post<void>(`/workflows/${id}/cancel`, {}),
  retry:   (id: string) => apiClient.post<void>(`/workflows/${id}/retry`, {}),

  jobs: (id: string) => apiClient.get<WorkflowJob[]>(`/workflows/${id}/jobs`),

  skipJob:   (runId: string, stepId: string) =>
    apiClient.post<void>(`/workflows/${runId}/jobs/${stepId}/skip`, {}),

  retryJob:  (runId: string, stepId: string) =>
    apiClient.post<void>(`/workflows/${runId}/jobs/${stepId}/retry`, {}),

  injectResult: (runId: string, stepId: string, result: Record<string, unknown>, actor: string) =>
    apiClient.post<void>(`/workflows/${runId}/jobs/${stepId}/inject`, { result, actor }),
};
