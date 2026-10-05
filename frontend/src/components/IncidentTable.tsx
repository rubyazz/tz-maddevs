// Incident log: start, end, duration, cause.

import type { Incident } from '../api/types';
import { fmtDateTime, fmtDuration } from '../lib/format';
import { EmptyState } from './ui';

export function IncidentTable({ incidents }: { incidents: Incident[] }) {
  if (incidents.length === 0) {
    return <EmptyState title="No incidents recorded" hint="Incidents appear after the failure threshold is reached." />;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-edge text-left text-xs text-ink-muted">
            <th className="py-2 pr-4 font-medium">Started</th>
            <th className="py-2 pr-4 font-medium">Ended</th>
            <th className="py-2 pr-4 font-medium">Duration</th>
            <th className="py-2 font-medium">Cause</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <tr key={incident.id} className="border-b border-edge/60">
              <td className="py-2.5 pr-4 text-ink-secondary">{fmtDateTime(incident.started_at)}</td>
              <td className="py-2.5 pr-4 text-ink-secondary">
                {incident.ended_at ? (
                  fmtDateTime(incident.ended_at)
                ) : (
                  <span className="font-medium text-status-down">ongoing</span>
                )}
              </td>
              <td className="num py-2.5 pr-4 text-ink-secondary">
                {fmtDuration(
                  incident.duration_s ??
                    Math.floor((Date.now() - new Date(incident.started_at).getTime()) / 1000),
                )}
              </td>
              <td className="max-w-[280px] truncate py-2.5 text-xs text-ink-muted" title={incident.last_error ?? ''}>
                {incident.last_error ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
