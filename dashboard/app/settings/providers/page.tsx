"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type ProviderSnapshot } from "@/lib/api";
import { Badge, ErrorNote, Panel, Spinner } from "@/components/ui";

const DESCRIPTIONS: Record<string, string> = {
  stt: "Speech to text — transcribes what the caller says",
  llm: "Language model — intent, answers, and summaries",
  tts: "Text to speech — the voice the caller hears",
  embeddings: "Vector embeddings — powers knowledge base search",
  telephony: "Phone network — the only component with no local option",
  calendar: "Availability and booking",
};

export default function ProvidersPage() {
  const [snapshot, setSnapshot] = useState<ProviderSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback((refresh = false) => {
    setRefreshing(refresh);
    api
      .get<ProviderSnapshot>(`/settings/providers${refresh ? "?refresh=true" : ""}`)
      .then(setSnapshot)
      .catch((e) => setError(e.message))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => load(), [load]);

  if (error) return <ErrorNote error={error} />;
  if (!snapshot) return <Spinner />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/settings" className="btn px-2 py-1 text-xs">
          ← Settings
        </Link>
        <h1 className="text-lg font-semibold text-slate-100">Provider health</h1>
        <button className="btn ml-auto px-2 py-1 text-xs" onClick={() => load(true)}>
          {refreshing ? "Probing…" : "Re-probe"}
        </button>
      </div>

      <div
        className={`rounded-md border px-4 py-3 text-sm ${
          snapshot.local_only
            ? "border-emerald-900 bg-emerald-950/40 text-emerald-300"
            : "border-sky-900 bg-sky-950/40 text-sky-300"
        }`}
      >
        {snapshot.local_only ? (
          <>
            <strong>Local-only mode.</strong> Cloud providers are disabled regardless of which
            API keys are configured. Every inference call runs on your hardware at zero cost.
          </>
        ) : (
          <>
            <strong>Cloud fallbacks enabled.</strong> If a local provider is unhealthy, the
            configured paid API takes over for that component and the cost is recorded per call.
          </>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {Object.entries(snapshot.components).map(([component, rows]) => {
          const serving = rows.find((r) => r.healthy);
          return (
            <Panel
              key={component}
              title={component.toUpperCase()}
              subtitle={DESCRIPTIONS[component]}
              actions={
                serving ? (
                  <span className="flex items-center gap-2 text-xs">
                    <span className="text-muted">serving:</span>
                    <span className="font-mono text-slate-200">{serving.provider}</span>
                    <Badge value={serving.tier} />
                  </span>
                ) : (
                  <span className="text-xs text-danger">no healthy provider</span>
                )
              }
            >
              <div className="divide-y divide-edge">
                {rows.map((row) => (
                  <div key={row.provider} className="flex items-center gap-3 px-4 py-2.5">
                    <span
                      className={`h-2 w-2 shrink-0 rounded-full ${
                        row.healthy ? "bg-emerald-500" : "bg-slate-700"
                      }`}
                      aria-label={row.healthy ? "healthy" : "unavailable"}
                    />
                    <span className="w-36 shrink-0 font-mono text-sm">{row.provider}</span>
                    <Badge value={row.tier} />
                    <span className="flex-1 truncate text-xs text-muted">{row.detail}</span>
                    <span className="shrink-0 font-mono text-xs">
                      {row.cost_per_unit === 0 ? (
                        <span className="text-accent">free</span>
                      ) : (
                        <span className="text-muted">
                          ${row.cost_per_unit}/{row.unit}
                        </span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
