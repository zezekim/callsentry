"use client";

import { useEffect, useState } from "react";
import { api, type BusinessSettings } from "@/lib/api";
import { Card, ErrorSummary, Field, Notice, Spinner, WarningText } from "@/components/ui";

const DAYS = [
  ["mon", "Monday"],
  ["tue", "Tuesday"],
  ["wed", "Wednesday"],
  ["thu", "Thursday"],
  ["fri", "Friday"],
  ["sat", "Saturday"],
  ["sun", "Sunday"],
] as const;

export default function BusinessSettingsPage() {
  const [settings, setSettings] = useState<BusinessSettings | null>(null);
  const [voices, setVoices] = useState<{ id: string; label: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<BusinessSettings>("/settings"),
      api.get<{ voices: { id: string; label: string }[] }>("/settings/voices"),
    ])
      .then(([s, v]) => {
        setSettings(s);
        setVoices(v.voices);
      })
      .catch((e) => setError(e.message));
  }, []);

  function update<K extends keyof BusinessSettings>(key: K, value: BusinessSettings[K]) {
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  function setHours(day: string, value: [string, string] | null) {
    setSettings((prev) => (prev ? { ...prev, business_hours: { ...prev.business_hours, [day]: value } } : prev));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await api.patch<BusinessSettings>("/settings", {
        name: settings.name,
        timezone: settings.timezone,
        business_hours: settings.business_hours,
        escalation_phone: settings.escalation_phone || null,
        after_hours_message: settings.after_hours_message || null,
        greeting_override: settings.greeting_override || null,
        twilio_number: settings.twilio_number || null,
        voice_id: settings.voice_id,
      });
      setSettings(updated);
      setNotice("Business settings have been saved.");
      window.scrollTo({ top: 0 });
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
        text: "Hello, thank you for calling. I am an automated assistant. How can I help you today?",
        voice: settings.voice_id,
      });
      new Audio(URL.createObjectURL(blob)).play();
    } catch {
      setError("The voice preview failed. Check that the worker service is running.");
    }
  }

  if (error && !settings) return <ErrorSummary error={error} />;
  if (!settings) return <Spinner />;

  return (
    <form onSubmit={save}>
      <h2 className="h2 mb-6">Business</h2>
      <ErrorSummary error={error} />
      {notice && <Notice kind="success">{notice}</Notice>}

      <Card title="Details" className="mb-6">
        <Field label="Business name" htmlFor="name" hint="Used in the greeting and in appointment confirmations">
          <input id="name" className="input input-medium" value={settings.name} onChange={(e) => update("name", e.target.value)} />
        </Field>
        <Field label="Time zone" htmlFor="timezone" hint="IANA name, for example Europe/London or America/New_York">
          <input id="timezone" className="input input-medium" value={settings.timezone} onChange={(e) => update("timezone", e.target.value)} />
        </Field>
        <Field label="Inbound phone number" htmlFor="twilio" hint="The Twilio number callers dial. Must match exactly, in E.164 format.">
          <input id="twilio" className="input input-narrow kv" value={settings.twilio_number ?? ""} onChange={(e) => update("twilio_number", e.target.value)} placeholder="+15551234567" />
        </Field>
        <Field label="Escalation phone number" htmlFor="escalation" hint="Where calls are transferred when a person is needed. If blank, the receptionist takes a message instead.">
          <input id="escalation" className="input input-narrow kv" value={settings.escalation_phone ?? ""} onChange={(e) => update("escalation_phone", e.target.value)} placeholder="+15559876543" />
        </Field>
      </Card>

      <Card title="Opening hours" description="Outside these hours callers hear the after-hours message" className="mb-6">
        <table className="table max-w-xl">
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Open</th>
              <th scope="col">From</th>
              <th scope="col">To</th>
            </tr>
          </thead>
          <tbody>
            {DAYS.map(([key, label]) => {
              const window = settings.business_hours[key];
              return (
                <tr key={key}>
                  <td className="font-bold">
                    <label htmlFor={`open-${key}`}>{label}</label>
                  </td>
                  <td>
                    <input
                      id={`open-${key}`}
                      type="checkbox"
                      className="checkbox"
                      checked={Boolean(window)}
                      onChange={(e) => setHours(key, e.target.checked ? ["09:00", "17:00"] : null)}
                    />
                  </td>
                  {window ? (
                    <>
                      <td>
                        <input type="time" aria-label={`${label} opening time`} className="input input-narrow" value={window[0]} onChange={(e) => setHours(key, [e.target.value, window[1]])} />
                      </td>
                      <td>
                        <input type="time" aria-label={`${label} closing time`} className="input input-narrow" value={window[1]} onChange={(e) => setHours(key, [window[0], e.target.value])} />
                      </td>
                    </>
                  ) : (
                    <td colSpan={2} className="text-secondary">Closed</td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <Card title="Voice and greeting" className="mb-6">
        <Field label="Voice" htmlFor="voice">
          <div className="flex flex-wrap gap-3">
            <select id="voice" className="input input-medium" value={settings.voice_id} onChange={(e) => update("voice_id", e.target.value)}>
              {voices.map((voice) => (
                <option key={voice.id} value={voice.id}>{voice.label}</option>
              ))}
            </select>
            <button type="button" className="btn btn-secondary" onClick={previewVoice}>
              Play a sample
            </button>
          </div>
        </Field>
        <Field
          label="Greeting override"
          htmlFor="greeting"
          hint="Leave blank to use the standard greeting, which includes the automated-assistant disclosure and the recording notice."
        >
          <textarea id="greeting" className="input" value={settings.greeting_override ?? ""} onChange={(e) => update("greeting_override", e.target.value)} />
        </Field>
        {settings.greeting_override && (
          <WarningText>
            With a custom greeting you are responsible for keeping the automated-assistant disclosure and the
            recording notice in the opening line.
          </WarningText>
        )}
        <Field label="After-hours message" htmlFor="after-hours">
          <textarea id="after-hours" className="input" value={settings.after_hours_message ?? ""} onChange={(e) => update("after_hours_message", e.target.value)} />
        </Field>
      </Card>

      <div className="flex flex-wrap items-center gap-4">
        <button className="btn" type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save changes"}
        </button>
        <span className="text-sm text-secondary">
          {settings.local_only ? "This installation is in local-only mode: no paid inference API is called." : "Cloud fallbacks are enabled for this installation."}
        </span>
      </div>
    </form>
  );
}
