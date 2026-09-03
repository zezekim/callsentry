"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, Empty, ErrorSummary, Field, Notice, PageHeader, Spinner, Stat, WarningText, money, when } from "@/components/ui";

interface BusinessRow {
  id: string;
  name: string;
  timezone: string;
  twilio_number: string | null;
  call_count: number;
  total_cost_usd: number;
  created_at: string;
}

interface PlatformCosts {
  total_usd: number;
  by_tier: Record<string, number>;
  by_category: Record<string, number>;
  by_business: { name: string; cost_usd: number }[];
  local_share_pct: number;
}

export default function AdminPage() {
  const [businesses, setBusinesses] = useState<BusinessRow[] | null>(null);
  const [costs, setCosts] = useState<PlatformCosts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [confirming, setConfirming] = useState<BusinessRow | null>(null);
  const [typed, setTyped] = useState("");

  const [form, setForm] = useState({
    name: "",
    timezone: "America/New_York",
    admin_email: "",
    admin_password: "",
    twilio_number: "",
    escalation_phone: "",
  });

  function load() {
    Promise.all([api.get<BusinessRow[]>("/admin/businesses"), api.get<PlatformCosts>("/admin/costs")])
      .then(([b, c]) => {
        setBusinesses(b);
        setCosts(c);
      })
      .catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function provision(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    setNotice(null);
    try {
      await api.post("/admin/businesses", {
        ...form,
        twilio_number: form.twilio_number || null,
        escalation_phone: form.escalation_phone || null,
      });
      setNotice(`${form.name} has been set up. Its administrator can sign in with the email address given.`);
      setForm({ ...form, name: "", admin_email: "", admin_password: "", twilio_number: "" });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Provisioning failed");
    } finally {
      setCreating(false);
    }
  }

  async function remove(business: BusinessRow) {
    setError(null);
    try {
      await api.delete(`/admin/businesses/${business.id}`);
      setNotice(`${business.name} and all of its records have been deleted.`);
      setConfirming(null);
      setTyped("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (error && !businesses) return <ErrorSummary error={error} />;
  if (!businesses || !costs) return <Spinner />;

  return (
    <div>
      <PageHeader
        caption="Platform operators"
        title="Administration"
        lede="Every business served by this installation, and what the platform as a whole has cost."
      />
      <ErrorSummary error={error} />
      {notice && <Notice kind="success">{notice}</Notice>}

      <div className="mb-8 grid gap-4 sm:grid-cols-4">
        <Stat label="Businesses" value={businesses.length} />
        <Stat label="Platform cost to date" value={money(costs.total_usd)} />
        <Stat label="Processed locally" value={`${costs.local_share_pct}%`} />
        <Stat label="Cloud spend" value={money(costs.by_tier.cloud ?? 0)} hint="telephony plus any cloud fallbacks" />
      </div>

      <Card title="Businesses" flush className="mb-8">
        {businesses.length === 0 ? (
          <Empty message="No businesses have been set up." />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Number</th>
                  <th scope="col">Time zone</th>
                  <th scope="col" className="num">Calls</th>
                  <th scope="col" className="num">Cost</th>
                  <th scope="col">Created</th>
                  <th scope="col"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {businesses.map((business) => (
                  <tr key={business.id}>
                    <td className="font-bold">{business.name}</td>
                    <td className="kv">{business.twilio_number ?? "—"}</td>
                    <td>{business.timezone}</td>
                    <td className="num">{business.call_count}</td>
                    <td className="num">{money(business.total_cost_usd)}</td>
                    <td className="text-secondary">{when(business.created_at)}</td>
                    <td className="text-right">
                      <button
                        className="btn btn-warning btn-sm"
                        onClick={() => {
                          setConfirming(business);
                          setTyped("");
                        }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {confirming && (
        <Card title={`Delete ${confirming.name}`} className="mb-8">
          <WarningText>
            This permanently deletes the business and every call, appointment, document, user and cost
            record belonging to it. It cannot be undone.
          </WarningText>
          <Field label="Type the business name to confirm" htmlFor="confirm-name">
            <input id="confirm-name" className="input input-medium" value={typed} onChange={(e) => setTyped(e.target.value)} />
          </Field>
          <div className="flex gap-3">
            <button className="btn btn-warning" disabled={typed !== confirming.name} onClick={() => remove(confirming)}>
              Delete this business
            </button>
            <button className="btn btn-secondary" onClick={() => setConfirming(null)}>
              Cancel
            </button>
          </div>
        </Card>
      )}

      <Card title="Set up a new business" description="Creates the business and its first administrator">
        <form onSubmit={provision} className="max-w-2xl">
          <div className="grid gap-x-6 sm:grid-cols-2">
            <Field label="Business name" htmlFor="name">
              <input id="name" className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Time zone" htmlFor="tz" hint="IANA name, for example Europe/London">
              <input id="tz" className="input" required value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
            </Field>
            <Field label="Administrator email" htmlFor="admin-email">
              <input id="admin-email" className="input" type="email" required value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} />
            </Field>
            <Field label="Administrator password" htmlFor="admin-password" hint="At least 10 characters">
              <input id="admin-password" className="input" type="password" required minLength={10} autoComplete="new-password" value={form.admin_password} onChange={(e) => setForm({ ...form, admin_password: e.target.value })} />
            </Field>
            <Field label="Twilio number (optional)" htmlFor="twilio" hint="E.164 format, for example +15551234567">
              <input id="twilio" className="input" value={form.twilio_number} onChange={(e) => setForm({ ...form, twilio_number: e.target.value })} />
            </Field>
            <Field label="Escalation phone (optional)" htmlFor="escalation" hint="Where calls are transferred when the receptionist cannot help">
              <input id="escalation" className="input" value={form.escalation_phone} onChange={(e) => setForm({ ...form, escalation_phone: e.target.value })} />
            </Field>
          </div>
          <button className="btn" type="submit" disabled={creating}>
            {creating ? "Setting up…" : "Set up business"}
          </button>
        </form>
      </Card>
    </div>
  );
}
