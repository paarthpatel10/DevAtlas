export function ListSkeleton({ rows = 5, label }: { rows?: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="rounded border border-rule bg-surface px-4">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="animate-pulse border-b border-rule py-4 last:border-b-0">
          <div className="h-4 w-48 rounded bg-rule" />
          <div className="mt-2 h-3 w-full max-w-xl rounded bg-rule/70" />
          <div className="mt-2 h-3 w-64 rounded bg-rule/50" />
        </div>
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}
