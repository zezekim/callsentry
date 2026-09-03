"use client";

import { useEffect, useState } from "react";
import { api, type Appointment } from "@/lib/api";
import { Card, Empty, ErrorSummary, PageHeader, Spinner, Tag } from "@/components/ui";

function dayKey(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone,
  });
}

function timeOf(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone });
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

  if (error && !appointments) return <ErrorSummary error={error} />;
  if (!appointments) return <Spinner />;

  const grouped = appointments.reduce<Record<string, Appointment[]>>((acc, appointment) => {
    const key = dayKey(appointment.scheduled_at, appointment.timezone);
    (acc[key] ??= []).push(appointment);
    return acc;
  }, {});

  return (
    <div>
      <PageHeader
        title="Appointments"
        lede="Bookings made by the receptionist. Where Cal.com is connected they are held in that calendar as well."
      />
      <ErrorSummary error={error} />

      {appointments.length === 0 ? (
        <Card>
          <Empty
            message="There are no upcoming appointments."
            hint="Connect Cal.com under Settings so the receptionist can offer real availability."
          />
        </Card>
      ) : (
        <div className="space-y-8">
          {Object.entries(grouped).map(([day, items]) => (
            <section key={day}>
              <h2 className="h2 mb-3">{day}</h2>
              <div className="table-scroll card">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col" className="w-20">Time</th>
                      <th scope="col">Caller</th>
                      <th scope="col">Reason</th>
                      <th scope="col">Status</th>
                      <th scope="col">Calendar</th>
                      <th scope="col"><span className="sr-only">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((appointment) => (
                      <tr key={appointment.id}>
                        <td className="tabular-nums">{timeOf(appointment.scheduled_at, appointment.timezone)}</td>
                        <td>
                          <div className="font-bold">{appointment.caller_name}</div>
                          <div className="kv text-secondary">{appointment.caller_phone}</div>
                          {appointment.confirmation_sent && (
                            <div className="text-xs text-secondary">Confirmation SMS sent</div>
                          )}
                        </td>
                        <td>{appointment.reason ?? <span className="text-secondary">Not given</span>}</td>
                        <td><Tag value={appointment.status} /></td>
                        <td>
                          {appointment.cal_com_event_id ? (
                            <Tag value="in Cal.com" tone="tag-blue" />
                          ) : (
                            <Tag value="local only" tone="tag-grey" />
                          )}
                        </td>
                        <td className="whitespace-nowrap text-right">
                          {appointment.status === "confirmed" && (
                            <>
                              <button
                                className="btn btn-secondary btn-sm mr-2"
                                disabled={busy === appointment.id}
                                onClick={() => setStatus(appointment.id, "no_show")}
                              >
                                Mark no-show
                              </button>
                              <button
                                className="btn btn-warning btn-sm"
                                disabled={busy === appointment.id}
                                onClick={() => setStatus(appointment.id, "cancelled")}
                              >
                                Cancel
                              </button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
