import type { Metadata } from "next";

import { SavedList } from "@/components/repository/saved-list";
import { Pagination } from "@/components/search/pagination";
import { RefreshError } from "@/components/states/refresh-error";
import { ApiError, listSaved } from "@/lib/api";
import type { Page, RepositorySummary } from "@/lib/types";

export const metadata: Metadata = { title: "Saved" };

export default async function SavedPage(props: PageProps<"/saved">) {
  const { page: rawPage } = await props.searchParams;
  const page = Math.max(1, Number.parseInt(typeof rawPage === "string" ? rawPage : "1", 10) || 1);

  let saved: Page<RepositorySummary>;
  try {
    saved = await listSaved(page);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Saved repositories could not load.";
    return <RefreshError title="Saved couldn't load" message={message} />;
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Saved repositories</h1>
        <p className="mt-1 text-sm text-muted">
          {saved.total} saved. Saves belong to the demo user until accounts are added.
        </p>
      </div>
      <SavedList key={`${page}-${saved.total}`} initial={saved.items} />
      <Pagination
        params={{}}
        page={page}
        pageSize={saved.page_size}
        total={saved.total}
        basePath="/saved"
      />
    </div>
  );
}
