// Human formatting helpers (local timezone for display, per contract §9).

export function relTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 10) return 'just now';
  if (seconds < 60) return `${Math.floor(seconds)}s ago`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.floor(minutes)}m ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.floor(hours)}h ago`;
  const days = hours / 24;
  return `${Math.floor(days)}d ago`;
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  const s = Math.max(0, Math.floor(seconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

export function durationSince(iso: string | null | undefined): string {
  if (!iso) return '—';
  return fmtDuration((Date.now() - new Date(iso).getTime()) / 1000);
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}

export function fmtPct(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined) return '—';
  return `${(ratio * 100).toFixed(2)}%`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function intervalLabel(seconds: number): string {
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
}
