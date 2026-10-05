// Status presentation primitives. A status color is never the only carrier:
// every badge pairs the dot with a text label (contract §9 / dataviz rules).

import type { CheckState, GroupStatus } from '../api/types';

const CHECK_COLORS: Record<string, string> = {
  up: 'bg-status-up',
  down: 'bg-status-down',
  unknown: 'bg-status-unknown',
  paused: 'bg-status-warn',
};

const CHECK_LABELS: Record<string, string> = {
  up: 'Up',
  down: 'Down',
  unknown: 'Unknown',
  paused: 'Paused',
};

export function StatusDot({ state }: { state: CheckState | 'paused' }) {
  return (
    <span
      className={`inline-block size-2.5 shrink-0 rounded-full ${CHECK_COLORS[state] ?? CHECK_COLORS.unknown}`}
      aria-hidden
    />
  );
}

export function StateBadge({ state, failing }: { state: CheckState | 'paused'; failing?: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-secondary">
      <StatusDot state={state} />
      {CHECK_LABELS[state] ?? 'Unknown'}
      {failing ? <span className="text-ink-muted">({failing})</span> : null}
    </span>
  );
}

const GROUP_STYLES: Record<GroupStatus, { color: string; label: string }> = {
  operational: { color: 'text-status-up', label: 'Operational' },
  degraded: { color: 'text-status-warn', label: 'Degraded' },
  partial_outage: { color: 'text-status-partial', label: 'Partial outage' },
  major_outage: { color: 'text-status-down', label: 'Major outage' },
};

export function GroupStatusBadge({ status }: { status: GroupStatus }) {
  const { color, label } = GROUP_STYLES[status] ?? GROUP_STYLES.operational;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${color}`}>
      <StatusDot state={status === 'operational' ? 'up' : status === 'degraded' ? 'unknown' : 'down'} />
      {label}
    </span>
  );
}
