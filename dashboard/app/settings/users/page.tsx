"use client";

import { useEffect, useState } from "react";
import { api, type DashboardUser } from "@/lib/api";
import { useSession } from "@/components/shell";
import { Card, Empty, ErrorSummary, Field, Notice, Spinner, Tag, when } from "@/components/ui";

const MIN_PASSWORD = 10;

export default function UsersPage() {
  const session = useSession();
  const [users, setUsers] = useState<DashboardUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [form, setForm] = useState({ email: "", password: "", role: "admin" });
  const [creating, setCreating] = useState(false);

  const [resetting, setResetting] = useState<DashboardUser | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [removing, setRemoving] = useState<DashboardUser | null>(null);
  const [busy, setBusy] = useState(false);

  function load() {
    api
      .get<DashboardUser[]>("/settings/users")
      .then(setUsers)
      .catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    setNotice(null);
    try {
      const created = await api.post<DashboardUser>("/settings/users", form);
      setNotice(`${created.email} can now sign in.`);
      setForm({ email: "", password: "", role: "admin" });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add the user");
    } finally {
      setCreating(false);
    }
  }

  async function resetPassword(event: React.FormEvent) {
    event.preventDefault();
    if (!resetting) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.put(`/settings/users/${resetting.id}/password`, { password: newPassword });
      setNotice(`The password for ${resetting.email} has been changed.`);
      setResetting(null);
      setNewPassword("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change the password");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!removing) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.delete(`/settings/users/${removing.id}`);
      setNotice(`${removing.email} has been removed and can no longer sign in.`);
      setRemoving(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove the user");
    } finally {
      setBusy(false);
    }
  }

  if (error && !users) return <ErrorSummary error={error} />;
  if (!users) return <Spinner />;

  return (
    <div>
      <h2 className="h2 mb-6">Users</h2>
      <ErrorSummary error={error} />
      {notice && <Notice kind="success">{notice}</Notice>}

      <Card title="Who can sign in" description="Administrators have full access to this business; viewers can only look" flush className="mb-6">
        {users.length === 0 ? (
          <Empty message="No users." />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Email address</th>
                  <th scope="col">Role</th>
                  <th scope="col">Added</th>
                  <th scope="col"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>
                      {user.email}
                      {user.is_current_user && <span className="ml-2 text-sm text-secondary">(you)</span>}
                    </td>
                    <td><Tag value={user.role} /></td>
                    <td className="text-secondary">{when(user.created_at)}</td>
                    <td className="whitespace-nowrap text-right">
                      <button
                        className="btn btn-secondary btn-sm mr-2"
                        onClick={() => {
                          setResetting(user);
                          setRemoving(null);
                          setNewPassword("");
                        }}
                      >
                        Change password
                      </button>
                      <button
                        className="btn btn-warning btn-sm"
                        disabled={user.is_current_user || users.length <= 1}
                        title={user.is_current_user ? "You cannot remove your own account" : undefined}
                        onClick={() => {
                          setRemoving(user);
                          setResetting(null);
                        }}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {resetting && (
        <Card title={`Change password for ${resetting.email}`} className="mb-6">
          <form onSubmit={resetPassword} className="max-w-md">
            <Field label="New password" htmlFor="reset-password" hint={`At least ${MIN_PASSWORD} characters. Tell the user directly; it is not emailed.`}>
              <input
                id="reset-password"
                className="input"
                type="password"
                autoComplete="new-password"
                minLength={MIN_PASSWORD}
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </Field>
            <div className="flex gap-3">
              <button className="btn" type="submit" disabled={busy || newPassword.length < MIN_PASSWORD}>
                Change password
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setResetting(null)}>
                Cancel
              </button>
            </div>
          </form>
        </Card>
      )}

      {removing && (
        <Card title={`Remove ${removing.email}`} className="mb-6">
          <p className="mb-4">
            They will be signed out at their next request and will no longer be able to access this business.
            Call records and appointments are not affected.
          </p>
          <div className="flex gap-3">
            <button className="btn btn-warning" disabled={busy} onClick={remove}>
              Remove this user
            </button>
            <button className="btn btn-secondary" onClick={() => setRemoving(null)}>
              Cancel
            </button>
          </div>
        </Card>
      )}

      <Card title="Add a user">
        <form onSubmit={create} className="max-w-md">
          <Field label="Email address" htmlFor="new-email" hint="They will sign in with this">
            <input
              id="new-email"
              className="input"
              type="email"
              autoComplete="off"
              spellCheck={false}
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
          <Field label="Temporary password" htmlFor="new-password" hint={`At least ${MIN_PASSWORD} characters. They can change it from Your account.`}>
            <input
              id="new-password"
              className="input"
              type="password"
              autoComplete="new-password"
              minLength={MIN_PASSWORD}
              required
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </Field>
          <Field
            label="Role"
            htmlFor="new-role"
            hint="Viewers can see calls, appointments, the knowledge base and reports but cannot change anything. Administrators have full access to this business."
          >
            <select id="new-role" className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="admin">Administrator</option>
              <option value="viewer">Viewer (read-only)</option>
              {session?.role === "operator" && <option value="operator">Platform operator</option>}
            </select>
          </Field>
          <button className="btn" type="submit" disabled={creating}>
            {creating ? "Adding…" : "Add user"}
          </button>
        </form>
      </Card>
    </div>
  );
}
