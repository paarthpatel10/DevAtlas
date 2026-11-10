import type { Metadata } from "next";
import Link from "next/link";

import { RepositoryCard } from "@/components/repository/repository-card";
import { SnapshotNote } from "@/components/repository/snapshot-note";
import { CategoryNav } from "@/components/search/category-nav";
import { FilterBar } from "@/components/search/filter-bar";
import { Pagination } from "@/components/search/pagination";
import { SearchBar } from "@/components/search/search-bar";
import { exploreHref } from "@/components/search/url-state";
import { RefreshError } from "@/components/states/refresh-error";
import { EmptyState } from "@/components/states/states";
import { ApiError, getFacets, listRepositories } from "@/lib/api";

export const metadata: Metadata = { title: "Explore" };

const PAGE_SIZE = 20;
const KEYS = ["q", "category", "language", "license", "sort", "page"] as const;

export default async function ExplorePage(props: PageProps<"/explore">) {
  const raw = await props.searchParams;
  const params: Record<string, string | undefined> = {};
  for (const key of KEYS) {
    const value = raw[key];
    params[key] = typeof value === "string" && value ? value : undefined;
  }
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  let data;
  try {
    const [results, facets] = await Promise.all([
      listRepositories({ ...params, page, pageSize: PAGE_SIZE }),
      getFacets(),
    ]);
    data = { results, facets };
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : "The repository index could not be loaded.";
    return <RefreshError title="Explore couldn't load" message={message} />;
  }
  const { results, facets } = data;
  const filtered = Boolean(params.q || params.category || params.language || params.license);
  const snapshot = results.items.find((r) => r.data_source === "seed_snapshot");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Explore open-source projects</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          A curated index of repositories across backend, frontend, data, DevOps, AI and more.
        </p>
      </div>
      <SearchBar key={params.q ?? ""} params={params} />
      <CategoryNav params={params} categories={facets.categories} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-sm text-muted" aria-live="polite">
          {results.total} {results.total === 1 ? "repository" : "repositories"}
          {params.q && (
            <>
              {" "}
              matching <span className="text-ink">“{params.q}”</span>
            </>
          )}
        </p>
        <FilterBar params={params} facets={facets} />
      </div>
      {snapshot && <SnapshotNote fetchedAt={snapshot.source_fetched_at} />}
      {results.items.length === 0 ? (
        <EmptyState
          title="No repositories match"
          message="Try fewer or different words, or clear the filters. To describe a problem in your own words, use Ask AI."
          action={
            <>
              {filtered && (
                <Link href={exploreHref({}, {})} className="text-sm text-accent hover:underline">
                  Clear search and filters
                </Link>
              )}
              <Link
                href={params.q ? `/ask?q=${encodeURIComponent(params.q)}` : "/ask"}
                className="text-sm text-accent hover:underline"
              >
                Ask AI instead
              </Link>
            </>
          }
        />
      ) : (
        <section aria-label="Repositories" className="rounded border border-rule bg-surface px-4">
          {results.items.map((repo) => (
            <RepositoryCard key={repo.id} repo={repo} />
          ))}
        </section>
      )}
      <Pagination params={params} page={page} pageSize={PAGE_SIZE} total={results.total} />
    </div>
  );
}
