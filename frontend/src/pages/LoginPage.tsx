import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Activity } from 'lucide-react';
import { api, setToken } from '../api/client';
import type { AuthResponse } from '../api/types';
import { Button, Field, inputClass } from '../components/ui';

export default function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: { email: string; password: string }) =>
      api<AuthResponse>(`/api/auth/${mode}`, { method: 'POST', body: payload }),
    onSuccess: (data) => {
      setToken(data.token);
      navigate('/');
    },
    onError: (err: Error) => setError(err.message),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    mutation.mutate({
      email: String(form.get('email') ?? ''),
      password: String(form.get('password') ?? ''),
    });
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <span className="grid size-9 place-items-center rounded-lg bg-status-info/15 text-status-info">
            <Activity size={20} />
          </span>
          <span className="text-2xl font-semibold tracking-tight">Pulse</span>
        </div>
        <div className="rounded-xl border border-edge bg-surface p-6">
          <div className="mb-5 flex rounded-lg border border-edge p-0.5 text-sm">
            {(['login', 'register'] as const).map((value) => (
              <button
                key={value}
                onClick={() => {
                  setMode(value);
                  setError(null);
                }}
                className={`flex-1 rounded-md py-1.5 capitalize transition-colors ${
                  mode === value ? 'bg-status-info/15 text-ink-primary' : 'text-ink-secondary'
                }`}
              >
                {value === 'login' ? 'Sign in' : 'Register'}
              </button>
            ))}
          </div>
          <form onSubmit={submit} className="space-y-4">
            <Field label="Email">
              <input
                name="email"
                type="email"
                required
                defaultValue="demo@pulse.dev"
                className={inputClass}
              />
            </Field>
            <Field label="Password">
              <input
                name="password"
                type="password"
                required
                minLength={8}
                defaultValue="demo1234"
                className={inputClass}
              />
            </Field>
            {error ? <p className="text-sm text-status-down">{error}</p> : null}
            <Button type="submit" disabled={mutation.isPending} className="w-full justify-center">
              {mode === 'login' ? 'Sign in' : 'Create account'}
            </Button>
          </form>
          <p className="mt-4 text-center text-xs text-ink-muted">
            Demo account: demo@pulse.dev / demo1234 (prefilled)
          </p>
        </div>
      </div>
    </div>
  );
}
