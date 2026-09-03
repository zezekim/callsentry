"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, clearToken, getToken } from "@/lib/api";

const NAV = [
  { href: "/overview", label: "Overview" },
  { href: "/calls", label: "Calls" },
  { href: "/appointments", label: "Appointments" },
  { href: "/kb", label: "Knowledge base" },
  { href: "/analytics", label: "Reports" },
  { href: "/settings", label: "Settings" },
];

export interface Session {
  id: string;
  email: string;
  role: string;
  business_id: string;
}

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session | null {
  return useContext(SessionContext);
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<Session | null>(null);

  // The showcase page and sign-in render without the authenticated frame.
  const isPublic = pathname === "/" || pathname === "/login";

  useEffect(() => {
    if (isPublic) {
      setReady(true);
      return;
    }
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api
      .get<Session>("/auth/me")
      .then(setSession)
      .catch(() => {
        /* the api client already redirects on 401 */
      })
      .finally(() => setReady(true));
  }, [isPublic, pathname, router]);

  if (isPublic) return <>{children}</>;
  if (!ready) return <p className="p-8 text-secondary">Loading…</p>;

  const nav = session?.role === "operator" ? [...NAV, { href: "/admin", label: "Administration" }] : NAV;

  function signOut() {
    clearToken();
    router.replace("/login");
  }

  return (
    <SessionContext.Provider value={session}>
      <div className="flex min-h-screen flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-0 focus:top-0 focus:z-20 focus:bg-focus focus:px-4 focus:py-2 focus:font-bold"
        >
          Skip to main content
        </a>

        <header className="border-b-[10px] border-brand bg-ink text-white">
          <div className="mx-auto flex max-w-page flex-wrap items-center justify-between gap-x-6 gap-y-2 px-6 py-3">
            <Link href="/overview" className="flex items-baseline gap-3 text-white no-underline">
              <span className="text-xl font-bold tracking-tight">CallSentry</span>
              <span className="text-sm text-[#b1b4b6]">Receptionist administration</span>
            </Link>
            <div className="flex items-center gap-4 text-sm">
              {session && (
                <span className="hidden sm:inline">
                  {session.email}
                  <span className="ml-2 text-[#b1b4b6]">({session.role})</span>
                </span>
              )}
              <button onClick={signOut} className="link text-white hover:text-white">
                Sign out
              </button>
            </div>
          </div>
        </header>

        <nav aria-label="Service" className="border-b border-border bg-white">
          <ul className="mx-auto flex max-w-page flex-wrap gap-x-6 px-6">
            {nav.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`-mb-px block border-b-4 py-3 text-base no-underline ${
                      active
                        ? "border-brand font-bold text-ink"
                        : "border-transparent text-link hover:border-border hover:text-link-hover"
                    }`}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <main id="main" className="mx-auto w-full max-w-page flex-1 px-6 py-8">
          {children}
        </main>

        <footer className="border-t border-border bg-canvas">
          <div className="mx-auto flex max-w-page flex-wrap items-center justify-between gap-4 px-6 py-6 text-sm text-secondary">
            <span>CallSentry · self-hosted voice receptionist</span>
            <span>
              Calls are recorded and transcribed under your retention policy. See{" "}
              <Link href="/settings/platform" className="link">
                data retention
              </Link>
              .
            </span>
          </div>
        </footer>
      </div>
    </SessionContext.Provider>
  );
}
