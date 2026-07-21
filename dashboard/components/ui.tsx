"use client";

import type { ReactNode } from "react";

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-slate-100">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass = {
    default: "text-slate-100",
    good: "text-accent",
    warn: "text-warn",
    bad: "text-danger",
  }[tone];

  return (
    <div className="panel px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 font-mono text-2xl ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

const TONES: Record<string, string> = {
  booked: "bg-emerald-950 text-emerald-300",
  answered: "bg-slate-800 text-slate-300",
  escalated: "bg-amber-950 text-amber-300",
  voicemail: "bg-sky-950 text-sky-300",
  abandoned: "bg-red-950 text-red-300",
  positive: "bg-emerald-950 text-emerald-300",
  neutral: "bg-slate-800 text-slate-300",
  negative: "bg-red-950 text-red-300",
  confirmed: "bg-emerald-950 text-emerald-300",
  cancelled: "bg-red-950 text-red-300",
  no_show: "bg-amber-950 text-amber-300",
  local: "bg-emerald-950 text-emerald-300",
  cloud: "bg-sky-950 text-sky-300",
  mock: "bg-amber-950 text-amber-300",
};

export function Badge({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-muted">—</span>;
  return (
    <span className={`chip ${TONES[value] ?? "bg-slate-800 text-slate-300"}`}>
      {value.replace(/_/g, " ")}
    </span>
  );
}

export function Empty({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="text-sm text-muted">{message}</p>
      {hint && <p className="mt-1 text-xs text-slate-600">{hint}</p>}
    </div>
  );
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="rounded-md border border-red-900 bg-red-950/40 px-3 py-2 text-sm text-red-300">
      {error}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <div className="px-4 py-12 text-center text-sm text-muted">{label}…</div>;
}

export function money(value: number): string {
  // Sub-cent amounts are the whole point of the cost tracker; don't round
  // them away to "$0.00".
  if (value === 0) return "$0.00";
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

export function duration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function when(iso: string, timeZone?: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    ...(timeZone ? { timeZone } : {}),
  });
}
