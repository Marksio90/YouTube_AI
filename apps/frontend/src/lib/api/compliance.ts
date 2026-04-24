import type {
  ComplianceCheck,
  ComplianceCheckDetail,
  ComplianceSummary,
  RiskFlag,
} from "@/lib/types";
import { apiClient } from "./client";

export const complianceApi = {
  runCheck: (
    channelId: string,
    data: { script_id?: string; publication_id?: string; mode?: string }
  ) =>
    apiClient.post<ComplianceCheck>(
      `/compliance/channels/${channelId}/checks`,
      data
    ),

  getCheck: (checkId: string) =>
    apiClient.get<ComplianceCheckDetail>(`/compliance/checks/${checkId}`),

  listChecks: (channelId: string, params?: { script_id?: string; status?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.script_id) q.set("script_id", params.script_id);
    if (params?.status)    q.set("status", params.status);
    if (params?.limit)     q.set("limit", String(params.limit));
    return apiClient.get<ComplianceSummary[]>(
      `/compliance/channels/${channelId}/checks${q.toString() ? `?${q}` : ""}`
    );
  },

  latestForScript: (scriptId: string) =>
    apiClient.get<ComplianceCheck | null>(`/compliance/scripts/${scriptId}/latest-check`),

  override: (checkId: string, data: { override_by: string; override_reason: string }) =>
    apiClient.post<ComplianceCheck>(`/compliance/checks/${checkId}/override`, data),

  dismissFlag: (flagId: string, data: { dismissed_by: string; reason?: string }) =>
    apiClient.post<RiskFlag>(`/compliance/flags/${flagId}/dismiss`, data),
};
