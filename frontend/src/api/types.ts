// API shapes — mirror docs/CONTRACT.md §4/§5.

export type CheckState = 'up' | 'down' | 'unknown';
export type GroupStatus =
  | 'operational'
  | 'degraded'
  | 'partial_outage'
  | 'major_outage';

export interface User {
  id: string;
  email: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface AlertEmail {
  id: string;
  email: string;
}

export interface IncidentBrief {
  id: string;
  started_at: string;
}

export interface Check {
  id: string;
  group_id: string;
  name: string;
  url: string;
  interval_seconds: number;
  timeout_seconds: number;
  expected_status: number;
  expected_body: string | null;
  failure_threshold: number;
  paused: boolean;
  show_on_public: boolean;
  state: CheckState;
  consecutive_failures: number;
  last_checked_at: string | null;
  last_ok: boolean | null;
  last_status_code: number | null;
  last_response_time_ms: number | null;
  last_error: string | null;
  open_incident: IncidentBrief | null;
  uptime_24h: number | null;
}

export interface GroupView {
  id: string;
  name: string;
  description: string;
  public_slug: string | null;
  status: GroupStatus;
  alert_emails: AlertEmail[];
  checks: Check[];
}

export interface Overview {
  groups: GroupView[];
}

export interface Incident {
  id: string;
  started_at: string;
  ended_at: string | null;
  duration_s: number | null;
  last_error: string | null;
}

export interface CheckDetail extends Check {
  group: { id: string; name: string };
  incidents: Incident[];
}

export interface HistoryBucket {
  ts: string;
  count: number;
  ok_count: number;
  uptime_ratio: number | null;
  avg_response_ms: number | null;
  max_response_ms: number | null;
}

export interface HistorySummary {
  checks: number;
  ok: number;
  uptime: number | null;
  avg_response_ms: number | null;
  p95_response_ms: number | null;
}

export interface History {
  period: 'day' | 'week' | 'month';
  buckets: HistoryBucket[];
  summary: HistorySummary;
  incidents: Incident[];
}

export interface CheckResult {
  id: number;
  checked_at: string;
  ok: boolean;
  status_code: number | null;
  response_time_ms: number | null;
  error: string | null;
}

export interface ResultsPage {
  items: CheckResult[];
  next_before: string | null;
}

export interface MaintenanceWindow {
  id: string;
  check_id: string | null;
  group_id: string | null;
  starts_at: string;
  ends_at: string;
  note: string;
  check_name: string | null;
  group_name: string | null;
}

export interface MailboxItem {
  id: string;
  group_id: string | null;
  check_id: string | null;
  to_email: string;
  subject: string;
  body: string;
  kind: 'down' | 'up' | 'test';
  status: 'sent' | 'suppressed';
  suppress_reason: string | null;
  created_at: string;
}

export interface PublicStatus {
  group: { name: string; description: string };
  status: GroupStatus;
  checks: Array<{
    id: string;
    name: string;
    state: CheckState | 'paused';
    last_checked_at: string | null;
    uptime_24h: number | null;
  }>;
}

export type Period = 'day' | 'week' | 'month';
