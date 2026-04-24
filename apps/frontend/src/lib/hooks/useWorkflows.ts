"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { workflowsApi } from "@/lib/api/workflows";

export function useWorkflows(params: Parameters<typeof workflowsApi.list>[0] = {}) {
  return useQuery({
    queryKey: ["workflows", params],
    queryFn: () => workflowsApi.list(params),
  });
}

export function useWorkflow(id: string) {
  return useQuery({
    queryKey: ["workflows", id],
    queryFn: () => workflowsApi.get(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "pending" ? 3000 : false;
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
