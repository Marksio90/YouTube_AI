"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { workflowsApi } from "@/lib/api/workflows";

export function useWorkflows(params: Parameters<typeof workflowsApi.list>[0] = {}) {
  return useQuery({
    queryKey: ["workflows", params],
    queryFn: () => workflowsApi.list(params),
  });
}

const MAX_POLL_MS = 30 * 60 * 1000;

export function useWorkflow(id: string) {
  return useQuery({
    queryKey: ["workflows", id],
    queryFn: () => workflowsApi.get(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status !== "running" && status !== "pending") return false;
      const age = Date.now() - (query.state.dataUpdatedAt ?? Date.now());
      if (age > MAX_POLL_MS) return false;
      return 3000;
    },
  });
}

export function useWorkflowAudit(id: string) {
  return useQuery({
    queryKey: ["workflows", id, "audit"],
    queryFn: () => workflowsApi.audit(id),
    enabled: !!id,
  });
}

export function useTriggerWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: workflowsApi.trigger,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });
}

export function useWorkflowAction(runId: string) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["workflows", runId] });
    qc.invalidateQueries({ queryKey: ["workflows"] });
  };

  const pause  = useMutation({ mutationFn: () => workflowsApi.pause(runId),  onSuccess: invalidate });
  const resume = useMutation({ mutationFn: () => workflowsApi.resume(runId), onSuccess: invalidate });
  const cancel = useMutation({ mutationFn: () => workflowsApi.cancel(runId), onSuccess: invalidate });
  const retry  = useMutation({ mutationFn: () => workflowsApi.retry(runId),  onSuccess: invalidate });

  return { pause, resume, cancel, retry };
}
