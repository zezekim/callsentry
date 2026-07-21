"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, clearToken, getToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/calls", label: "Calls" },
  { href: "/appointments", label: "Appointments" },
  { href: "/kb", label: "Knowledge Base" },
  { href: "/analytics", label: "Analytics" },
  { href: "/settings", label: "Settings" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState<string>("");
  const [role, setRole] = useState<string>("");

  const isLogin = pathname === "/login";

  useEffect(() => {
    if (isLogin) {
      setReady(true);
      return;
    }
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api
      .get<{ email: string; role: string }>("/auth/me")
      .then((me) => {
        setEmail(me.email);
        setRole(me.role);
      })
      .catch(() => {
        /* the api client already redirects on 401 */
      })
      .finally(() => setReady(true));
  }, [isLogin, pathname, router]);

  if (isLogin) return <>{children}</>;
  if (!ready) return <div className="p-8 text-sm text-muted">Loading…</div>;

  const nav = role === "operator" ? [...NAV, { href: "/admin", label: "Admin" }] : NAV;

  function signOut() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-edge bg-ink/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-lg">📞</span>
            <span className="font-semibold tracking-tight text-slate-100">CallSentry</span>
          </Link>

          <nav className="flex flex-wrap gap-1 text-sm">
            {nav.map((item) => {
              const active =
                item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-md px-2.5 py-1.5 transition ${
                    active
                      ? "bg-slate-800 text-slate-100"
                      : "text-muted hover:bg-slate-900 hover:text-slate-200"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3 text-xs text-muted">
            <span className="hidden sm:inline">{email}</span>
            <button onClick={signOut} className="btn px-2 py-1 text-xs">
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
