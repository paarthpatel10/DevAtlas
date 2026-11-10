export const NOT_AVAILABLE = "Not available";

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** Compact counts. Missing values are never shown as zero. */
export function formatCount(n: number | null | undefined): string {
  if (n === null || n === undefined) return NOT_AVAILABLE;
  if (n < 1000) return String(n);
  const [value, suffix] = n < 1_000_000 ? [n / 1000, "k"] : [n / 1_000_000, "M"];
  return `${value.toFixed(1).replace(/\.0$/, "")}${suffix}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return NOT_AVAILABLE;
  return dateFormat.format(new Date(iso));
}

export function snapshotLabel(dataSource: string, fetchedAt: string): string {
  const kind = dataSource === "seed_snapshot" ? "Snapshot" : "Live";
  return `${kind} · ${formatDate(fetchedAt)}`;
}
