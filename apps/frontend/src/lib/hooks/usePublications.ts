"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { publicationsApi } from "@/lib/api/publications";

export function usePublications(params: Parameters<typeof publicationsApi.list>[0] = {}) {
  return useQuery({
    queryKey: ["publications", params],
    queryFn: () => publicationsApi.list(params),
  });
}

export function usePublication(id: string) {
  return useQuery({
    queryKey: ["publications", id],
    queryFn: () => publicationsApi.get(id),
    enabled: !!id,
  });
}

export function useUpdatePublication() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof publicationsApi.update>[1] }) =>
      publicationsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publications"] }),
  });
}
