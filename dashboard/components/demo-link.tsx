"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setToken } from "@/lib/api";

/**
 * "View the dashboard" on the showcase. Signs the visitor in as the public
 * viewer account and goes straight to the overview; if the demo account is
 * not enabled it falls back to the sign-in page. Plain link without JS.
 */
export function DemoLink({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function open(event: React.MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const result = await api.post<{ access_token: string }>("/auth/demo");
      setToken(result.access_token);
      router.push("/overview");
    } catch {
      router.push("/login");
    } finally {
      setBusy(false);
    }
  }

  return (
    <a href="/login" onClick={open} className="link font-bold" aria-busy={busy}>
      {busy ? "Opening the dashboard…" : children}
    </a>
  );
}
