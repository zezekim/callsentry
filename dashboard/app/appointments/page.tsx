"use client";

import { useEffect, useState } from "react";
import { api, type Appointment } from "@/lib/api";
import { Badge, Empty, ErrorNote, Panel, Spinner } from "@/components/ui";

function dayKey(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
    timeZone,
  });
}

function timeOf(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  });
}

export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  function load() {
    api
      .get<Appointment[]>("/appointments/calendar")
      .then(setAppointments)
      .catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function setStatus(id: string, status: string) {
    setBusy(id);
    setError(null);
    try {
      await api.patch(`/appointments/${id}/status`, { status });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setBusy(null);
    }
  }

  if (error && !appointments) return <ErrorNote error={error} />;
  if (!appointments) return <Spinner />;

  // Group by local day so the page reads like a calendar, not a flat list.
  const grouped = appointments.reduce<Record<string, Appointment[]>>((acc, appointment) => {
    const key = dayKey(appointment.scheduled_at, appointment.timezone);
    (acc[key] ??= []).push(appointment);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <ErrorNote error={error} />

      <Panel
        title="Appointments"
        subtitle="Booked by the receptionist and synced with Cal.com"
      >
        {appointments.length === 0 ? (
          <Empty
            message="No appointments booked yet."
            hint="Connect Cal.com in Settings so the agent can check real availability."
          />
        ) : (
          <div className="divide-y divide-edge">
            {Object.entries(grouped).map(([day, items]) => (
              <div key={day}>
                <div className="bg-slate-900/60 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  {day}
                </div>
                {items.map((appointment) => (
                  <div
                    key={appointment.id}
                    className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 hover:bg-slate-900/40"
                  >
                    <span className="w-20 font-mono text-sm text-slate-100">
                      {timeOf(appointment.scheduled_at, appointment.timezone)}
                    </span>
                    <div className="min-w-[12rem] flex-1">
                      <div className="text-sm text-slate-200">{appointment.caller_name}</div>
                      <div className="font-mono text-xs text-muted">
                        {appointment.caller_phone}
                      </div>
                      {appointment.reason && (
                        <div className="mt-0.5 text-xs text-muted">{appointment.reason}</div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 text-xs">
                      <Badge value={appointment.status} />
                      {appointment.cal_com_event_id ? (
                        <span className="chip bg-sky-950 text-sky-300">cal.com synced</span>
                      ) : (
                        <span className="chip bg-amber-950 text-amber-300">local only</span>
                      )}
                      {appointment.confirmation_sent && (
                        <span className="text-muted">SMS sent</span>
                      )}
                    </div>

                    {appointment.status === "confirmed" && (
                      <div className="flex gap-2">
                        <button
                          className="btn px-2 py-1 text-xs"
                          disabled={busy === appointment.id}
                          onClick={() => setStatus(appointment.id, "no_show")}
                        >
                          No-show
                        </button>
                        <button
                          className="btn btn-danger px-2 py-1 text-xs"
                          disabled={busy === appointment.id}
                          onClick={() => setStatus(appointment.id, "cancelled")}
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
