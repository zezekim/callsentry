"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type CallStats, type CallSummary, type ProviderSnapshot } from "@/lib/api";
import { useSession } from "@/components/shell";
import {
  ButtonLink,
  Card,
  Empty,
  ErrorSummary,
  PageHeader,
  Spinner,
  Stat,
  Tag,
  duration,
  money,
  when,
} from "@/components/ui";

export default function OverviewPage() {
  const [stats, setStats] = useState<CallStats | null>(null);
  const [recent, setRecent] = useState<CallSummary[]>([]);
  const [providers, setProviders] = useState<ProviderSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const session = useSession();
  const canConfigure = session?.role !== "viewer";

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

  if (error) return <ErrorSummary error={error} />;
  if (!stats) return <Spinner />;

  const sentimentTotal = Object.values(stats.sentiment).reduce((a, b) => a + b, 0);
  const degraded = providers
    ? Object.entries(providers.components).filter(([, rows]) => !rows.some((r) => r.healthy && r.tier !== "mock"))
    : [];

  return (
    <div>
      <PageHeader
        title="Overview"
        lede="Activity in the last 24 hours and the current state of the receptionist."
        actions={<ButtonLink href="/calls">View call log</ButtonLink>}
      />

      {degraded.length > 0 && (
        <div className="banner">
          <div className="banner-title">Service degraded</div>
          <div className="banner-body">
            <p>
              {degraded.length === 1 ? "One component is" : `${degraded.length} components are`}{" "}
              running on the placeholder provider, so callers are being handed to a person
              for anything it cannot do.
              {canConfigure && (
                <>
                  {" "}
                  <Link href="/settings/providers" className="link">
                    Check provider status
                  </Link>
                  .
                </>
              )}
            </p>
          </div>
        </div>
      )}

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Calls in the last 24 hours" value={stats.calls_today} />
        <Stat label="Appointments booked" value={stats.bookings_today} />
        <Stat label="Escalated to a person" value={stats.escalations_today} />
        <Stat label="Average call length" value={duration(Math.round(stats.avg_duration_seconds))} hint="minutes:seconds" />
      </div>

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <Stat label="Cost in the last 24 hours" value={money(stats.cost_today_usd)} />
        <Stat label="Cost to date" value={money(stats.cost_all_time_usd)} />
        <Stat label="Processed on local hardware" value={`${stats.local_share_pct}%`} hint="share of inference not sent to a paid API" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Recent calls" className="min-w-0 lg:col-span-2" flush actions={<ButtonLink href="/calls" small>All calls</ButtonLink>}>
          {recent.length === 0 ? (
            <Empty
              message="No calls have been received yet."
              hint="Point the voice webhook for your Twilio number at /webhooks/twilio to begin."
            />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Caller</th>
                    <th scope="col">Outcome</th>
                    <th scope="col">Sentiment</th>
                    <th scope="col" className="num">Length</th>
                    <th scope="col" className="num">Cost</th>
                    <th scope="col">Received</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((call) => (
                    <tr key={call.id}>
                      <td>
                        <Link href={`/calls/${call.id}`} className="link kv">
                          {call.caller_number}
                        </Link>
                      </td>
                      <td><Tag value={call.outcome} /></td>
                      <td><Tag value={call.sentiment} /></td>
                      <td className="num">{duration(call.duration_seconds)}</td>
                      <td className="num">{money(call.cost_usd)}</td>
                      <td className="text-secondary">{when(call.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="min-w-0 space-y-6">
          <Card title="Caller sentiment">
            {sentimentTotal === 0 ? (
              <p className="text-secondary">No analysed calls yet.</p>
            ) : (
              <table className="table">
                <tbody>
                  {(["positive", "neutral", "negative"] as const).map((key) => {
                    const count = stats.sentiment[key] ?? 0;
                    const pct = Math.round((count / sentimentTotal) * 100);
                    return (
                      <tr key={key}>
                        <td className="capitalize">{key}</td>
                        <td className="num">{count}</td>
                        <td className="num text-secondary">{pct}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </Card>

          <Card
            title="Provider status"
            description={providers?.local_only ? "Local-only mode" : "Cloud fallbacks enabled"}
            actions={canConfigure ? <ButtonLink href="/settings/providers" small>Details</ButtonLink> : undefined}
          >
            <ul className="divide-y divide-border">
              {providers &&
                Object.entries(providers.components).map(([component, rows]) => {
                  const serving = rows.find((r) => r.healthy);
                  return (
                    <li key={component} className="flex items-center justify-between gap-3 py-2">
                      <span className="shrink-0 text-sm uppercase">{component}</span>
                      {serving ? (
                        <span className="flex min-w-0 items-center gap-2">
                          <span className="kv truncate text-xs" title={serving.provider}>{serving.provider}</span>
                          <Tag value={serving.tier} />
                        </span>
                      ) : (
                        <span className="font-bold text-error">Unavailable</span>
                      )}
                    </li>
                  );
                })}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
