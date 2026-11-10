export default function Loading() {
  return (
    <div role="status" aria-label="Loading discoveries…" className="space-y-6">
      <div className="h-7 w-40 animate-pulse rounded bg-rule" />
      <div className="grid gap-3 md:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-44 animate-pulse rounded border border-rule bg-surface" />
        ))}
      </div>
      <span className="sr-only">Loading discoveries…</span>
    </div>
  );
}
