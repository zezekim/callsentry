"use client";

import { useEffect, useState } from "react";
import { api, type BusinessSettings } from "@/lib/api";
import { Card, ErrorSummary, Field, Notice, Spinner, SummaryList } from "@/components/ui";

export default function CalendarSettingsPage() {
  const [settings, setSettings] = useState<BusinessSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [eventType, setEventType] = useState("");

  useEffect(() => {
    api
      .get<BusinessSettings>("/settings")
      .then((s) => {
        setSettings(s);
        setEventType(s.cal_com_event_type_id ?? "");
      })
      .catch((e) => setError(e.message));
  }, []);

  async function connect(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.post<{ detail: string }>("/settings/connect-cal", {
        api_key: apiKey,
        event_type_id: eventType,
      });
      setNotice(result.detail);
      setApiKey("");
      setSettings(await api.get<BusinessSettings>("/settings"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cal.com connection failed");
    } finally {
      setBusy(false);
    }
  }

  if (error && !settings) return <ErrorSummary error={error} />;
  if (!settings) return <Spinner />;

  const connected = settings.cal_com_api_key !== "<unset>";

  return (
    <div>
      <h2 className="h2 mb-6">Calendar</h2>
      <ErrorSummary error={error} />
      {notice && <Notice kind="success">{notice}</Notice>}

      <Card title="Cal.com" description="Where the receptionist checks availability and places bookings" className="mb-6">
        <SummaryList
          rows={[
            { key: "Status", value: connected ? "Connected" : "Not connected. Bookings are held locally only." },
            { key: "API key", value: <span className="kv">{connected ? settings.cal_com_api_key : "Not set"}</span> },
            { key: "Event type", value: settings.cal_com_event_type_id ? <span className="kv">{settings.cal_com_event_type_id}</span> : "Not set" },
          ]}
        />
      </Card>

      <Card title={connected ? "Replace the connection" : "Connect Cal.com"} description="The key is checked against Cal.com before it is stored, then encrypted at rest">
        <form onSubmit={connect} className="max-w-md">
          <Field label="API key" htmlFor="cal-key" hint="From Cal.com under Settings, Developer, API keys">
            <input
              id="cal-key"
              className="input kv"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="cal_live_…"
            />
          </Field>
          <Field label="Event type ID" htmlFor="cal-event" hint="The numeric ID of the event type callers are booked into">
            <input id="cal-event" className="input input-narrow kv" value={eventType} onChange={(e) => setEventType(e.target.value)} />
          </Field>
          <button className="btn" type="submit" disabled={busy || !apiKey || !eventType}>
            {busy ? "Checking…" : "Verify and save"}
          </button>
        </form>
      </Card>
    </div>
  );
}
