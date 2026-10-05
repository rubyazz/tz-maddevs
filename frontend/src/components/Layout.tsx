import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Activity, FlaskConical, LayoutDashboard, Mail, LogOut, Wrench } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api, clearToken } from '../api/client';
import { useEvents } from '../lib/sse';
import type { User } from '../api/types';

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/maintenance', label: 'Maintenance', icon: Wrench },
  { to: '/mailbox', label: 'Mailbox', icon: Mail },
  { to: '/demo', label: 'Demo', icon: FlaskConical },
];

export default function Layout() {
  useEvents(); // live updates for every signed-in tab
  const navigate = useNavigate();
  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: () => api<User>('/api/me'),
  });

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-edge bg-surface/60">
        <div className="flex items-center gap-2 px-5 py-5">
          <span className="grid size-8 place-items-center rounded-lg bg-status-info/15 text-status-info">
            <Activity size={18} />
          </span>
          <span className="text-lg font-semibold tracking-tight">Pulse</span>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-status-info/10 text-ink-primary'
                    : 'text-ink-secondary hover:bg-white/5 hover:text-ink-primary'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-edge p-4">
          <p className="truncate text-xs text-ink-muted">{me?.email ?? '…'}</p>
          <button
            onClick={() => {
              clearToken();
              navigate('/login');
            }}
            className="mt-2 flex items-center gap-2 text-xs text-ink-secondary hover:text-ink-primary"
          >
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-8 py-6">
        <Outlet />
      </main>
    </div>
  );
}
