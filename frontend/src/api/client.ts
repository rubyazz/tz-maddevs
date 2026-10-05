// Minimal typed fetch client. Auth token lives in localStorage;
// 401 anywhere outside /auth/* clears it and redirects to /login.

const TOKEN_KEY = 'pulse_token';

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail?: unknown,
  ) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`);
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = new URL(path, window.location.origin);
  if (opts.params) {
    for (const [key, value] of Object.entries(opts.params)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(url, {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (response.status === 401 && !path.startsWith('/api/auth/')) {
    clearToken();
    window.location.href = '/login';
    throw new ApiError(401, 'Session expired');
  }
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = (await response.json())?.detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
