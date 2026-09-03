"use client";

/**
 * Thin API client.
 *
 * The JWT lives in localStorage rather than a cookie because the dashboard is
 * a pure SPA against a separate API origin in dev; there is no server-rendered
 * authenticated surface that would need it sent automatically.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "callsentry.token";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${BASE}${path}`, { ...init, headers });

  if (response.status === 401) {
    // The token expired or was revoked. Drop it and bounce to login rather
    // than letting every subsequent panel render its own error.
    clearToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError("Session expired", 401);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body; keep the status text */
    }
    throw new ApiError(typeof detail === "string" ? detail : "Request failed", response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  put: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T,>(path: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(path, { method: "POST", body: form });
  },
  /** Absolute URL, for links and audio elements that bypass the fetch wrapper. */
  url: (path: string) => `${BASE}${path}`,
  async blob(path: string, body: unknown): Promise<Blob> {
    const token = getToken();
    const response = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new ApiError("Request failed", response.status);
    return response.blob();
  },
};

// --- Shared response types -------------------------------------------------

export interface CallSummary {
  id: string;
  caller_number: string;
  duration_seconds: number;
  outcome: string;
  sentiment: string | null;
  escalated: boolean;
  cost_usd: number;
  created_at: string;
}

export interface CallDetail extends CallSummary {
  transcript: string | null;
  summary: string | null;
  recording_url: string | null;
  escalation_reason: string | null;
  provider_log: ProviderAttempt[];
}

export interface ProviderAttempt {
  component: string;
  provider: string;
  tier: string;
  ok: boolean;
  latency_ms: number;
  detail?: string;
}

export interface CallStats {
  calls_today: number;
  bookings_today: number;
  escalations_today: number;
  avg_duration_seconds: number;
  cost_today_usd: number;
  cost_all_time_usd: number;
  local_share_pct: number;
  sentiment: Record<string, number>;
  outcomes: Record<string, number>;
}

export interface Appointment {
  id: string;
  call_id: string | null;
  caller_name: string;
  caller_phone: string;
  caller_email: string | null;
  reason: string | null;
  scheduled_at: string;
  timezone: string;
  status: string;
  cal_com_event_id: string | null;
  reminder_sent: boolean;
  confirmation_sent: boolean;
  created_at: string;
}

export interface KBDocument {
  id: string;
  filename: string;
  content_type: string;
  chunk_count: number;
  indexed: boolean;
  created_at: string;
}

export interface ProviderRow {
  provider: string;
  tier: string;
  healthy: boolean;
  detail: string;
  unit: string;
  cost_per_unit: number;
}

export interface ProviderSnapshot {
  local_only: boolean;
  components: Record<string, ProviderRow[]>;
}

export interface BusinessSettings {
  business_id: string;
  name: string;
  timezone: string;
  business_hours: Record<string, [string, string] | null>;
  escalation_phone: string | null;
  after_hours_message: string | null;
  greeting_override: string | null;
  twilio_number: string | null;
  voice_id: string;
  cal_com_event_type_id: string | null;
  cal_com_api_key: string;
  local_only: boolean;
}

export interface Analytics {
  volume: { date: string; calls: number; bookings: number; escalations: number; cost_usd: number }[];
  peak_hours: { hour: number; calls: number }[];
  booking_conversion_pct: number;
  escalation_rate_pct: number;
  avg_cost_per_call_usd: number;
  cost_by_category: Record<string, Record<string, number>>;
  top_topics: { topic: string; count: number }[];
}

export interface DashboardUser {
  id: string;
  email: string;
  role: string;
  created_at: string;
  is_current_user: boolean;
}

export interface PlatformField {
  key: string;
  env: string;
  group: string;
  label: string;
  kind: "text" | "secret" | "bool" | "int" | "float" | "url";
  help: string;
  restart_required: boolean;
  value: string;
  is_set: boolean;
  overridden: boolean;
  env_value: string;
  updated_at: string | null;
}

export interface PlatformSettings {
  can_edit: boolean;
  groups: { id: string; label: string }[];
  fields: PlatformField[];
}
