// Mailbox: the emulated email outbox. Proves alerting behavior — sent and
// suppressed (maintenance) letters are both visible.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Mail } from 'lucide-react';
import { api } from '../api/client';
import type { MailboxItem } from '../api/types';
import { Card, EmptyState } from '../components/ui';
import { fmtDateTime } from '../lib/format';

const KIND_STYLES: Record<MailboxItem['kind'], string> = {
  down: 'bg-status-down/15 text-status-down',
  up: 'bg-status-up/15 text-status-up',
  test: 'bg-white/5 text-ink-secondary',
};

export default function MailboxPage() {
  const { data } = useQuery({
    queryKey: ['mailbox'],
    queryFn: () => api<{ items: MailboxItem[] }>('/api/mailbox', { params: { limit: 200 } }),
  });
  const [openId, setOpenId] = useState<string | null>(null);
  const items = data?.items ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="flex items-center gap-2 text-xl font-semibold">
        <Mail size={18} /> Mailbox
      </h1>
      <p className="text-sm text-ink-muted">
        SMTP is emulated: letters are recorded here instead of being sent. Suppressed rows show
        why they were held back (e.g. a maintenance window).
      </p>
      <Card>
        {items.length === 0 ? (
          <EmptyState
            title="No letters yet"
            hint="Break a site from the Demo page (or click Test on an alert email) and watch letters arrive."
          />
        ) : (
          <ul className="divide-y divide-edge/60">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  className="flex w-full items-center gap-3 px-1 py-3 text-left text-sm hover:bg-white/[0.02]"
                  onClick={() => setOpenId(openId === item.id ? null : item.id)}
                >
                  {openId === item.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  <span className={`rounded-md px-2 py-0.5 text-xs font-semibold uppercase ${KIND_STYLES[item.kind]}`}>
                    {item.kind}
                  </span>
                  <span
                    className={`rounded-md px-2 py-0.5 text-xs ${
                      item.status === 'suppressed'
                        ? 'bg-status-warn/15 text-status-warn'
                        : 'bg-white/5 text-ink-secondary'
                    }`}
                  >
                    {item.status}
                    {item.suppress_reason ? ` · ${item.suppress_reason}` : ''}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{item.subject}</span>
                  <span className="hidden shrink-0 text-xs text-ink-muted sm:block">{item.to_email}</span>
                  <span className="shrink-0 text-xs text-ink-muted">{fmtDateTime(item.created_at)}</span>
                </button>
                {openId === item.id ? (
                  <pre className="mb-3 whitespace-pre-wrap rounded-lg border border-edge bg-page px-4 py-3 text-xs text-ink-secondary">
                    {item.body}
                  </pre>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
