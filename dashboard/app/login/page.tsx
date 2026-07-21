"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setToken } from "@/lib/api";
import { ErrorNote } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("demo@callsentry.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await api.post<{ access_token: string }>("/auth/login", {
        email,
        password,
      });
      setToken(result.access_token);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="panel w-full max-w-sm p-6">
        <div className="mb-6 text-center">
          <div className="text-3xl">📞</div>
          <h1 className="mt-2 text-lg font-semibold text-slate-100">CallSentry</h1>
          <p className="mt-1 text-xs text-muted">Every call answered. Nothing slips through.</p>
        </div>

        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          <ErrorNote error={error} />

          <button type="submit" className="btn btn-primary w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </div>

        <p className="mt-6 text-center text-xs text-slate-600">
          Seeded demo login: demo@callsentry.local / changeme
        </p>
      </form>
    </div>
  );
}
