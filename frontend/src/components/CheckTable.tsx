// The live checks table used on the dashboard and group page.

import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Pause, Play, Trash2, Zap } from 'lucide-react';
import { api } from '../api/client';
import type { Check } from '../api/types';
import { StateBadge } from './Status';
import { durationSince, fmtMs, fmtPct, intervalLabel, relTime } from '../lib/format';

export function CheckTable({ checks }: { checks: Check[] }) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['overview'] });
    queryClient.invalidateQueries({ queryKey: ['check'] });
  };

  const runMutation = useMutation({
    mutationFn: (id: string) => api<Check>(`/api/checks/${id}/run`, { method: 'POST' }),
    onSuccess: invalidate,
  });
  const toggleMutation = useMutation({
    mutationFn: (check: Check) =>
      api<Check>(`/api/checks/${check.id}/${check.paused ? 'resume' : 'pause'}`, { method: 'POST' }),
    onSuccess: invalidate,
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api<void>(`/api/checks/${id}`, { method: 'DELETE' }),
    onSuccess: invalidate,
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-sm">
        <thead>
          <tr className="border-b border-edge text-left text-xs text-ink-muted">
            <th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 pr-4 font-medium">Check</th>
            <th className="py-2 pr-4 font-medium">Response</th>
            <th className="py-2 pr-4 font-medium">Last check</th>
            <th className="py-2 pr-4 font-medium">Downtime</th>
            <th className="py-2 pr-4 font-medium">24h uptime</th>
            <th className="py-2 pr-4 font-medium">Interval</th>
            <th className="py-2 pr-4 font-medium">Public</th>
            <th className="py-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((check) => (
            <tr key={check.id} className="border-b border-edge/60 hover:bg-white/[0.02]">
              <td className="py-2.5 pr-4">
                <StateBadge
                  state={check.paused ? 'paused' : check.state}
                  failing={
                    !check.paused && check.state === 'up' && check.consecutive_failures > 0
                      ? check.consecutive_failures
                      : undefined
                  }
                />
              </td>
              <td className="py-2.5 pr-4">
                <Link
                  to={`/checks/${check.id}`}
                  className="font-medium text-ink-primary hover:text-status-info"
                >
                  {check.name}
                </Link>
                <p className="max-w-[280px] truncate text-xs text-ink-muted">{check.url}</p>
                {check.state === 'up' && check.consecutive_failures > 0 && (
                  <p className="text-xs text-status-warn">
                    failing {check.consecutive_failures}/{check.failure_threshold}
                  </p>
                )}
              </td>
              <td className="num py-2.5 pr-4 text-ink-secondary">{fmtMs(check.last_response_time_ms)}</td>
              <td className="py-2.5 pr-4 text-ink-secondary">{relTime(check.last_checked_at)}</td>
              <td className="py-2.5 pr-4 text-ink-secondary">
                {check.open_incident ? (
                  <span className="text-status-down">{durationSince(check.open_incident.started_at)}</span>
                ) : (
                  '—'
                )}
              </td>
              <td className="num py-2.5 pr-4 text-ink-secondary">{fmtPct(check.uptime_24h)}</td>
              <td className="py-2.5 pr-4 text-ink-secondary">{intervalLabel(check.interval_seconds)}</td>
              <td className="py-2.5 pr-4 text-ink-secondary">{check.show_on_public ? 'Yes' : 'No'}</td>
              <td className="py-2.5">
                <div className="flex items-center gap-1">
                  <button
                    title="Run now"
                    disabled={runMutation.isPending && runMutation.variables === check.id}
                    onClick={() => runMutation.mutate(check.id)}
                    className="rounded p-1.5 text-ink-muted hover:bg-white/5 hover:text-status-info disabled:opacity-40"
                  >
                    <Zap size={14} />
                  </button>
                  <button
                    title={check.paused ? 'Resume' : 'Pause'}
                    onClick={() => toggleMutation.mutate(check)}
                    className="rounded p-1.5 text-ink-muted hover:bg-white/5 hover:text-status-warn"
                  >
                    {check.paused ? <Play size={14} /> : <Pause size={14} />}
                  </button>
                  <button
                    title="Delete"
                    onClick={() => {
                      if (confirm(`Delete check "${check.name}"?`)) deleteMutation.mutate(check.id);
                    }}
                    className="rounded p-1.5 text-ink-muted hover:bg-white/5 hover:text-status-down"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
