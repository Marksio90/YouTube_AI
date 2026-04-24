"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { channelsApi } from "@/lib/api/channels";

export function useChannels(page = 1) {
  return useQuery({
    queryKey: ["channels", page],
    queryFn: () => channelsApi.list(page),
  });
}

export function useChannel(id: string) {
  return useQuery({
    queryKey: ["channels", id],
    queryFn: () => channelsApi.get(id),
    enabled: !!id,
  });
}

export function useCreateChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: channelsApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }),
  });
}

export function useUpdateChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof channelsApi.update>[1] }) =>
      channelsApi.update(id, data),
    onSuccess: (_d, { id }) => {
      qc.invalidateQueries({ queryKey: ["channels"] });
      qc.invalidateQueries({ queryKey: ["channels", id] });
    },
  });
}
