// Group page: settings, alert emails, public page controls, checks, windows.

import { FormEvent, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Copy, Globe, EyeOff, Mail, Plus, Send } from 'lucide-react';
import { api } from '../api/client';
import type { GroupView, Overview } from '../api/types';
import { CheckTable } from '../components/CheckTable';
import { AddCheckModal } from '../components/AddCheckModal';
import { GroupStatusBadge } from '../components/Status';
import { Button, Card, Field, inputClass } from '../components/ui';

export default function GroupPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [showAddCheck, setShowAddCheck] = useState(false);

  const { data } = useQuery({
    queryKey: ['overview'],
    queryFn: () => api<Overview>('/api/overview'),
  });
  const group = data?.groups.find((group) => group.id === id);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['overview'] });
  };

  const slugMutation = useMutation({
    mutationFn: (action: 'generate' | 'clear') =>
      action === 'generate'
        ? api<{ public_slug: string }>(`/api/groups/${id}/public-slug/generate`, { method: 'POST' })
        : api(`/api/groups/${id}`, { method: 'PATCH', body: { public_slug: null } }),
    onSuccess: invalidate,
  });

  if (!group) return <p className="text-sm text-ink-muted">Loading…</p>;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-ink-secondary hover:text-ink-primary">
        <ArrowLeft size={14} /> Dashboard
      </Link>

      <Card>
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">{group.name}</h1>
            <GroupStatusBadge status={group.status} />
          </div>
          <Button variant="ghost" onClick={() => setShowAddCheck(true)}>
            <Plus size={14} /> Check
          </Button>
        </div>
        <GroupSettingsForm group={group} onSaved={invalidate} />

        <div className="mt-6 border-t border-edge pt-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <Globe size={14} /> Public status page
          </h2>
          {group.public_slug ? (
            <div className="flex flex-wrap items-center gap-3">
              <Link
                to={`/status/${group.public_slug}`}
                className="rounded-md border border-edge px-3 py-1.5 text-sm text-status-info hover:border-status-info/40"
              >
                /status/{group.public_slug}
              </Link>
              <Button
                variant="ghost"
                onClick={() => navigator.clipboard?.writeText(`${window.location.origin}/status/${group.public_slug}`)}
              >
                <Copy size={13} /> Copy link
              </Button>
              <Button variant="danger" onClick={() => slugMutation.mutate('clear')}>
                <EyeOff size={13} /> Unpublish
              </Button>
              <p className="w-full text-xs text-ink-muted">
                Only checks with "show on public" are visible; the link is unguessable.
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <Button onClick={() => slugMutation.mutate('generate')} disabled={slugMutation.isPending}>
                Publish status page
              </Button>
              <p className="text-xs text-ink-muted">Generates an unguessable link, no login required.</p>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Mail size={14} /> Alert emails
        </h2>
        <AlertEmails group={group} onChanged={invalidate} />
      </Card>

      <Card>
        <h2 className="mb-4 text-sm font-semibold">Checks</h2>
        {group.checks.length === 0 ? (
          <p className="text-sm text-ink-muted">No checks yet.</p>
        ) : (
          <CheckTable checks={group.checks} />
        )}
      </Card>

      {showAddCheck && <AddCheckModal groupId={group.id} onClose={() => setShowAddCheck(false)} />}
    </div>
  );
}

function GroupSettingsForm({ group, onSaved }: { group: GroupView; onSaved: () => void }) {
  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api(`/api/groups/${group.id}`, { method: 'PATCH', body: payload }),
    onSuccess: onSaved,
  });
  return (
    <form
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        mutation.mutate({
          name: String(form.get('name') ?? '').trim(),
          description: String(form.get('description') ?? '').trim(),
        });
      }}
      className="grid gap-4 sm:grid-cols-2"
    >
      <Field label="Name">
        <input name="name" defaultValue={group.name} required maxLength={100} className={inputClass} />
      </Field>
      <Field label="Description">
        <input name="description" defaultValue={group.description} className={inputClass} />
      </Field>
      <div>
        <Button type="submit" disabled={mutation.isPending}>
          Save group
        </Button>
      </div>
    </form>
  );
}

function AlertEmails({ group, onChanged }: { group: GroupView; onChanged: () => void }) {
  const [value, setValue] = useState('');
  const addMutation = useMutation({
    mutationFn: (email: string) =>
      api(`/api/groups/${group.id}/emails`, { method: 'POST', body: { email } }),
    onSuccess: () => {
      setValue('');
      onChanged();
    },
  });
  const removeMutation = useMutation({
    mutationFn: (emailId: string) =>
      api(`/api/groups/${group.id}/emails/${emailId}`, { method: 'DELETE' }),
    onSuccess: onChanged,
  });
  const testMutation = useMutation({
    mutationFn: (emailId: string) =>
      api(`/api/groups/${group.id}/emails/${emailId}/test`, { method: 'POST' }),
    onSuccess: onChanged,
  });

  return (
    <div className="space-y-3">
      {group.alert_emails.length === 0 ? (
        <p className="text-xs text-ink-muted">
          No alert emails — down/up letters will be recorded to noreply in the Mailbox.
        </p>
      ) : (
        <ul className="space-y-2">
          {group.alert_emails.map((row) => (
            <li key={row.id} className="flex items-center gap-2 rounded-lg border border-edge px-3 py-2 text-sm">
              <span className="flex-1">{row.email}</span>
              <Button variant="ghost" onClick={() => testMutation.mutate(row.id)} title="Send test letter">
                <Send size={13} /> Test
              </Button>
              <Button variant="danger" onClick={() => removeMutation.mutate(row.id)}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (value.trim()) addMutation.mutate(value.trim());
        }}
      >
        <input
          type="email"
          required
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="alerts@example.com"
          className={inputClass}
        />
        <Button type="submit" disabled={addMutation.isPending}>
          <Plus size={14} /> Add
        </Button>
      </form>
    </div>
  );
}
