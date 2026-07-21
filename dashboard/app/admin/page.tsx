"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Empty, ErrorNote, Panel, Spinner, Stat, money, when } from "@/components/ui";

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

  const [form, setForm] = useState({
    name: "",
    timezone: "America/New_York",
    admin_email: "",
    admin_password: "",
    twilio_number: "",
    escalation_phone: "",
  });

  function load() {
    Promise.all([
      api.get<BusinessRow[]>("/admin/businesses"),
      api.get<PlatformCosts>("/admin/costs"),
    ])
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
      setNotice(`Provisioned ${form.name}.`);
      setForm({ ...form, name: "", admin_email: "", admin_password: "", twilio_number: "" });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Provisioning failed");
    } finally {
      setCreating(false);
    }
  }

  async function remove(business: BusinessRow) {
    // Irreversible and cascading - make the operator type the name.
    const typed = window.prompt(
      `This permanently deletes "${business.name}" and every call, appointment, ` +
        `document, and cost record belonging to it.\n\nType the business name to confirm:`,
    );
    if (typed !== business.name) return;

    setError(null);
    try {
      await api.delete(`/admin/businesses/${business.id}`);
      setNotice(`Deleted ${business.name}.`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (error && !businesses) return <ErrorNote error={error} />;
  if (!businesses || !costs) return <Spinner />;

  return (
    <div className="space-y-6">
      <ErrorNote error={error} />
      {notice && (
        <div className="rounded-md border border-emerald-900 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-300">
          {notice}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="Businesses" value={businesses.length} />
        <Stat label="Platform cost" value={money(costs.total_usd)} tone="good" />
        <Stat
          label="Served locally"
          value={`${costs.local_share_pct}%`}
          tone={costs.local_share_pct > 90 ? "good" : "warn"}
        />
        <Stat
          label="Cloud spend"
          value={money(costs.by_tier.cloud ?? 0)}
          hint="telephony plus any cloud fallbacks"
        />
      </div>

      <Panel title="Businesses">
        {businesses.length === 0 ? (
          <Empty message="No businesses provisioned." />
        ) : (
          <div className="table-scroll">
            <table className="w-full">
              <thead className="border-b border-edge">
                <tr>
                  <th className="th">Name</th>
                  <th className="th">Number</th>
                  <th className="th">Timezone</th>
                  <th className="th">Calls</th>
                  <th className="th">Cost</th>
                  <th className="th">Created</th>
                  <th className="th"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {businesses.map((business) => (
                  <tr key={business.id}>
                    <td className="td text-slate-100">{business.name}</td>
                    <td className="td font-mono text-muted">
                      {business.twilio_number ?? "—"}
                    </td>
                    <td className="td text-muted">{business.timezone}</td>
                    <td className="td font-mono">{business.call_count}</td>
                    <td className="td font-mono text-accent">
                      {money(business.total_cost_usd)}
                    </td>
                    <td className="td text-muted">{when(business.created_at)}</td>
                    <td className="td text-right">
                      <button
                        className="btn btn-danger px-2 py-1 text-xs"
                        onClick={() => remove(business)}
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
      </Panel>

      <Panel title="Provision a business" subtitle="Creates the tenant and its first admin user">
        <form onSubmit={provision} className="grid gap-4 p-4 sm:grid-cols-2">
          <div>
            <label className="label">Business name</label>
            <input
              className="input"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Timezone</label>
            <input
              className="input"
              required
              value={form.timezone}
              onChange={(e) => setForm({ ...form, timezone: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Admin email</label>
            <input
              className="input"
              type="email"
              required
              value={form.admin_email}
              onChange={(e) => setForm({ ...form, admin_email: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Admin password</label>
            <input
              className="input"
              type="password"
              required
              minLength={10}
              value={form.admin_password}
              onChange={(e) => setForm({ ...form, admin_password: e.target.value })}
            />
            <p className="mt-1 text-xs text-muted">Minimum 10 characters.</p>
          </div>
          <div>
            <label className="label">Twilio number (optional)</label>
            <input
              className="input font-mono"
              value={form.twilio_number}
              onChange={(e) => setForm({ ...form, twilio_number: e.target.value })}
              placeholder="+15551234567"
            />
          </div>
          <div>
            <label className="label">Escalation phone (optional)</label>
            <input
              className="input font-mono"
              value={form.escalation_phone}
              onChange={(e) => setForm({ ...form, escalation_phone: e.target.value })}
              placeholder="+15559876543"
            />
          </div>
          <div className="sm:col-span-2">
            <button className="btn btn-primary" type="submit" disabled={creating}>
              {creating ? "Provisioning…" : "Provision business"}
            </button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
