import Link from "next/link";

import { exploreHref } from "@/components/search/url-state";

export function Pagination({
  params,
  page,
  pageSize,
  total,
  basePath = "/explore",
}: {
  params: Record<string, string | undefined>;
  page: number;
  pageSize: number;
  total: number;
  basePath?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  const href = (p: number) =>
    exploreHref(params, { page: p > 1 ? String(p) : undefined }).replace("/explore", basePath);
  const linkClass = "rounded border border-rule bg-surface px-3 py-1.5 text-sm hover:border-ink";
  const disabledClass = "rounded border border-rule px-3 py-1.5 text-sm text-muted opacity-50";

  return (
    <nav aria-label="Pagination" className="mt-6 flex items-center justify-between gap-4">
      {page > 1 ? (
        <Link href={href(page - 1)} className={linkClass}>
          Previous
        </Link>
      ) : (
        <span aria-disabled="true" className={disabledClass}>
          Previous
        </span>
      )}
      <span className="text-sm text-muted">
        Page {page} of {pages}
      </span>
      {page < pages ? (
        <Link href={href(page + 1)} className={linkClass}>
          Next
        </Link>
      ) : (
        <span aria-disabled="true" className={disabledClass}>
          Next
        </span>
      )}
    </nav>
  );
}
