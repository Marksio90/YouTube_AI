"use client";

import { apiClient, ApiClientError } from "@/lib/api/client";
import { clearSession, loadSession, saveSession } from "@/lib/auth/session";
import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useMemo, useState } from "react";

type LoginPayload = { email: string; password: string };
type LoginResponse = { access_token: string; refresh_token: string; token_type: string };

type AuthContextType = {
  ready: boolean;
  isAuthenticated: boolean;
  accessToken: string | null;
  login: (payload: LoginPayload) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    const { accessToken: storedAccess } = loadSession();
    if (storedAccess) {
      setAccessToken(storedAccess);
      apiClient.setToken(storedAccess);
    }
    setReady(true);
  }, []);

  const login = async ({ email, password }: LoginPayload) => {
    const result = await apiClient.post<LoginResponse>("/auth/login", { email, password });
    saveSession(result.access_token, result.refresh_token);
    setAccessToken(result.access_token);
    apiClient.setToken(result.access_token);
    router.push("/dashboard");
  };

  const logout = () => {
    clearSession();
    setAccessToken(null);
    apiClient.setToken(null);
    router.push("/login");
  };

  const value = useMemo<AuthContextType>(
    () => ({
      ready,
      isAuthenticated: Boolean(accessToken),
      accessToken,
      login,
      logout,
    }),
    [ready, accessToken]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function getAuthErrorMessage(err: unknown) {
  if (err instanceof ApiClientError) return err.error?.message || "Authentication failed";
  return "Authentication failed";
}
