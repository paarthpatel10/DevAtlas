import Link from "next/link";

import { DiscoverCard } from "@/components/discover/discover-card";
import type { FeedName, FeedPage } from "@/lib/types";

export function basisNote(data: FeedPage): string | null {
  if (data.basis === "not_computed") return "This feed hasn't been computed yet. Run the compute_feeds job.";
  if (data.basis === "insufficient_history")
    return data.note ?? "Not enough history yet for this feed.";
  if (data.basis === "popularity_activity")
    return "Ranked by popularity and recent activity: there isn't enough star history for this period yet.";
  return data.note;
}

export function FeedSection({
  title,
  description,
  feed,
  data,
  seeAllHref,
  emptyText = "Nothing to show here yet.",
}: {
  title: string;
  description?: string;
  feed: FeedName;
  data: FeedPage;
  seeAllHref?: string;
  emptyText?: string;
}) {
  const note = basisNote(data);
  const headingId = `feed-${feed}`;
  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id={headingId} className="text-lg font-semibold tracking-tight">
            {title}
          </h2>
          {description && <p className="text-sm text-muted">{description}</p>}
        </div>
        {seeAllHref && data.total > data.items.length && (
          <Link href={seeAllHref} className="text-sm text-accent hover:underline">
            See all {data.total}
          </Link>
        )}
      </div>
      {data.basis === "github_trending" && (
        <p className="text-xs text-muted">
          From GitHub Trending (
          <a href="https://github.com/trending" target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
            github.com/trending
          </a>
          ), recorded daily: star counts are the ones GitHub reports.
        </p>
      )}
      {note && (
        <p className="rounded border border-amber/40 bg-amber-soft px-3 py-2 text-xs text-amber">{note}</p>
      )}
      {data.items.length === 0 ? (
        <p className="text-sm text-muted">{data.basis === "growth" ? emptyText : null}</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.items.map((item) => (
            <DiscoverCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}
