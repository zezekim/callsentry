"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Analytics } from "@/lib/api";
import { Card, Details, Empty, ErrorSummary, PageHeader, Spinner, Stat, money } from "@/components/ui";

/**
 * Categorical slots 1-3 of the validated light palette, checked against this
 * page's white card surface: lightness band, chroma floor, CVD separation and
 * normal-vision separation all pass. Slot 3 sits just under 3:1 contrast on
 * white, so every chart also ships its data as a table (the relief rule).
 *
 * Bound to the entity, never to rank - filtering a series out must not
 * repaint the survivors.
 */
const SERIES = {
  calls: "#2a78d6",
  bookings: "#eb6834",
  escalations: "#1baf7a",
} as const;

const MAGNITUDE = "#2a78d6";
const AXIS = "#505a5f";
const GRID = "#e5e6e7";
const SURFACE = "#ffffff";

function TooltipBox({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="border border-ink bg-white px-3 py-2 text-sm shadow-[2px_2px_0_#0b0c0c]">
      <div className="mb-1 font-bold">{label}</div>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 shrink-0" style={{ background: entry.color }} aria-hidden />
          <span className="text-secondary">{entry.name}</span>
          <span className="ml-auto tabular-nums">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api
      .get<Analytics>(`/analytics?days=${days}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [days]);

  if (error) return <ErrorSummary error={error} />;

  const volume = (data?.volume ?? []).map((point) => ({
    ...point,
    label: new Date(point.date).toLocaleDateString("en-GB", { day: "numeric", month: "short" }),
  }));
  const hours = (data?.peak_hours ?? []).map((point) => ({ ...point, label: hourLabel(point.hour) }));
  const costRows = Object.entries(data?.cost_by_category ?? {})
    .map(([category, values]) => ({
      category,
      cost: values.cost_usd ?? 0,
      operations: values.calls ?? 0,
      localOperations: values.local_calls ?? 0,
    }))
    .sort((a, b) => b.cost - a.cost);
  const hasVolume = volume.some((v) => v.calls > 0);

  return (
    <div>
      <PageHeader title="Reports" lede="Call volume, outcomes and cost over the selected period." />

      <fieldset className="mb-8">
        <legend className="label">Period</legend>
        <div className="flex flex-wrap gap-2">
          {[7, 30, 90].map((option) => (
            <button
              key={option}
              onClick={() => setDays(option)}
              aria-pressed={days === option}
              className={`btn btn-sm ${days === option ? "" : "btn-secondary"}`}
            >
              Last {option} days
            </button>
          ))}
        </div>
      </fieldset>

      {!data ? (
        <Spinner />
      ) : (
        <div className="space-y-8">
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Calls ending in a confirmed booking" value={`${data.booking_conversion_pct}%`} />
            <Stat label="Calls handed to a person" value={`${data.escalation_rate_pct}%`} />
            <Stat label="Average cost per call" value={money(data.avg_cost_per_call_usd)} hint="telephony plus any cloud fallbacks" />
          </div>

          <Card title="Daily call volume" description={`Calls, bookings and escalations per day over the last ${days} days`}>
            {!hasVolume ? (
              <Empty message="No calls in this period." />
            ) : (
              <>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={volume} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                      <CartesianGrid stroke={GRID} vertical={false} />
                      <XAxis dataKey="label" stroke={GRID} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} minTickGap={24} />
                      <YAxis stroke={GRID} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={false} allowDecimals={false} />
                      <Tooltip content={<TooltipBox />} cursor={{ stroke: AXIS, strokeDasharray: "3 3" }} />
                      <Legend wrapperStyle={{ fontSize: 13, color: AXIS, paddingTop: 8 }} iconType="plainline" />
                      {(["calls", "bookings", "escalations"] as const).map((key) => (
                        <Line
                          key={key}
                          type="monotone"
                          dataKey={key}
                          name={key[0].toUpperCase() + key.slice(1)}
                          stroke={SERIES[key]}
                          strokeWidth={2}
                          dot={false}
                          activeDot={{ r: 4, strokeWidth: 2, stroke: SURFACE }}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <Details summary="View this chart as a table">
                  <div className="table-scroll">
                    <table className="table">
                      <thead>
                        <tr>
                          <th scope="col">Date</th>
                          <th scope="col" className="num">Calls</th>
                          <th scope="col" className="num">Bookings</th>
                          <th scope="col" className="num">Escalations</th>
                          <th scope="col" className="num">Cost</th>
                        </tr>
                      </thead>
                      <tbody>
                        {volume.map((row) => (
                          <tr key={row.date}>
                            <td>{row.label}</td>
                            <td className="num">{row.calls}</td>
                            <td className="num">{row.bookings}</td>
                            <td className="num">{row.escalations}</td>
                            <td className="num">{money(row.cost_usd)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Details>
              </>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Calls by hour of day" description="Local time for the business">
              {hours.length === 0 ? (
                <Empty message="Not enough data yet." />
              ) : (
                <>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={hours} margin={{ top: 8, right: 12, bottom: 0, left: -20 }}>
                        <CartesianGrid stroke={GRID} vertical={false} />
                        <XAxis dataKey="label" stroke={GRID} tick={{ fill: AXIS, fontSize: 11 }} tickLine={false} interval={2} />
                        <YAxis stroke={GRID} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} axisLine={false} allowDecimals={false} />
                        <Tooltip content={<TooltipBox />} cursor={{ fill: "#f3f2f1" }} />
                        <Bar dataKey="calls" name="Calls" fill={MAGNITUDE} radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <Details summary="View this chart as a table">
                    <table className="table">
                      <thead>
                        <tr>
                          <th scope="col">Hour</th>
                          <th scope="col" className="num">Calls</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hours.map((row) => (
                          <tr key={row.hour}>
                            <td>{row.label}</td>
                            <td className="num">{row.calls}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Details>
                </>
              )}
            </Card>

            <Card title="Cost by component" description="Local providers record every operation at $0.00" flush>
              {costRows.length === 0 ? (
                <Empty message="No provider activity recorded yet." />
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Component</th>
                      <th scope="col" className="num">Operations</th>
                      <th scope="col" className="num">Local</th>
                      <th scope="col" className="num">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costRows.map((row) => {
                      const localPct = row.operations ? Math.round((row.localOperations / row.operations) * 100) : 100;
                      return (
                        <tr key={row.category}>
                          <td className="uppercase text-sm">{row.category}</td>
                          <td className="num">{row.operations}</td>
                          <td className="num">{localPct}%</td>
                          <td className="num">{money(row.cost)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </Card>
          </div>

          <Card title="Most common topics" description="Derived from call summaries" flush>
            {data.top_topics.length === 0 ? (
              <Empty message="No topics identified yet." />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Topic</th>
                    <th scope="col" className="num">Calls</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_topics.map((topic) => (
                    <tr key={topic.topic}>
                      <td>{topic.topic}</td>
                      <td className="num">{topic.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
