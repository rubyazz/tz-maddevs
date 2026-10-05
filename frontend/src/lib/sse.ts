// SSE subscriptions. Any domain event invalidates the relevant queries —
// the snapshot re-fetch keeps clients correct after any reconnect, events
// only make it instant (CONTRACT §5).

import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getToken } from '../api/client';

const EVENT_NAMES = ['check.update', 'incident.opened', 'incident.closed'] as const;

export function useEvents(): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const source = new EventSource(`/api/events?token=${encodeURIComponent(token)}`);
    const invalidate = () => {
      queryClient.invalidateQueries({ queryKey: ['overview'] });
      queryClient.invalidateQueries({ queryKey: ['check'] });
      queryClient.invalidateQueries({ queryKey: ['history'] });
      queryClient.invalidateQueries({ queryKey: ['results'] });
      queryClient.invalidateQueries({ queryKey: ['mailbox'] });
    };
    for (const name of EVENT_NAMES) source.addEventListener(name, invalidate);
    return () => source.close();
  }, [queryClient]);
}

export function usePublicEvents(slug: string | undefined): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!slug) return;
    const source = new EventSource(`/api/public/${slug}/events`);
    const invalidate = () => queryClient.invalidateQueries({ queryKey: ['public', slug] });
    for (const name of EVENT_NAMES) source.addEventListener(name, invalidate);
    return () => source.close();
  }, [queryClient, slug]);
}
