"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/components/shell";
import { Card, ErrorSummary, Field, Notice, SummaryList, Tag } from "@/components/ui";

const MIN_PASSWORD = 10;

export default function AccountPage() {
  const session = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const mismatch = confirm.length > 0 && next !== confirm;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      setNotice("Your password has been changed. Use it the next time you sign in.");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change the password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2 className="h2 mb-6">Your account</h2>
      <ErrorSummary error={error} />
      {notice && <Notice kind="success">{notice}</Notice>}

      <Card title="Signed in as" className="mb-6">
        <SummaryList
          rows={[
            { key: "Email address", value: session?.email ?? "—" },
            { key: "Role", value: <Tag value={session?.role} /> },
          ]}
        />
      </Card>

      <Card title="Change your password">
        <form onSubmit={submit} className="max-w-md">
          <Field label="Current password" htmlFor="current">
            <input id="current" className="input" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Field label="New password" htmlFor="next" hint={`At least ${MIN_PASSWORD} characters. Longer passphrases are supported.`}>
            <input id="next" className="input" type="password" autoComplete="new-password" minLength={MIN_PASSWORD} required value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
          <Field label="Confirm new password" htmlFor="confirm" error={mismatch ? "The passwords do not match" : null}>
            <input id="confirm" className={`input ${mismatch ? "input-error" : ""}`} type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <button className="btn" type="submit" disabled={busy || mismatch || next.length < MIN_PASSWORD || !current}>
            {busy ? "Changing…" : "Change password"}
          </button>
        </form>
      </Card>
    </div>
  );
}
