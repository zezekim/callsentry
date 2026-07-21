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
import { Empty, ErrorNote, Panel, Spinner, Stat, money } from "@/components/ui";

/**
 * Categorical slots 1-3, stepped for a dark surface and validated against
 * this dashboard's panel colour (#131a23): lightness band, chroma floor,
 * CVD separation (worst adjacent deutan ΔE 9.4), normal-vision separation
 * (ΔE 26.5), and >= 3:1 contrast all pass.
 *
 * Assigned in fixed order and bound to the entity, never to rank - filtering
 * a series out must not repaint the survivors.
 */
const SERIES = {
  calls: "#3987e5",
  bookings: "#d95926",
  escalations: "#199e70",
} as const;

/** Single hue for magnitude-only charts. */
const MAGNITUDE = "#3987e5";

const AXIS = "#8b9bb0";
const GRID = "#1f2a37";
const SURFACE = "#131a23";

function TooltipBox({
  active,
  payload,
  label,
  format,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string | number;
  format?: (value: number, name: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-edge bg-ink px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-slate-200">{label}</div>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2">
          <span
            className="h-2 w-2 shrink-0 rounded-sm"
            style={{ background: entry.color }}
            aria-hidden
          />
          <span className="text-muted">{entry.name}</span>
          <span className="ml-auto font-mono text-slate-200">
            {format ? format(entry.value, entry.name) : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

function hourLabel(hour: number): string {
  if (hour === 0) return "12a";
  if (hour === 12) return "12p";
  return hour < 12 ? `${hour}a` : `${hour - 12}p`;
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

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Spinner />;

  const volume = data.volume.map((point) => ({
    ...point,
    label: new Date(point.date).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    }),
  }));

  const hours = data.peak_hours.map((point) => ({
    ...point,
    label: hourLabel(point.hour),
  }));

  const costRows = Object.entries(data.cost_by_category)
    .map(([category, values]) => ({
      category,
      cost: values.cost_usd ?? 0,
      operations: values.calls ?? 0,
      localOperations: values.local_calls ?? 0,
    }))
    .sort((a, b) => b.cost - a.cost);

  const hasVolume = volume.some((v) => v.calls > 0);

  return (
    <div className="space-y-6">
      {/* Filters sit in one row above the charts. */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-muted">Range</span>
        {[7, 30, 90].map((option) => (
          <button
            key={option}
            onClick={() => setDays(option)}
            className={`btn px-2.5 py-1 text-xs ${
              days === option ? "border-emerald-600 text-emerald-300" : ""
            }`}
          >
            {option} days
          </button>
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          label="Booking conversion"
          value={`${data.booking_conversion_pct}%`}
          tone="good"
          hint="calls that ended in a confirmed appointment"
        />
        <Stat
          label="Escalation rate"
          value={`${data.escalation_rate_pct}%`}
          tone={data.escalation_rate_pct > 25 ? "warn" : "default"}
          hint="calls handed to a human"
        />
        <Stat
          label="Avg cost per call"
          value={money(data.avg_cost_per_call_usd)}
          tone="good"
          hint="telephony plus any cloud fallbacks"
        />
      </div>

      <Panel title="Call volume" subtitle={`Daily totals over the last ${days} days`}>
        {!hasVolume ? (
          <Empty message="No calls in this range yet." />
        ) : (
          <div className="h-72 p-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={volume} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke={GRID}
                  tick={{ fill: AXIS, fontSize: 11 }}
                  tickLine={false}
                  minTickGap={24}
                />
                <YAxis
                  stroke={GRID}
                  tick={{ fill: AXIS, fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  content={<TooltipBox />}
                  cursor={{ stroke: AXIS, strokeDasharray: "3 3" }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12, color: AXIS, paddingTop: 8 }}
                  iconType="plainline"
                />
                {(["calls", "bookings", "escalations"] as const).map((key) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    name={key[0].toUpperCase() + key.slice(1)}
                    stroke={SERIES[key]}
                    strokeWidth={2}
                    dot={false}
                    // 8px marker with a 2px surface ring, so overlapping
                    // series stay separable where lines cross.
                    activeDot={{ r: 4, strokeWidth: 2, stroke: SURFACE }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Peak call hours" subtitle="When callers actually ring, local time">
          {hours.length === 0 ? (
            <Empty message="Not enough data yet." />
          ) : (
            <div className="h-64 p-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={hours} margin={{ top: 8, right: 12, bottom: 0, left: -20 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis
                    dataKey="label"
                    stroke={GRID}
                    tick={{ fill: AXIS, fontSize: 11 }}
                    tickLine={false}
                    interval={1}
                  />
                  <YAxis
                    stroke={GRID}
                    tick={{ fill: AXIS, fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip content={<TooltipBox />} cursor={{ fill: "#1f2a3755" }} />
                  {/* Rounded data-end anchored to the baseline. */}
                  <Bar dataKey="calls" name="Calls" fill={MAGNITUDE} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel
          title="Cost by component"
          subtitle="Local providers record every operation at $0.00"
        >
          {costRows.length === 0 ? (
            <Empty message="No provider activity recorded yet." />
          ) : (
            <div className="divide-y divide-edge">
              {costRows.map((row) => {
                const localPct = row.operations
                  ? Math.round((row.localOperations / row.operations) * 100)
                  : 100;
                return (
                  <div key={row.category} className="px-4 py-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="uppercase tracking-wide text-muted">{row.category}</span>
                      <span
                        className={`font-mono ${row.cost === 0 ? "text-accent" : "text-slate-200"}`}
                      >
                        {money(row.cost)}
                      </span>
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full rounded-full bg-emerald-500"
                        style={{ width: `${localPct}%` }}
                      />
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      {row.operations} operations · {localPct}% served locally
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      </div>

      {/* A ranked list of a handful of labels is not a chart. */}
      <Panel title="Most common topics" subtitle="Derived from call summaries">
        {data.top_topics.length === 0 ? (
          <Empty message="No topics identified yet." />
        ) : (
          <div className="flex flex-wrap gap-2 p-4">
            {data.top_topics.map((topic) => (
              <span
                key={topic.topic}
                className="chip bg-slate-800 text-slate-300"
                title={`${topic.count} calls mentioned this`}
              >
                {topic.topic}
                <span className="ml-1.5 font-mono text-muted">{topic.count}</span>
              </span>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
