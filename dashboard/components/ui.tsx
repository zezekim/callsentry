"use client";

import Link from "next/link";
import type { ReactNode } from "react";

/* ------------------------------------------------------------------------ */
/* Page structure                                                           */
/* ------------------------------------------------------------------------ */

export function PageHeader({
  caption,
  title,
  lede,
  actions,
}: {
  caption?: string;
  title: string;
  lede?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
      <div>
        {caption && <span className="caption">{caption}</span>}
        <h1 className="h1">{title}</h1>
        {lede && <p className="mt-3 max-w-3xl text-secondary">{lede}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-3">{actions}</div>}
    </div>
  );
}

export function Card({
  title,
  description,
  actions,
  children,
  flush = false,
  className = "",
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-header">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {description && <p className="mt-0.5 text-sm text-secondary">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {flush ? children : <div className="card-body">{children}</div>}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="mt-1 text-xs text-secondary">{hint}</div>}
    </div>
  );
}

export function SummaryList({
  rows,
}: {
  rows: { key: string; value: ReactNode; action?: ReactNode }[];
}) {
  return (
    <dl className="summary-list">
      {rows.map((row) => (
        <div key={row.key} className="summary-row">
          <dt className="summary-key">{row.key}</dt>
          <dd className="summary-value">{row.value}</dd>
          {row.action && <dd className="text-right">{row.action}</dd>}
        </div>
      ))}
    </dl>
  );
}

export function Details({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="my-4 group">
      <summary className="cursor-pointer text-link underline underline-offset-[3px] hover:text-link-hover">
        {summary}
      </summary>
      <div className="mt-3 border-l-[5px] border-border pl-4 text-base">{children}</div>
    </details>
  );
}

/* ------------------------------------------------------------------------ */
/* Status                                                                   */
/* ------------------------------------------------------------------------ */

const TONES: Record<string, string> = {
  booked: "tag-green",
  answered: "tag-blue",
  escalated: "tag-orange",
  voicemail: "tag-turquoise",
  abandoned: "tag-red",
  positive: "tag-green",
  neutral: "tag-grey",
  negative: "tag-red",
  confirmed: "tag-green",
  cancelled: "tag-red",
  no_show: "tag-yellow",
  local: "tag-green",
  cloud: "tag-blue",
  mock: "tag-yellow",
  admin: "tag-blue",
  operator: "tag-purple",
  viewer: "tag-turquoise",
  healthy: "tag-green",
  unavailable: "tag-grey",
};

export function Tag({ value, tone }: { value: string | null | undefined; tone?: string }) {
  if (!value) return <span className="text-secondary">—</span>;
  return <span className={`tag ${tone ?? TONES[value] ?? "tag-grey"}`}>{value.replace(/_/g, " ")}</span>;
}

export function Notice({
  kind = "info",
  title,
  children,
}: {
  kind?: "info" | "success";
  title?: string;
  children: ReactNode;
}) {
  const heading = title ?? (kind === "success" ? "Success" : "Important");
  return (
    <div className={`banner ${kind === "success" ? "banner-success" : ""}`} role="status">
      <div className="banner-title">{heading}</div>
      <div className="banner-body">{children}</div>
    </div>
  );
}

export function ErrorSummary({ error, title = "There is a problem" }: { error: string | null; title?: string }) {
  if (!error) return null;
  return (
    <div className="error-summary" role="alert" aria-live="assertive">
      <h2 className="h3 mb-2">{title}</h2>
      <p className="text-base">{error}</p>
    </div>
  );
}

export function Inset({ children }: { children: ReactNode }) {
  return <div className="inset">{children}</div>;
}

export function WarningText({ children }: { children: ReactNode }) {
  return (
    <div className="warning-text">
      <span
        aria-hidden
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-lg font-bold text-white"
      >
        !
      </span>
      <div>
        <span className="sr-only">Warning: </span>
        {children}
      </div>
    </div>
  );
}

export function Empty({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="px-4 py-10 text-center">
      <p className="text-base">{message}</p>
      {hint && <p className="mt-1 text-sm text-secondary">{hint}</p>}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <p className="px-4 py-10 text-center text-base text-secondary" role="status">
      {label}…
    </p>
  );
}

/* ------------------------------------------------------------------------ */
/* Forms                                                                    */
/* ------------------------------------------------------------------------ */

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  className = "",
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`form-group ${error ? "form-group-error" : ""} ${className}`}>
      <label className="label" htmlFor={htmlFor}>
        {label}
      </label>
      {hint && <span className="hint">{hint}</span>}
      {error && <span className="error-msg">{error}</span>}
      {children}
    </div>
  );
}

export function ButtonLink({
  href,
  children,
  variant = "secondary",
  small = false,
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary" | "warning";
  small?: boolean;
}) {
  const cls = ["btn", variant === "secondary" && "btn-secondary", variant === "warning" && "btn-warning", small && "btn-sm"]
    .filter(Boolean)
    .join(" ");
  return (
    <Link href={href} className={cls}>
      {children}
    </Link>
  );
}

/* ------------------------------------------------------------------------ */
/* Formatting                                                               */
/* ------------------------------------------------------------------------ */

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
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    ...(timeZone ? { timeZone } : {}),
  });
}

export function dateOnly(iso: string, timeZone?: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    ...(timeZone ? { timeZone } : {}),
  });
}
