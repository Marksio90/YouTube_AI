"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { topicsApi } from "@/lib/api/topics";

export function useTopics(params: Parameters<typeof topicsApi.list>[0] = {}) {
  return useQuery({
    queryKey: ["topics", params],
    queryFn: () => topicsApi.list(params),
  });
}

export function useTopic(id: string) {
  return useQuery({
    queryKey: ["topics", id],
    queryFn: () => topicsApi.get(id),
    enabled: !!id,
  });
}

export function useCreateTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: topicsApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["topics"] }),
  });
}

export function useUpdateTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof topicsApi.update>[1] }) =>
      topicsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["topics"] }),
  });
}
