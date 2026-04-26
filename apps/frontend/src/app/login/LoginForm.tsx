"use client";

import { getAuthErrorMessage, useAuth } from "@/components/auth/AuthContext";
import { Button } from "@/components/ui/Button";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

export default function LoginForm() {
  const { login, isAuthenticated } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const next = useSearchParams().get("next") || "/dashboard";
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated) router.replace(next);
  }, [isAuthenticated, next, router]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login({ email, password });
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="w-full max-w-md space-y-4 bg-gray-900 border border-gray-800 rounded-xl p-6">
      <h1 className="text-2xl font-semibold text-white">Login</h1>
      <p className="text-sm text-gray-400">Sign in to your AI Media OS workspace.</p>

      <label className="block text-sm text-gray-300">
        Email
        <input
          className="mt-1 w-full rounded-lg bg-gray-950 border border-gray-700 px-3 py-2 text-white"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          type="email"
          required
        />
      </label>

      <label className="block text-sm text-gray-300">
        Password
        <input
          className="mt-1 w-full rounded-lg bg-gray-950 border border-gray-700 px-3 py-2 text-white"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          required
        />
      </label>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <Button type="submit" className="w-full" disabled={loading}>
        {loading ? "Signing in..." : "Sign in"}
      </Button>
    </form>
  );
}
