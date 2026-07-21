"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type CallDetail } from "@/lib/api";
import { Badge, Empty, ErrorNote, Panel, Spinner, Stat, duration, money, when } from "@/components/ui";

export default function CallDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [call, setCall] = useState<CallDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<CallDetail>(`/calls/${id}`)
      .then(setCall)
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) return <ErrorNote error={error} />;
  if (!call) return <Spinner />;

  const lines = (call.transcript ?? "").split("\n").filter(Boolean);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/calls" className="btn px-2 py-1 text-xs">
          ← Back
        </Link>
        <h1 className="font-mono text-lg text-slate-100">{call.caller_number}</h1>
        <Badge value={call.outcome} />
        <Badge value={call.sentiment} />
        <span className="text-xs text-muted">{when(call.created_at)}</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Duration" value={duration(call.duration_seconds)} />
        <Stat label="Cost" value={money(call.cost_usd)} tone="good" />
        <Stat
          label="Escalated"
          value={call.escalated ? "Yes" : "No"}
          tone={call.escalated ? "warn" : "default"}
          hint={call.escalation_reason ?? undefined}
        />
      </div>

      {call.summary && (
        <Panel title="AI summary">
          <p className="px-4 py-3 text-sm leading-relaxed text-slate-300">{call.summary}</p>
        </Panel>
      )}

      {call.recording_url && (
        <Panel title="Recording" subtitle="Deleted automatically once retention expires">
          <div className="px-4 py-3">
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <audio controls src={call.recording_url} className="w-full" />
          </div>
        </Panel>
      )}

      <Panel title="Transcript">
        {lines.length === 0 ? (
          <Empty message="No transcript captured for this call." />
        ) : (
          <div className="space-y-3 p-4">
            {lines.map((line, index) => {
              const isCaller = line.startsWith("Caller:");
              const text = line.replace(/^(Caller|Assistant):\s*/, "");
              return (
                <div key={index} className={isCaller ? "" : "pl-8"}>
                  <div className="mb-0.5 text-xs uppercase tracking-wide text-muted">
                    {isCaller ? "Caller" : "Assistant"}
                  </div>
                  <div
                    className={`rounded-lg px-3 py-2 text-sm ${
                      isCaller ? "bg-slate-800/60" : "bg-emerald-950/40"
                    }`}
                  >
                    {text}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      <Panel
        title="Provider trace"
        subtitle="Which tier served each step, and what it cost"
      >
        {call.provider_log.length === 0 ? (
          <Empty message="No provider activity recorded." />
        ) : (
          <div className="table-scroll">
            <table className="w-full">
              <thead className="border-b border-edge">
                <tr>
                  <th className="th">Component</th>
                  <th className="th">Provider</th>
                  <th className="th">Tier</th>
                  <th className="th">Result</th>
                  <th className="th">Latency</th>
                  <th className="th">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {call.provider_log.map((attempt, index) => (
                  <tr key={index}>
                    <td className="td uppercase text-muted">{attempt.component}</td>
                    <td className="td font-mono">{attempt.provider}</td>
                    <td className="td">
                      <Badge value={attempt.tier} />
                    </td>
                    <td className="td">
                      {attempt.ok ? (
                        <span className="text-accent">ok</span>
                      ) : (
                        <span className="text-danger">failed</span>
                      )}
                    </td>
                    <td className="td font-mono text-muted">{attempt.latency_ms}ms</td>
                    <td className="td text-xs text-muted">{attempt.detail || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
