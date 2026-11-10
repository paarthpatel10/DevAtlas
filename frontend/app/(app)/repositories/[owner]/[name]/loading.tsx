export default function Loading() {
  return (
    <div role="status" aria-label="Loading repository…" className="animate-pulse space-y-4">
      <div className="h-7 w-64 rounded bg-rule" />
      <div className="h-4 w-full max-w-2xl rounded bg-rule/70" />
      <div className="h-20 rounded border border-rule bg-surface" />
      <div className="h-40 rounded bg-rule/40" />
      <span className="sr-only">Loading repository…</span>
    </div>
  );
}
