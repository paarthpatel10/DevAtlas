import { formatDate } from "@/lib/format";

/** Visible "Demo data" label required by spec section 15 for static snapshot metrics. */
export function SnapshotNote({ fetchedAt }: { fetchedAt: string }) {
  return (
    <p className="rounded border border-rule bg-surface px-3 py-2 text-xs text-muted">
      <span className="font-medium text-ink">Demo data:</span> repository metrics come from a
      GitHub snapshot taken {formatDate(fetchedAt)}, not live values.
    </p>
  );
}
