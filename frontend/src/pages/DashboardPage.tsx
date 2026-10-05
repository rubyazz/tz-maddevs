// Dashboard: groups with computed status + live checks tables.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Globe, Plus } from 'lucide-react';
import { api } from '../api/client';
import type { GroupView, Overview } from '../api/types';
import { CheckTable } from '../components/CheckTable';
import { AddCheckModal } from '../components/AddCheckModal';
import { GroupStatusBadge } from '../components/Status';
import { Button, Card, EmptyState, Field, Modal, inputClass } from '../components/ui';

export default function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['overview'],
    queryFn: () => api<Overview>('/api/overview'),
  });
  const [addCheckFor, setAddCheckFor] = useState<string | null>(null);
  const [showAddGroup, setShowAddGroup] = useState(false);

  if (isLoading) return <p className="text-sm text-ink-muted">Loading…</p>;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <Button onClick={() => setShowAddGroup(true)}>
          <Plus size={15} /> New group
        </Button>
      </div>

      {!data || data.groups.length === 0 ? (
        <EmptyState
          title="No groups yet"
          hint="Create a group, then add checks to start monitoring."
          action={
            <Button onClick={() => setShowAddGroup(true)}>
              <Plus size={15} /> New group
            </Button>
          }
        />
      ) : (
        data.groups.map((group) => <GroupCard key={group.id} group={group} onAddCheck={() => setAddCheckFor(group.id)} />)
      )}

      {addCheckFor && <AddCheckModal groupId={addCheckFor} onClose={() => setAddCheckFor(null)} />}
      {showAddGroup && <AddGroupModal onClose={() => setShowAddGroup(false)} />}
    </div>
  );
}

function GroupCard({ group, onAddCheck }: { group: GroupView; onAddCheck: () => void }) {
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Link to={`/groups/${group.id}`} className="text-base font-semibold hover:text-status-info">
          {group.name}
        </Link>
        <GroupStatusBadge status={group.status} />
        {group.public_slug ? (
          <Link
            to={`/status/${group.public_slug}`}
            className="inline-flex items-center gap-1 rounded-md border border-edge px-2 py-0.5 text-xs text-status-info hover:border-status-info/40"
          >
            <Globe size={12} /> /status/{group.public_slug}
            <ExternalLink size={11} />
          </Link>
        ) : null}
        <span className="ml-auto text-xs text-ink-muted">
          {group.alert_emails.length > 0
            ? `alerts → ${group.alert_emails.map((e) => e.email).join(', ')}`
            : 'no alert emails'}
        </span>
        <Button variant="ghost" onClick={onAddCheck}>
          <Plus size={14} /> Check
        </Button>
      </div>
      {group.checks.length === 0 ? (
        <EmptyState
          title="No checks in this group"
          hint="Add a URL to monitor — try http://demo-sites:8090/site/main"
        />
      ) : (
        <CheckTable checks={group.checks} />
      )}
    </Card>
  );
}

function AddGroupModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (payload: { name: string; description: string }) =>
      api('/api/groups', { method: 'POST', body: payload }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['overview'] });
      onClose();
    },
  });
  return (
    <Modal title="New group" onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          mutation.mutate({
            name: String(form.get('name') ?? '').trim(),
            description: String(form.get('description') ?? '').trim(),
          });
        }}
        className="space-y-4"
      >
        <Field label="Name">
          <input name="name" required maxLength={100} className={inputClass} placeholder="Production" />
        </Field>
        <Field label="Description">
          <input name="description" className={inputClass} placeholder="Public-facing services" />
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            Create group
          </Button>
        </div>
      </form>
    </Modal>
  );
}
