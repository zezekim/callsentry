"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api,
  type CallStats,
  type CallSummary,
  type ProviderSnapshot,
} from "@/lib/api";
import { Badge, Empty, ErrorNote, Panel, Spinner, Stat, duration, money, when } from "@/components/ui";

export default function OverviewPage() {
  const [stats, setStats] = useState<CallStats | null>(null);
  const [recent, setRecent] = useState<CallSummary[]>([]);
  const [providers, setProviders] = useState<ProviderSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<CallStats>("/calls/stats"),
      api.get<CallSummary[]>("/calls?limit=8"),
      api.get<ProviderSnapshot>("/settings/providers"),
    ])
      .then(([s, r, p]) => {
        setStats(s);
        setRecent(r);
        setProviders(p);
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorNote error={error} />;
  if (!stats) return <Spinner />;

  const sentimentTotal = Object.values(stats.sentiment).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Calls (24h)" value={stats.calls_today} />
        <Stat label="Bookings (24h)" value={stats.bookings_today} tone="good" />
        <Stat
          label="Escalations (24h)"
          value={stats.escalations_today}
          tone={stats.escalations_today > 0 ? "warn" : "default"}
        />
        <Stat
          label="Avg duration"
          value={duration(Math.round(stats.avg_duration_seconds))}
          hint="minutes:seconds"
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          label="Cost (24h)"
          value={money(stats.cost_today_usd)}
          tone="good"
          hint="telephony is the only paid component"
        />
        <Stat label="Cost (all time)" value={money(stats.cost_all_time_usd)} tone="good" />
        <Stat
          label="Served locally"
          value={`${stats.local_share_pct}%`}
          tone={stats.local_share_pct > 90 ? "good" : "warn"}
          hint="share of inference done on your hardware"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel
          title="Recent calls"
          className="lg:col-span-2"
          actions={
            <Link href="/calls" className="btn px-2 py-1 text-xs">
              View all
            </Link>
          }
        >
          {recent.length === 0 ? (
            <Empty
              message="No calls yet."
              hint="Point your Twilio number's voice webhook at /webhooks/twilio to get started."
            />
          ) : (
            <div className="table-scroll">
              <table className="w-full">
                <thead className="border-b border-edge">
                  <tr>
                    <th className="th">Caller</th>
                    <th className="th">Outcome</th>
                    <th className="th">Sentiment</th>
                    <th className="th">Length</th>
                    <th className="th">Cost</th>
                    <th className="th">When</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge">
                  {recent.map((call) => (
                    <tr key={call.id} className="hover:bg-slate-900/60">
                      <td className="td">
                        <Link href={`/calls/${call.id}`} className="font-mono hover:text-accent">
                          {call.caller_number}
                        </Link>
                      </td>
                      <td className="td">
                        <Badge value={call.outcome} />
                      </td>
                      <td className="td">
                        <Badge value={call.sentiment} />
                      </td>
                      <td className="td font-mono text-muted">
                        {duration(call.duration_seconds)}
                      </td>
                      <td className="td font-mono text-accent">{money(call.cost_usd)}</td>
                      <td className="td text-muted">{when(call.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <div className="space-y-6">
          <Panel title="Sentiment">
            {sentimentTotal === 0 ? (
              <Empty message="No analysed calls yet." />
            ) : (
              <div className="space-y-3 p-4">
                {(["positive", "neutral", "negative"] as const).map((key) => {
                  const count = stats.sentiment[key] ?? 0;
                  const pct = Math.round((count / sentimentTotal) * 100);
                  const bar = {
                    positive: "bg-emerald-500",
                    neutral: "bg-slate-500",
                    negative: "bg-red-500",
                  }[key];
                  return (
                    <div key={key}>
                      <div className="mb-1 flex justify-between text-xs">
                        <span className="capitalize text-muted">{key}</span>
                        <span className="font-mono">
                          {count} ({pct}%)
                        </span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                        <div className={`h-full ${bar}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>

          <Panel
            title="System health"
            subtitle={providers?.local_only ? "Local-only mode" : "Cloud fallbacks enabled"}
            actions={
              <Link href="/settings/providers" className="btn px-2 py-1 text-xs">
                Details
              </Link>
            }
          >
            <div className="space-y-2 p-4">
              {providers &&
                Object.entries(providers.components).map(([component, rows]) => {
                  const serving = rows.find((r) => r.healthy);
                  return (
                    <div key={component} className="flex items-center justify-between text-xs">
                      <span className="uppercase tracking-wide text-muted">{component}</span>
                      {serving ? (
                        <span className="flex items-center gap-1.5">
                          <span className="font-mono text-slate-300">{serving.provider}</span>
                          <Badge value={serving.tier} />
                        </span>
                      ) : (
                        <span className="text-danger">unavailable</span>
                      )}
                    </div>
                  );
                })}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
