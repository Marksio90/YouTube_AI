"use client";

import { apiClient, ApiClientError } from "@/lib/api/client";
import { clearSession, loadSession, saveSession } from "@/lib/auth/session";
import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useMemo, useState } from "react";

type LoginPayload = { email: string; password: string };

type AuthContextType = {
  ready: boolean;
  isAuthenticated: boolean;
  accessToken: null;
  login: (payload: LoginPayload) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(loadSession().hasSession);
  const router = useRouter();

  const fetchSession = async () => {
    await apiClient.get("/auth/me", { skipAuthRefresh: true });
    saveSession();
    setIsAuthenticated(true);
  };

  useEffect(() => {
    const checkSession = async () => {
      try {
        await fetchSession();
      } catch {
        clearSession();
        setIsAuthenticated(false);
      } finally {
        setReady(true);
      }
    };

    void checkSession();
  }, []);

  const login = async ({ email, password }: LoginPayload) => {
    await apiClient.post("/auth/login", { email, password }, { skipAuthRefresh: true });
    await fetchSession();
    router.push("/dashboard");
  };

  const logout = async () => {
    try {
      await apiClient.post("/auth/logout", undefined, { skipAuthRefresh: true });
    } finally {
      clearSession();
      setIsAuthenticated(false);
      router.push("/login");
    }
  };

  const value = useMemo<AuthContextType>(
    () => ({
      ready,
      isAuthenticated,
      accessToken: null,
      login,
      logout,
    }),
    [ready, isAuthenticated]
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
