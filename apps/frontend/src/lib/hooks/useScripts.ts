"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { scriptsApi } from "@/lib/api/scripts";

export function useScripts(params: Parameters<typeof scriptsApi.list>[0] = {}) {
  return useQuery({
    queryKey: ["scripts", params],
    queryFn: () => scriptsApi.list(params),
  });
}

export function useScript(id: string) {
  return useQuery({
    queryKey: ["scripts", id],
    queryFn: () => scriptsApi.get(id),
    enabled: !!id,
  });
}

export function useGenerateScript() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: scriptsApi.generate,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scripts"] }),
  });
}

export function useUpdateScript() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof scriptsApi.update>[1] }) =>
      scriptsApi.update(id, data),
    onSuccess: (_d, { id }) => {
      qc.invalidateQueries({ queryKey: ["scripts"] });
      qc.invalidateQueries({ queryKey: ["scripts", id] });
    },
  });
}
