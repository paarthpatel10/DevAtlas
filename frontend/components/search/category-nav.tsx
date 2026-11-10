import Link from "next/link";

import { exploreHref } from "@/components/search/url-state";
import type { Facets } from "@/lib/types";

export function CategoryNav({
  params,
  categories,
}: {
  params: Record<string, string | undefined>;
  categories: Facets["categories"];
}) {
  const items = [{ value: "", label: "All", count: undefined }, ...categories];
  return (
    <nav aria-label="Categories" className="-mx-4 overflow-x-auto px-4">
      <ul className="flex gap-1 whitespace-nowrap border-b border-rule">
        {items.map((c) => {
          const active = (params.category ?? "") === c.value;
          return (
            <li key={c.value || "all"}>
              <Link
                href={exploreHref(params, { category: c.value || undefined })}
                aria-current={active ? "page" : undefined}
                className={`-mb-px inline-block border-b-2 px-3 py-2 text-sm ${
                  active
                    ? "border-accent font-medium text-ink"
                    : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {c.label}
                {c.count !== undefined && <span className="ml-1 text-xs text-muted">{c.count}</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
