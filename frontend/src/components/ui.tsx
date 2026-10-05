// Small shared UI atoms: modal, empty state, stat tile, buttons.

import { ReactNode } from 'react';
import { X } from 'lucide-react';

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-edge bg-surface p-5 ${className}`}>{children}</div>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-page/80 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl border border-edge bg-surface p-6 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} className="text-ink-muted hover:text-ink-primary" aria-label="Close">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed border-edge px-6 py-12 text-center">
      <p className="text-sm font-medium text-ink-secondary">{title}</p>
      {hint ? <p className="mt-1 max-w-sm text-xs text-ink-muted">{hint}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-edge bg-surface px-4 py-3">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="num mt-1 text-xl font-semibold text-ink-primary">{value}</p>
      {sub ? <p className="mt-0.5 text-xs text-ink-muted">{sub}</p> : null}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = 'primary',
  disabled,
  type = 'button',
  className = '',
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: 'primary' | 'ghost' | 'danger';
  disabled?: boolean;
  type?: 'button' | 'submit';
  className?: string;
  title?: string;
}) {
  const styles = {
    primary: 'bg-status-info/90 text-white hover:bg-status-info disabled:opacity-50',
    ghost:
      'border border-edge text-ink-secondary hover:text-ink-primary hover:border-white/20 disabled:opacity-50',
    danger: 'text-status-down hover:bg-status-down/10 disabled:opacity-50',
  }[variant];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-secondary">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  'w-full rounded-lg border border-edge bg-page px-3 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:border-status-info/60 focus:outline-none';
