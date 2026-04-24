"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { complianceApi } from "@/lib/api/compliance";

export function useComplianceChecks(channelId: string, params?: { script_id?: string; status?: string }) {
  return useQuery({
    queryKey: ["compliance", "list", channelId, params],
    queryFn:  () => complianceApi.listChecks(channelId, params),
    enabled:  !!channelId,
    staleTime: 30_000,
  });
}

export function useComplianceCheck(checkId: string) {
  return useQuery({
    queryKey: ["compliance", "check", checkId],
    queryFn:  () => complianceApi.getCheck(checkId),
    enabled:  !!checkId,
    staleTime: 15_000,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "pending" ? 5_000 : false;
    },
  });
}

export function useLatestScriptCheck(scriptId: string) {
  return useQuery({
    queryKey: ["compliance", "script-latest", scriptId],
    queryFn:  () => complianceApi.latestForScript(scriptId),
    enabled:  !!scriptId,
    staleTime: 30_000,
  });
}

export function useRunComplianceCheck(channelId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { script_id?: string; publication_id?: string; mode?: string }) =>
      complianceApi.runCheck(channelId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["compliance", "list", channelId] });
    },
  });
}

export function useOverrideCheck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      checkId,
      override_by,
      override_reason,
    }: {
      checkId: string;
      override_by: string;
      override_reason: string;
    }) => complianceApi.override(checkId, { override_by, override_reason }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["compliance", "check", vars.checkId] });
    },
  });
}

export function useDismissFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      flagId,
      dismissed_by,
      reason,
    }: {
      flagId: string;
      dismissed_by: string;
      reason?: string;
    }) => complianceApi.dismissFlag(flagId, { dismissed_by, reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["compliance"] });
    },
  });
}
