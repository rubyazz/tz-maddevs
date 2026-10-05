// Public status page: /status/:slug — no auth, only what the owner published.

import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Activity } from 'lucide-react';
import { api } from '../api/client';
import type { PublicStatus } from '../api/types';
import { StatusDot } from '../components/Status';
import { usePublicEvents } from '../lib/sse';
import { fmtPct, relTime } from '../lib/format';

const BANNER: Record<string, { color: string; label: string }> = {
  operational: { color: 'bg-status-up/15 text-status-up', label: 'All systems operational' },
  degraded: { color: 'bg-status-warn/15 text-status-warn', label: 'Degraded performance' },
  partial_outage: { color: 'bg-status-partial/15 text-status-partial', label: 'Partial outage' },
  major_outage: { color: 'bg-status-down/15 text-status-down', label: 'Major outage' },
};

export default function PublicStatusPage() {
  const { slug } = useParams<{ slug: string }>();
  usePublicEvents(slug); // live updates without login
  const { data, error, isLoading } = useQuery({
    queryKey: ['public', slug],
    queryFn: () => api<PublicStatus>(`/api/public/${slug}`),
    retry: false,
  });

  if (isLoading) {
    return <div className="grid min-h-screen place-items-center text-ink-muted">Loading…</div>;
  }
  if (error || !data) {
    return (
      <div className="grid min-h-screen place-items-center px-4 text-center">
        <div>
          <p className="text-lg font-semibold">Status page not found</p>
          <p className="mt-1 text-sm text-ink-muted">This link is invalid or was unpublished.</p>
        </div>
      </div>
    );
  }

  const banner = BANNER[data.status] ?? BANNER.operational;

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-6 flex items-center gap-2">
        <span className="grid size-7 place-items-center rounded-lg bg-status-info/15 text-status-info">
          <Activity size={16} />
        </span>
        <span className="text-lg font-semibold tracking-tight">Pulse</span>
      </div>

      <h1 className="text-2xl font-semibold">{data.group.name}</h1>
      {data.group.description ? (
        <p className="mt-1 text-sm text-ink-secondary">{data.group.description}</p>
      ) : null}

      <div className={`mt-5 rounded-xl px-5 py-4 text-base font-medium ${banner.color}`}>
        {banner.label}
      </div>

      <ul className="mt-6 divide-y divide-edge/60 rounded-xl border border-edge bg-surface">
        {data.checks.map((check) => (
          <li key={check.id} className="flex items-center gap-3 px-5 py-3.5 text-sm">
            <StatusDot state={check.state} />
            <span className="flex-1 font-medium">{check.name}</span>
            <span className="num text-xs text-ink-muted">{fmtPct(check.uptime_24h)} 24h</span>
            <span className="w-24 text-right text-xs text-ink-muted">
              {relTime(check.last_checked_at)}
            </span>
          </li>
        ))}
        {data.checks.length === 0 ? (
          <li className="px-5 py-6 text-center text-sm text-ink-muted">
            Nothing published for this page yet.
          </li>
        ) : null}
      </ul>

      <p className="mt-6 text-center text-xs text-ink-muted">
        Updates live · Powered by Pulse
      </p>
    </div>
  );
}
