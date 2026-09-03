"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, getToken, type CallSummary } from "@/lib/api";
import { Card, Empty, ErrorSummary, PageHeader, Spinner, Tag, duration, money, when } from "@/components/ui";

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
    <div>
      <PageHeader
        title="Call log"
        lede="Every call the receptionist has handled. Select a caller number for the transcript and provider trace."
        actions={
          <button onClick={exportCsv} className="btn btn-secondary">
            Export as CSV
          </button>
        }
      />
      <ErrorSummary error={error} />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <div>
          <label className="label" htmlFor="search">Search</label>
          <input
            id="search"
            className="input"
            placeholder="Number or words in the transcript"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="outcome">Outcome</label>
          <select id="outcome" className="input" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            {OUTCOMES.map((o) => (
              <option key={o} value={o}>{o ? o.replace(/_/g, " ") : "All outcomes"}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="sentiment">Sentiment</label>
          <select id="sentiment" className="input" value={sentiment} onChange={(e) => setSentiment(e.target.value)}>
            {SENTIMENTS.map((s) => (
              <option key={s} value={s}>{s || "All sentiment"}</option>
            ))}
          </select>
        </div>
      </div>

      <Card flush>
        {calls === null ? (
          <Spinner />
        ) : calls.length === 0 ? (
          <Empty message="No calls match these filters." />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <caption className="sr-only">Calls</caption>
              <thead>
                <tr>
                  <th scope="col">Caller</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Sentiment</th>
                  <th scope="col">Escalated</th>
                  <th scope="col" className="num">Length</th>
                  <th scope="col" className="num">Cost</th>
                  <th scope="col">Received</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id}>
                    <td>
                      <Link href={`/calls/${call.id}`} className="link kv">{call.caller_number}</Link>
                    </td>
                    <td><Tag value={call.outcome} /></td>
                    <td><Tag value={call.sentiment} /></td>
                    <td>{call.escalated ? "Yes" : <span className="text-secondary">No</span>}</td>
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
      {calls && calls.length > 0 && (
        <p className="mt-3 text-sm text-secondary">Showing the most recent {calls.length} calls.</p>
      )}
    </div>
  );
}
