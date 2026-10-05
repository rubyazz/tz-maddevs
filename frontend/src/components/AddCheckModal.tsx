// Create-check modal form (validation mirrors backend bounds).

import { FormEvent, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Check } from '../api/types';
import { Button, Field, Modal, inputClass } from './ui';

export function AddCheckModal({
  groupId,
  onClose,
}: {
  groupId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api<Check>('/api/checks', { method: 'POST', body: payload }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['overview'] });
      onClose();
    },
    onError: (err: Error) => setError(err.message),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const expectedBody = String(form.get('expected_body') ?? '').trim();
    mutation.mutate({
      group_id: groupId,
      name: String(form.get('name') ?? '').trim(),
      url: String(form.get('url') ?? '').trim(),
      interval_seconds: Number(form.get('interval_seconds')),
      timeout_seconds: Number(form.get('timeout_seconds')),
      expected_status: Number(form.get('expected_status')),
      expected_body: expectedBody === '' ? null : expectedBody,
      failure_threshold: Number(form.get('failure_threshold')),
      show_on_public: form.get('show_on_public') === 'on',
    });
  }

  return (
    <Modal title="Add check" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name">
          <input name="name" required maxLength={100} className={inputClass} placeholder="Main site" />
        </Field>
        <Field label="URL">
          <input
            name="url"
            required
            type="url"
            className={inputClass}
            placeholder="http://demo-sites:8090/site/main"
          />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Interval, seconds (30–3600)">
            <input name="interval_seconds" type="number" defaultValue={60} min={30} max={3600} required className={inputClass} />
          </Field>
          <Field label="Timeout, seconds (1–30)">
            <input name="timeout_seconds" type="number" defaultValue={10} min={1} max={30} required className={inputClass} />
          </Field>
          <Field label="Expected status code">
            <input name="expected_status" type="number" defaultValue={200} min={100} max={599} required className={inputClass} />
          </Field>
          <Field label="Failure threshold (1–10)">
            <input name="failure_threshold" type="number" defaultValue={3} min={1} max={10} required className={inputClass} />
          </Field>
        </div>
        <Field label="Expected body substring (optional)">
          <input name="expected_body" className={inputClass} placeholder="OK" />
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink-secondary">
          <input type="checkbox" name="show_on_public" className="accent-status-info" />
          Show on public status page
        </label>
        {error ? <p className="text-sm text-status-down">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            Create check
          </Button>
        </div>
      </form>
    </Modal>
  );
}
