import type { ReactNode } from "react";

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded border border-dashed border-rule px-6 py-10 text-center">
      <h2 className="font-semibold">{title}</h2>
      <div className="mx-auto mt-2 max-w-prose text-sm text-muted">{message}</div>
      {action && <div className="mt-4 flex justify-center gap-3">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="rounded border border-danger/40 bg-danger-soft px-6 py-6">
      <h2 className="font-semibold text-danger">{title}</h2>
      <p className="mt-1 text-sm">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded border border-rule bg-surface px-3 py-1.5 text-sm font-medium hover:border-ink"
        >
          Retry
        </button>
      )}
    </div>
  );
}
