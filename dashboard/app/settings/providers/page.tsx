"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type ProviderSnapshot } from "@/lib/api";
import { Card, ErrorSummary, Inset, Spinner, Tag } from "@/components/ui";

const DESCRIPTIONS: Record<string, string> = {
  stt: "Speech to text. Transcribes what the caller says.",
  llm: "Language model. Understands intent, answers, and writes summaries.",
  tts: "Text to speech. The voice the caller hears.",
  embeddings: "Vector embeddings. Powers knowledge base search.",
  telephony: "Phone network. The only component with no local option.",
  calendar: "Availability and booking.",
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

  if (error) return <ErrorSummary error={error} />;
  if (!snapshot) return <Spinner />;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h2 className="h2">Provider status</h2>
        <button className="btn btn-secondary btn-sm" onClick={() => load(true)} disabled={refreshing}>
          {refreshing ? "Checking…" : "Check again"}
        </button>
      </div>

      <Inset>
        {snapshot.local_only ? (
          <>
            <strong>Local-only mode is on.</strong> Cloud providers are disabled whatever keys are configured, and every
            inference call runs on your own hardware at no cost.
          </>
        ) : (
          <>
            <strong>Cloud fallbacks are enabled.</strong> If a local provider is unhealthy, the configured paid API takes
            over for that component and the cost is recorded against the call.
          </>
        )}{" "}
        Keys and URLs are set under{" "}
        <Link href="/settings/platform" className="link">
          Platform configuration
        </Link>
        .
      </Inset>

      <div className="space-y-6">
        {Object.entries(snapshot.components).map(([component, rows]) => {
          const serving = rows.find((r) => r.healthy);
          return (
            <Card
              key={component}
              title={component.toUpperCase()}
              description={DESCRIPTIONS[component]}
              flush
              actions={
                serving ? (
                  <span className="text-sm">
                    Serving: <span className="kv">{serving.provider}</span> <Tag value={serving.tier} />
                  </span>
                ) : (
                  <span className="text-sm font-bold text-error">No healthy provider</span>
                )
              }
            >
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Provider</th>
                    <th scope="col">Tier</th>
                    <th scope="col">Status</th>
                    <th scope="col">Detail</th>
                    <th scope="col" className="num">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.provider}>
                      <td className="kv">{row.provider}</td>
                      <td><Tag value={row.tier} /></td>
                      <td>{row.healthy ? <Tag value="healthy" /> : <Tag value="unavailable" />}</td>
                      <td className="text-sm text-secondary">{row.detail}</td>
                      <td className="num text-sm">{row.cost_per_unit === 0 ? "Free" : `$${row.cost_per_unit} per ${row.unit.replace(/_/g, " ")}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
