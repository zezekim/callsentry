"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type BusinessSettings } from "@/lib/api";
import { ErrorNote, Panel, Spinner } from "@/components/ui";

const DAYS = [
  ["mon", "Monday"],
  ["tue", "Tuesday"],
  ["wed", "Wednesday"],
  ["thu", "Thursday"],
  ["fri", "Friday"],
  ["sat", "Saturday"],
  ["sun", "Sunday"],
] as const;

export default function SettingsPage() {
  const [settings, setSettings] = useState<BusinessSettings | null>(null);
  const [voices, setVoices] = useState<{ id: string; label: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [calKey, setCalKey] = useState("");
  const [calEventType, setCalEventType] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<BusinessSettings>("/settings"),
      api.get<{ voices: { id: string; label: string }[] }>("/settings/voices"),
    ])
      .then(([s, v]) => {
        setSettings(s);
        setVoices(v.voices);
        setCalEventType(s.cal_com_event_type_id ?? "");
      })
      .catch((e) => setError(e.message));
  }, []);

  function update<K extends keyof BusinessSettings>(key: K, value: BusinessSettings[K]) {
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  function setHours(day: string, value: [string, string] | null) {
    setSettings((prev) =>
      prev ? { ...prev, business_hours: { ...prev.business_hours, [day]: value } } : prev,
    );
  }

  async function save() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await api.patch<BusinessSettings>("/settings", {
        name: settings.name,
        timezone: settings.timezone,
        business_hours: settings.business_hours,
        escalation_phone: settings.escalation_phone,
        after_hours_message: settings.after_hours_message,
        greeting_override: settings.greeting_override,
        twilio_number: settings.twilio_number,
        voice_id: settings.voice_id,
      });
      setSettings(updated);
      setNotice("Settings saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function previewVoice() {
    if (!settings) return;
    setError(null);
    try {
      const blob = await api.blob("/settings/test-voice", {
        text: "Hi, thanks for calling. I'm an AI assistant. How can I help you today?",
        voice: settings.voice_id,
      });
      new Audio(URL.createObjectURL(blob)).play();
    } catch {
      setError("Voice preview failed — check that the worker service is running.");
    }
  }

  async function connectCal() {
    setError(null);
    setNotice(null);
    try {
      const result = await api.post<{ detail: string }>("/settings/connect-cal", {
        api_key: calKey,
        event_type_id: calEventType,
      });
      setNotice(result.detail);
      setCalKey("");
      setSettings(await api.get<BusinessSettings>("/settings"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cal.com connection failed");
    }
  }

  if (error && !settings) return <ErrorNote error={error} />;
  if (!settings) return <Spinner />;

  return (
    <div className="space-y-6">
      <ErrorNote error={error} />
      {notice && (
        <div className="rounded-md border border-emerald-900 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-300">
          {notice}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Business">
          <div className="space-y-4 p-4">
            <div>
              <label className="label">Name</label>
              <input
                className="input"
                value={settings.name}
                onChange={(e) => update("name", e.target.value)}
              />
            </div>
            <div>
              <label className="label">Timezone (IANA)</label>
              <input
                className="input"
                value={settings.timezone}
                onChange={(e) => update("timezone", e.target.value)}
                placeholder="America/New_York"
              />
            </div>
            <div>
              <label className="label">Twilio number</label>
              <input
                className="input font-mono"
                value={settings.twilio_number ?? ""}
                onChange={(e) => update("twilio_number", e.target.value)}
                placeholder="+15551234567"
              />
              <p className="mt-1 text-xs text-muted">
                Routes inbound calls to this business. Must match the number exactly.
              </p>
            </div>
            <div>
              <label className="label">Escalation phone</label>
              <input
                className="input font-mono"
                value={settings.escalation_phone ?? ""}
                onChange={(e) => update("escalation_phone", e.target.value)}
                placeholder="+15559876543"
              />
              <p className="mt-1 text-xs text-muted">
                Where warm transfers go. Without this, the agent takes a message instead.
              </p>
            </div>
          </div>
        </Panel>

        <Panel title="Opening hours" subtitle="Outside these, callers get the after-hours flow">
          <div className="space-y-2 p-4">
            {DAYS.map(([key, label]) => {
              const window = settings.business_hours[key];
              return (
                <div key={key} className="flex items-center gap-3">
                  <label className="flex w-28 items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={Boolean(window)}
                      onChange={(e) =>
                        setHours(key, e.target.checked ? ["09:00", "17:00"] : null)
                      }
                    />
                    {label}
                  </label>
                  {window ? (
                    <>
                      <input
                        type="time"
                        className="input max-w-[7.5rem]"
                        value={window[0]}
                        onChange={(e) => setHours(key, [e.target.value, window[1]])}
                      />
                      <span className="text-muted">to</span>
                      <input
                        type="time"
                        className="input max-w-[7.5rem]"
                        value={window[1]}
                        onChange={(e) => setHours(key, [window[0], e.target.value])}
                      />
                    </>
                  ) : (
                    <span className="text-sm text-muted">Closed</span>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel title="Voice & greeting">
          <div className="space-y-4 p-4">
            <div>
              <label className="label">Voice</label>
              <div className="flex gap-2">
                <select
                  className="input"
                  value={settings.voice_id}
                  onChange={(e) => update("voice_id", e.target.value)}
                >
                  {voices.map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.label}
                    </option>
                  ))}
                </select>
                <button className="btn whitespace-nowrap" onClick={previewVoice}>
                  ▶ Preview
                </button>
              </div>
            </div>
            <div>
              <label className="label">Greeting override</label>
              <textarea
                className="input min-h-[4.5rem] resize-y"
                value={settings.greeting_override ?? ""}
                onChange={(e) => update("greeting_override", e.target.value)}
                placeholder="Leave blank to use the compliant default greeting."
              />
              <p className="mt-1 text-xs text-warn">
                If you override this, you are responsible for keeping the AI disclosure and
                recording notice in the opening line.
              </p>
            </div>
            <div>
              <label className="label">After-hours message</label>
              <textarea
                className="input min-h-[4.5rem] resize-y"
                value={settings.after_hours_message ?? ""}
                onChange={(e) => update("after_hours_message", e.target.value)}
              />
            </div>
          </div>
        </Panel>

        <Panel
          title="Cal.com"
          subtitle="Credentials are verified before they're stored, then encrypted at rest"
        >
          <div className="space-y-4 p-4">
            <div className="text-xs text-muted">
              Current key: <span className="font-mono">{settings.cal_com_api_key}</span>
            </div>
            <div>
              <label className="label">API key</label>
              <input
                className="input font-mono"
                type="password"
                value={calKey}
                onChange={(e) => setCalKey(e.target.value)}
                placeholder="cal_live_…"
              />
            </div>
            <div>
              <label className="label">Event type ID</label>
              <input
                className="input font-mono"
                value={calEventType}
                onChange={(e) => setCalEventType(e.target.value)}
                placeholder="123456"
              />
            </div>
            <button
              className="btn"
              onClick={connectCal}
              disabled={!calKey || !calEventType}
            >
              Verify & connect
            </button>
          </div>
        </Panel>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save settings"}
        </button>
        <Link href="/settings/providers" className="btn">
          Provider health →
        </Link>
        <span className="text-xs text-muted">
          {settings.local_only
            ? "Local-only mode: no paid inference API will be called."
            : "Cloud fallbacks enabled."}
        </span>
      </div>
    </div>
  );
}
