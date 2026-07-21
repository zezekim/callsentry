"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, getToken, type CallSummary } from "@/lib/api";
import { Badge, Empty, ErrorNote, Panel, Spinner, duration, money, when } from "@/components/ui";

const OUTCOMES = ["", "booked", "answered", "escalated", "voicemail", "abandoned"];
const SENTIMENTS = ["", "positive", "neutral", "negative"];

export default function CallsPage() {
  const [calls, setCalls] = useState<CallSummary[] | null>(null);
  const [outcome, setOutcome] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams({ limit: "100" });
    if (outcome) params.set("outcome", outcome);
    if (sentiment) params.set("sentiment", sentiment);
    if (search.trim()) params.set("search", search.trim());

    setCalls(null);
    api
      .get<CallSummary[]>(`/calls?${params}`)
      .then(setCalls)
      .catch((e) => setError(e.message));
  }, [outcome, sentiment, search]);

  useEffect(() => {
    // Debounce so typing in the search box doesn't fire a request per keystroke.
    const timer = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, search]);

  function exportCsv() {
    const params = new URLSearchParams();
    if (outcome) params.set("outcome", outcome);
    if (sentiment) params.set("sentiment", sentiment);
    // The download bypasses the fetch wrapper, so the token rides in the query
    // is not an option - open a fetch and stream it into a blob instead.
    fetch(api.url(`/calls/export?${params}`), {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "calls.csv";
        link.click();
        URL.revokeObjectURL(url);
      })
      .catch((e) => setError(e.message));
  }

  return (
    <div className="space-y-4">
      <ErrorNote error={error} />

      <Panel
        title="Call log"
        subtitle="Click a caller number for the full transcript and provider trace"
        actions={
          <button onClick={exportCsv} className="btn px-2 py-1 text-xs">
            Export CSV
          </button>
        }
      >
        <div className="flex flex-wrap gap-3 border-b border-edge px-4 py-3">
          <input
            className="input max-w-xs"
            placeholder="Search transcripts and numbers…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="input max-w-[10rem]"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
          >
            {OUTCOMES.map((o) => (
              <option key={o} value={o}>
                {o || "All outcomes"}
              </option>
            ))}
          </select>
          <select
            className="input max-w-[10rem]"
            value={sentiment}
            onChange={(e) => setSentiment(e.target.value)}
          >
            {SENTIMENTS.map((s) => (
              <option key={s} value={s}>
                {s || "All sentiment"}
              </option>
            ))}
          </select>
        </div>

        {calls === null ? (
          <Spinner />
        ) : calls.length === 0 ? (
          <Empty message="No calls match those filters." />
        ) : (
          <div className="table-scroll">
            <table className="w-full">
              <thead className="border-b border-edge">
                <tr>
                  <th className="th">Caller</th>
                  <th className="th">Outcome</th>
                  <th className="th">Sentiment</th>
                  <th className="th">Escalated</th>
                  <th className="th">Length</th>
                  <th className="th">Cost</th>
                  <th className="th">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {calls.map((call) => (
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
                    <td className="td">
                      {call.escalated ? (
                        <span className="text-warn">yes</span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="td font-mono text-muted">{duration(call.duration_seconds)}</td>
                    <td className="td font-mono text-accent">{money(call.cost_usd)}</td>
                    <td className="td text-muted">{when(call.created_at)}</td>
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
