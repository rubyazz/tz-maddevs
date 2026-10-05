// Demo page: control the demo-sites emulator from the UI. Flip a site's mode
// and watch checks/incidents/letters react on the dashboard.

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { FlaskConical } from 'lucide-react';
import { Button, Card, inputClass } from '../components/ui';

const DEMO_URL = import.meta.env.VITE_DEMO_SITES_URL as string | undefined ?? 'http://localhost:8090';

const SITES = ['main', 'slow', 'flaky', 'dead'] as const;
const MODES = ['ok', 'error', 'dead', 'slow', 'flaky'] as const;
type Mode = (typeof MODES)[number];

export default function DemoPage() {
  const queryClient = useQueryClient();
  const [modes, setModes] = useState<Record<string, { mode: Mode; delay_ms?: number } | undefined>>({});
  const [delayMs, setDelayMs] = useState(12000);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    try {
      const response = await fetch(`${DEMO_URL}/modes`);
      setModes(await response.json());
    } catch {
      setModes({});
    }
  }

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, []);

  async function setMode(site: string, mode: Mode) {
    setBusy(site);
    try {
      await fetch(`${DEMO_URL}/mode/${site}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, delay_ms: delayMs }),
      });
      await refresh();
      queryClient.invalidateQueries({ queryKey: ['overview'] });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="flex items-center gap-2 text-xl font-semibold">
        <FlaskConical size={18} /> Demo sites
      </h1>
      <p className="text-sm text-ink-muted">
        These fake sites are what the seeded checks monitor
        (<code className="rounded bg-white/5 px-1">http://demo-sites:8090/site/&lt;name&gt;</code> from
        the backend's point of view). Flip a mode, then use “Run now” on the dashboard (or wait for
        the interval) and watch states, incidents and letters react.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        {SITES.map((site) => (
          <Card key={site}>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="font-semibold">/{site}</p>
                <p className="text-xs text-ink-muted">
                  current mode:{' '}
                  <span className="text-ink-secondary">{modes[site]?.mode ?? '…'}</span>
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {MODES.map((mode) => (
                <Button
                  key={mode}
                  variant={modes[site]?.mode === mode ? 'primary' : 'ghost'}
                  disabled={busy === site}
                  onClick={() => setMode(site, mode)}
                  className="px-2.5 py-1 text-xs"
                >
                  {mode}
                </Button>
              ))}
            </div>
          </Card>
        ))}
      </div>
      <Card>
        <p className="mb-2 text-sm font-medium">slow-mode delay (ms)</p>
        <input
          type="number"
          min={100}
          max={60000}
          value={delayMs}
          onChange={(event) => setDelayMs(Number(event.target.value))}
          className={`${inputClass} max-w-40`}
        />
        <p className="mt-2 text-xs text-ink-muted">
          Set it above a check's timeout (e.g. &gt; 5000 for “Slow API”) to produce timeouts.
        </p>
      </Card>
    </div>
  );
}
