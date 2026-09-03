"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type PlatformField, type PlatformSettings } from "@/lib/api";
import { Card, ErrorSummary, Inset, Notice, Spinner, Tag } from "@/components/ui";

/**
 * One form for every runtime-editable platform setting. Fields start empty
 * and only the ones the operator touches are sent, so saving never overwrites
 * a value with a stale copy. Clearing an override restores the environment.
 */
export default function PlatformSettingsPage() {
  const [data, setData] = useState<PlatformSettings | null>(null);
  const [draft, setDraft] = useState<Record<string, string | null>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .get<PlatformSettings>("/settings/platform")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const byGroup = useMemo(() => {
    const map: Record<string, PlatformField[]> = {};
    for (const field of data?.fields ?? []) (map[field.group] ??= []).push(field);
    return map;
  }, [data]);

  const dirty = Object.keys(draft).length;

  function edit(key: string, value: string | null) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function discard(key: string) {
    setDraft((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!dirty) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const values = Object.fromEntries(
        Object.entries(draft).filter(([, v]) => v === null || v.trim() !== ""),
      );
      const updated = await api.put<PlatformSettings>("/settings/platform", { values });
      setData(updated);
      setDraft({});
      const restart = updated.fields.some((f) => f.restart_required && f.key in values);
      setNotice(
        restart
          ? "Settings saved. At least one of them only takes effect after the app service is restarted."
          : "Settings saved and in effect.",
      );
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (error && !data) return <ErrorSummary error={error} />;
  if (!data) return <Spinner />;

  return (
    <form onSubmit={save}>
      <h2 className="h2 mb-6">Platform configuration</h2>
      <ErrorSummary error={error} />
      {notice && <Notice kind="success">{notice}</Notice>}

      {!data.can_edit && (
        <Inset>
          These settings apply to every business on this installation, so only a platform operator can change
          them. You are signed in as an administrator and can view them.
        </Inset>
      )}
      {data.can_edit && (
        <Inset>
          Values set here override the environment for the running service and are kept across restarts.
          Secret values are encrypted at rest and never shown again in full. Leave a field blank to keep its
          current value, or use <strong>Use environment value</strong> to remove an override.
        </Inset>
      )}

      <div className="space-y-6">
        {data.groups.map((group) => {
          const fields = byGroup[group.id] ?? [];
          if (fields.length === 0) return null;
          return (
            <Card key={group.id} title={group.label}>
              {fields.map((field) => (
                <FieldRow
                  key={field.key}
                  field={field}
                  value={draft[field.key]}
                  editable={data.can_edit}
                  onChange={(v) => edit(field.key, v)}
                  onDiscard={() => discard(field.key)}
                />
              ))}
            </Card>
          );
        })}
      </div>

      {data.can_edit && (
        <div className="sticky bottom-0 mt-8 flex flex-wrap items-center gap-4 border-t border-border bg-white py-4">
          <button className="btn" type="submit" disabled={saving || dirty === 0}>
            {saving ? "Saving…" : "Save changes"}
          </button>
          <span className="text-sm text-secondary">
            {dirty === 0 ? "No unsaved changes." : `${dirty} unsaved ${dirty === 1 ? "change" : "changes"}.`}
          </span>
        </div>
      )}
    </form>
  );
}

function FieldRow({
  field,
  value,
  editable,
  onChange,
  onDiscard,
}: {
  field: PlatformField;
  value: string | null | undefined;
  editable: boolean;
  onChange: (value: string | null) => void;
  onDiscard: () => void;
}) {
  const touched = value !== undefined;
  const clearing = value === null;
  const id = `pf-${field.key}`;
  const current = field.value || (field.kind === "secret" ? "Not set" : "Not set");

  let control: React.ReactNode;
  if (clearing) {
    control = (
      <p className="text-sm">
        Will revert to the environment value{" "}
        <span className="kv">{field.env_value || "(not set)"}</span>.
      </p>
    );
  } else if (field.kind === "bool") {
    control = (
      <select id={id} className="input input-narrow" disabled={!editable} value={value ?? field.value} onChange={(e) => onChange(e.target.value)}>
        <option value="true">On</option>
        <option value="false">Off</option>
      </select>
    );
  } else if (field.kind === "secret") {
    control = (
      <input
        id={id}
        className="input input-medium kv"
        type="password"
        autoComplete="new-password"
        disabled={!editable}
        placeholder={field.value ? `Currently ${field.value}` : "Not set"}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  } else {
    control = (
      <input
        id={id}
        className={`input ${field.kind === "int" || field.kind === "float" ? "input-narrow" : "input-medium"} ${field.kind === "url" ? "kv" : ""}`}
        type="text"
        inputMode={field.kind === "int" || field.kind === "float" ? "decimal" : undefined}
        disabled={!editable}
        value={value ?? field.value}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <div className={`form-group border-b border-border pb-5 last:border-b-0 last:pb-0 ${touched ? "form-group-error border-l-brand" : ""}`}>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <label className="label mb-0" htmlFor={id}>{field.label}</label>
        {field.overridden ? <Tag value="set here" tone="tag-blue" /> : <Tag value="from environment" tone="tag-grey" />}
        {field.restart_required && <Tag value="restart required" tone="tag-yellow" />}
      </div>
      <span className="hint">
        {field.help} Environment variable <span className="kv">{field.env}</span>.
        {field.kind === "secret" && field.value && <> Current value ends in <span className="kv">{field.value.slice(-4)}</span>.</>}
        {field.kind !== "secret" && field.overridden && field.env_value && (
          <> Environment value <span className="kv">{field.env_value}</span>.</>
        )}
      </span>
      <div className="flex flex-wrap items-center gap-3">
        {control}
        {editable && touched && (
          <button type="button" className="link text-sm" onClick={onDiscard}>
            Discard change
          </button>
        )}
        {editable && !touched && field.overridden && (
          <button type="button" className="link text-sm" onClick={() => onChange(null)}>
            Use environment value
          </button>
        )}
        {!editable && field.kind === "secret" && <span className="text-sm text-secondary">{current}</span>}
      </div>
    </div>
  );
}
