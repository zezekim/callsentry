"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type CallDetail } from "@/lib/api";
import { Card, Empty, ErrorSummary, PageHeader, Spinner, SummaryList, Tag, duration, money, when } from "@/components/ui";

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

  if (error) return <ErrorSummary error={error} />;
  if (!call) return <Spinner />;

  const lines = (call.transcript ?? "").split("\n").filter(Boolean);

  return (
    <div>
      <Link href="/calls" className="back-link">Back to call log</Link>
      <PageHeader caption="Call record" title={call.caller_number} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {call.summary && (
            <Card title="Summary" description="Written by the receptionist after the call">
              <p>{call.summary}</p>
            </Card>
          )}

          <Card title="Transcript" flush>
            {lines.length === 0 ? (
              <Empty message="No transcript was captured for this call." />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col" className="w-28">Speaker</th>
                    <th scope="col">Said</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line, index) => {
                    const isCaller = line.startsWith("Caller:");
                    const text = line.replace(/^(Caller|Assistant):\s*/, "");
                    return (
                      <tr key={index}>
                        <td className="font-bold">{isCaller ? "Caller" : "Receptionist"}</td>
                        <td>{text}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </Card>

          <Card title="Provider trace" description="Which service handled each step, and what it cost" flush>
            {call.provider_log.length === 0 ? (
              <Empty message="No provider activity was recorded." />
            ) : (
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Component</th>
                      <th scope="col">Provider</th>
                      <th scope="col">Tier</th>
                      <th scope="col">Result</th>
                      <th scope="col" className="num">Latency</th>
                      <th scope="col">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {call.provider_log.map((attempt, index) => (
                      <tr key={index}>
                        <td className="uppercase text-sm">{attempt.component}</td>
                        <td className="kv">{attempt.provider}</td>
                        <td><Tag value={attempt.tier} /></td>
                        <td>{attempt.ok ? "Succeeded" : <span className="font-bold text-error">Failed</span>}</td>
                        <td className="num">{attempt.latency_ms} ms</td>
                        <td className="text-sm text-secondary">{attempt.detail || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Details">
            <SummaryList
              rows={[
                { key: "Received", value: when(call.created_at) },
                { key: "Outcome", value: <Tag value={call.outcome} /> },
                { key: "Sentiment", value: <Tag value={call.sentiment} /> },
                { key: "Length", value: duration(call.duration_seconds) },
                { key: "Cost", value: money(call.cost_usd) },
                {
                  key: "Escalated",
                  value: call.escalated ? (
                    <>
                      Yes
                      {call.escalation_reason && <span className="block text-sm text-secondary">{call.escalation_reason}</span>}
                    </>
                  ) : (
                    "No"
                  ),
                },
              ]}
            />
          </Card>

          {call.recording_url && (
            <Card title="Recording" description="Deleted automatically when retention expires">
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <audio controls src={call.recording_url} className="w-full" />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
