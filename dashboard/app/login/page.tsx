"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setToken } from "@/lib/api";
import { ErrorSummary, Field } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await api.post<{ access_token: string }>("/auth/login", { email, password });
      setToken(result.access_token);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b-[10px] border-brand bg-ink text-white">
        <div className="mx-auto flex max-w-page items-baseline gap-3 px-6 py-3">
          <span className="text-xl font-bold tracking-tight">CallSentry</span>
          <span className="text-sm text-[#b1b4b6]">Receptionist administration</span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-page flex-1 px-6 py-10">
        <div className="max-w-md">
          <h1 className="h1 mb-6">Sign in</h1>
          <ErrorSummary error={error} />
          <form onSubmit={submit} noValidate>
            <Field label="Email address" htmlFor="email">
              <input
                id="email"
                type="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                spellCheck={false}
                required
              />
            </Field>
            <Field label="Password" htmlFor="password">
              <input
                id="password"
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </Field>
            <button type="submit" className="btn" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="inset mt-10 text-sm">
            This service is for authorised staff of the business it serves. Access is logged.
            If you have lost your password, ask an administrator to reset it from Settings.
          </div>
        </div>
      </main>

      <footer className="border-t border-border bg-canvas">
        <div className="mx-auto max-w-page px-6 py-6 text-sm text-secondary">
          CallSentry · self-hosted voice receptionist
        </div>
      </footer>
    </div>
  );
}
