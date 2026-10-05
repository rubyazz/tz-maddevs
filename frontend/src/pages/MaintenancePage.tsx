// Maintenance windows: planned work per check or per group.
// During a window checks run and statuses are shown, but letters are
// suppressed (and a still-open incident notifies once the window ends).

import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2, Wrench } from 'lucide-react';
import { api } from '../api/client';
import type { MaintenanceWindow, Overview } from '../api/types';
import { Button, Card, EmptyState, Field, inputClass } from '../components/ui';
import { fmtDateTime } from '../lib/format';

function toLocalInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export default function MaintenancePage() {
  const queryClient = useQueryClient();
  const { data: windows } = useQuery({
    queryKey: ['maintenance'],
    queryFn: () => api<MaintenanceWindow[]>('/api/maintenance-windows'),
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['maintenance'] });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api(`/api/maintenance-windows/${id}`, { method: 'DELETE' }),
    onSuccess: invalidate,
  });

  const now = Date.now();
  const sorted = [...(windows ?? [])].sort((a, b) => a.starts_at.localeCompare(b.starts_at));

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="flex items-center gap-2 text-xl font-semibold">
        <Wrench size={18} /> Maintenance windows
      </h1>
      <Card>
        <h2 className="mb-4 text-sm font-semibold">New window</h2>
        <CreateWindowForm onCreated={invalidate} />
      </Card>
      <Card>
        <h2 className="mb-4 text-sm font-semibold">Windows</h2>
        {!sorted.length ? (
          <EmptyState
            title="No maintenance windows"
            hint="Planned work suspends alert letters; checks keep running."
          />
        ) : (
          <ul className="space-y-2">
            {sorted.map((window) => {
              const active = new Date(window.starts_at).getTime() <= now && now < new Date(window.ends_at).getTime();
              return (
                <li key={window.id} className="flex items-center gap-3 rounded-lg border border-edge px-4 py-3 text-sm">
                  <span
                    className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                      active ? 'bg-status-info/15 text-status-info' : 'bg-white/5 text-ink-muted'
                    }`}
                  >
                    {active ? 'active now' : new Date(window.starts_at).getTime() > now ? 'upcoming' : 'past'}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate">
                      {window.check_name ? `Check: ${window.check_name}` : `Group: ${window.group_name}`}
                    </p>
                    <p className="text-xs text-ink-muted">
                      {fmtDateTime(window.starts_at)} → {fmtDateTime(window.ends_at)}
                      {window.note ? ` · ${window.note}` : ''}
                    </p>
                  </div>
                  <button
                    onClick={() => deleteMutation.mutate(window.id)}
                    className="rounded p-1.5 text-ink-muted hover:bg-white/5 hover:text-status-down"
                    title="Delete window"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}

function CreateWindowForm({ onCreated }: { onCreated: () => void }) {
  const { data: overview } = useQuery({
    queryKey: ['overview'],
    queryFn: () => api<Overview>('/api/overview'),
  });
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api('/api/maintenance-windows', { method: 'POST', body: payload }),
    onSuccess: onCreated,
    onError: (err: Error) => setError(err.message),
  });

  const targets: Array<{ value: string; label: string }> = [];
  for (const group of overview?.groups ?? []) {
    targets.push({ value: `group:${group.id}`, label: `Group: ${group.name}` });
    for (const check of group.checks) {
      targets.push({ value: `check:${check.id}`, label: `  ↳ Check: ${check.name}` });
    }
  }

  const soon = new Date(Date.now() + 15 * 60_000); // sensible default: in 15 minutes
  const later = new Date(soon.getTime() + 60 * 60_000);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const [kind, targetId] = String(form.get('target') ?? '').split(':');
    const startsAt = new Date(String(form.get('starts_at')));
    const endsAt = new Date(String(form.get('ends_at')));
    mutation.mutate({
      [kind === 'group' ? 'group_id' : 'check_id']: targetId,
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
      note: String(form.get('note') ?? '').trim(),
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Target (group or single check)">
          <select name="target" required className={inputClass}>
            {targets.map((target) => (
              <option key={target.value} value={target.value} className="bg-surface">
                {target.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Note">
          <input name="note" className={inputClass} placeholder="DB upgrade" />
        </Field>
        <Field label="Starts (local time)">
          <input type="datetime-local" name="starts_at" required defaultValue={toLocalInputValue(soon)} className={inputClass} />
        </Field>
        <Field label="Ends (local time)">
          <input type="datetime-local" name="ends_at" required defaultValue={toLocalInputValue(later)} className={inputClass} />
        </Field>
      </div>
      {error ? <p className="text-sm text-status-down">{error}</p> : null}
      <Button type="submit" disabled={mutation.isPending}>
        Create window
      </Button>
    </form>
  );
}
