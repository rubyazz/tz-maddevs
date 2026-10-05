// Check detail: live status, history charts (day/week/month), incidents,
// raw results, inline settings editor.

import { FormEvent, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Pause, Play, Zap } from 'lucide-react';
import { api } from '../api/client';
import type { CheckDetail, History, Period, ResultsPage } from '../api/types';
import { ResponseChart, UptimeBars } from '../components/charts';
import { IncidentTable } from '../components/IncidentTable';
import { StateBadge } from '../components/Status';
import { Button, Card, Field, StatTile, inputClass } from '../components/ui';
import { durationSince, fmtDateTime, fmtMs, fmtPct, relTime } from '../lib/format';

const PERIODS: Period[] = ['day', 'week', 'month'];

export default function CheckDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<Period>('day');

  const { data: check } = useQuery({
    queryKey: ['check', id],
    queryFn: () => api<CheckDetail>(`/api/checks/${id}`),
  });
  const { data: history } = useQuery({
    queryKey: ['history', id, period],
    queryFn: () => api<History>(`/api/checks/${id}/history`, { params: { period } }),
  });
  const { data: results, fetchNextPage } = useResultsFeed(id);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['check', id] });
    queryClient.invalidateQueries({ queryKey: ['history', id] });
    queryClient.invalidateQueries({ queryKey: ['overview'] });
  };

  const runMutation = useMutation({
    mutationFn: () => api(`/api/checks/${id}/run`, { method: 'POST' }),
    onSuccess: invalidate,
  });
  const toggleMutation = useMutation({
    mutationFn: () =>
      api(`/api/checks/${id}/${check?.paused ? 'resume' : 'pause'}`, { method: 'POST' }),
    onSuccess: invalidate,
  });
  const deleteMutation = useMutation({
    mutationFn: () => api(`/api/checks/${id}`, { method: 'DELETE' }),
    onSuccess: () => navigate('/'),
  });

  if (!check) return <p className="text-sm text-ink-muted">Loading…</p>;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-ink-secondary hover:text-ink-primary">
        <ArrowLeft size={14} /> Dashboard
      </Link>

      <Card>
        <div className="flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3">
              <h1 className="truncate text-xl font-semibold">{check.name}</h1>
              <StateBadge state={check.paused ? 'paused' : check.state} />
            </div>
            <p className="mt-1 truncate text-sm text-ink-muted">{check.url}</p>
            <p className="mt-2 text-xs text-ink-secondary">
              Group:{' '}
              <Link to={`/groups/${check.group_id}`} className="text-status-info hover:underline">
                {check.group.name}
              </Link>{' '}
              · every {check.interval_seconds}s · timeout {check.timeout_seconds}s · expects{' '}
              {check.expected_status}
              {check.expected_body ? ` · body contains "${check.expected_body}"` : ''} · threshold{' '}
              {check.failure_threshold}
            </p>
            <p className="mt-1 text-xs text-ink-secondary">
              Last check {relTime(check.last_checked_at)} ·{' '}
              {check.open_incident ? (
                <span className="text-status-down">
                  down for {durationSince(check.open_incident.started_at)}
                </span>
              ) : (
                <span>no open incident</span>
              )}
              {check.last_error && !check.paused ? ` · last error: ${check.last_error}` : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
              <Zap size={14} /> Run now
            </Button>
            <Button variant="ghost" onClick={() => toggleMutation.mutate()}>
              {check.paused ? <Play size={14} /> : <Pause size={14} />}
              {check.paused ? 'Resume' : 'Pause'}
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                if (confirm(`Delete check "${check.name}"?`)) deleteMutation.mutate();
              }}
            >
              Delete
            </Button>
          </div>
        </div>
      </Card>

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold">History</h2>
          <div className="flex rounded-lg border border-edge p-0.5 text-xs">
            {PERIODS.map((value) => (
              <button
                key={value}
                onClick={() => setPeriod(value)}
                className={`rounded-md px-3 py-1 capitalize transition-colors ${
                  period === value ? 'bg-status-info/15 text-ink-primary' : 'text-ink-secondary'
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </div>
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Uptime" value={fmtPct(history?.summary.uptime)} sub={`${history?.summary.ok ?? 0}/${history?.summary.checks ?? 0} checks`} />
          <StatTile label="Avg response" value={fmtMs(history?.summary.avg_response_ms)} />
          <StatTile label="p95 response" value={fmtMs(history?.summary.p95_response_ms)} />
          <StatTile label="Incidents" value={String(history?.incidents.length ?? 0)} />
        </div>
        <p className="mb-1 text-xs font-medium text-ink-secondary">Response time</p>
        <ResponseChart buckets={history?.buckets ?? []} />
        <p className="mb-1 mt-5 text-xs font-medium text-ink-secondary">
          Availability per bucket (gaps = no data)
        </p>
        <UptimeBars buckets={history?.buckets ?? []} />
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-semibold">Incidents</h2>
        <IncidentTable incidents={check.incidents} />
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-semibold">Recent results</h2>
        <ResultsTable data={results} onLoadMore={fetchNextPage} />
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-semibold">Settings</h2>
        <SettingsForm check={check} onSaved={invalidate} />
      </Card>
    </div>
  );
}

function useResultsFeed(id: string | undefined) {
  return useInfiniteQuery({
    queryKey: ['results', id],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api<ResultsPage>(`/api/checks/${id}/results`, { params: { limit: 25, before: pageParam } }),
    getNextPageParam: (last) => last.next_before ?? undefined,
  });
}

function ResultsTable({
  data,
  onLoadMore,
}: {
  data?: ReturnType<typeof useResultsFeed>['data'];
  onLoadMore: () => void;
}) {
  const items = data?.pages.flatMap((page) => page.items) ?? [];
  const hasMore = Boolean(data?.pages.at(-1)?.next_before);
  if (items.length === 0) {
    return <p className="text-sm text-ink-muted">No results yet.</p>;
  }
  return (
    <div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-edge text-left text-xs text-ink-muted">
            <th className="py-2 pr-4 font-medium">Time</th>
            <th className="py-2 pr-4 font-medium">Result</th>
            <th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 pr-4 font-medium">Response</th>
            <th className="py-2 font-medium">Error</th>
          </tr>
        </thead>
        <tbody>
          {items.map((result) => (
            <tr key={result.id} className="border-b border-edge/60">
              <td className="py-2 pr-4 text-ink-secondary">{fmtDateTime(result.checked_at)}</td>
              <td className="py-2 pr-4">
                <span className={result.ok ? 'text-status-up' : 'text-status-down'}>
                  {result.ok ? 'OK' : 'FAIL'}
                </span>
              </td>
              <td className="num py-2 pr-4 text-ink-secondary">{result.status_code ?? '—'}</td>
              <td className="num py-2 pr-4 text-ink-secondary">{fmtMs(result.response_time_ms)}</td>
              <td className="max-w-[260px] truncate py-2 text-xs text-ink-muted" title={result.error ?? ''}>
                {result.error ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore ? (
        <Button variant="ghost" className="mt-3" onClick={onLoadMore}>
          Load more
        </Button>
      ) : null}
    </div>
  );
}

function SettingsForm({ check, onSaved }: { check: CheckDetail; onSaved: () => void }) {
  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api(`/api/checks/${check.id}`, { method: 'PATCH', body: payload }),
    onSuccess: onSaved,
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = String(form.get('expected_body') ?? '').trim();
    mutation.mutate({
      name: String(form.get('name') ?? '').trim(),
      url: String(form.get('url') ?? '').trim(),
      interval_seconds: Number(form.get('interval_seconds')),
      timeout_seconds: Number(form.get('timeout_seconds')),
      expected_status: Number(form.get('expected_status')),
      expected_body: body === '' ? null : body,
      failure_threshold: Number(form.get('failure_threshold')),
      show_on_public: form.get('show_on_public') === 'on',
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name">
          <input name="name" defaultValue={check.name} required maxLength={100} className={inputClass} />
        </Field>
        <Field label="URL">
          <input name="url" defaultValue={check.url} required type="url" className={inputClass} />
        </Field>
        <Field label="Interval, seconds (30–3600)">
          <input name="interval_seconds" type="number" defaultValue={check.interval_seconds} min={30} max={3600} required className={inputClass} />
        </Field>
        <Field label="Timeout, seconds (1–30)">
          <input name="timeout_seconds" type="number" defaultValue={check.timeout_seconds} min={1} max={30} required className={inputClass} />
        </Field>
        <Field label="Expected status code">
          <input name="expected_status" type="number" defaultValue={check.expected_status} min={100} max={599} required className={inputClass} />
        </Field>
        <Field label="Failure threshold (1–10)">
          <input name="failure_threshold" type="number" defaultValue={check.failure_threshold} min={1} max={10} required className={inputClass} />
        </Field>
      </div>
      <Field label="Expected body substring (empty = any body)">
        <input name="expected_body" defaultValue={check.expected_body ?? ''} className={inputClass} />
      </Field>
      <label className="flex items-center gap-2 text-sm text-ink-secondary">
        <input type="checkbox" name="show_on_public" defaultChecked={check.show_on_public} className="accent-status-info" />
        Show on public status page
      </label>
      <Button type="submit" disabled={mutation.isPending}>
        Save settings
      </Button>
    </form>
  );
}
