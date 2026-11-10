"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import type { CategorySummary, Period } from "@/lib/types";

export function discoverHref(
  base: string,
  params: Record<string, string | undefined>,
  changes: Record<string, string | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...params, ...changes })) if (v) search.set(k, v);
  if (!("page" in changes)) search.delete("page");
  const text = search.toString();
  return text ? `${base}?${text}` : base;
}

export function CategoryTabs({
  base,
  params,
  categories,
}: {
  base: string;
  params: Record<string, string | undefined>;
  categories: CategorySummary[];
}) {
  const items = [{ value: "", label: "All categories", count: undefined as number | undefined }, ...categories];
  return (
    <nav aria-label="Categories" className="-mx-4 overflow-x-auto px-4">
      <ul className="flex gap-1 whitespace-nowrap border-b border-rule">
        {items.map((c) => {
          const active = (params.category ?? "") === c.value;
          return (
            <li key={c.value || "all"}>
              <Link
                href={discoverHref(base, params, { category: c.value || undefined })}
                aria-current={active ? "page" : undefined}
                className={`-mb-px inline-block border-b-2 px-3 py-2 text-sm ${
                  active ? "border-accent font-medium text-ink" : "border-transparent text-muted hover:text-ink"
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

export function LanguageSelect({
  base,
  params,
  languages,
}: {
  base: string;
  params: Record<string, string | undefined>;
  languages: string[];
}) {
  const router = useRouter();
  return (
    <label htmlFor="discover-language" className="flex items-center gap-2 text-xs text-muted">
      Language
      <select
        id="discover-language"
        value={params.language ?? ""}
        onChange={(e) => router.push(discoverHref(base, params, { language: e.target.value || undefined }))}
        className="rounded border border-rule bg-surface px-2 py-1.5 text-sm text-ink"
      >
        <option value="">Any language</option>
        {languages.map((l) => (
          <option key={l} value={l}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

const PERIODS: { value: Period; label: string }[] = [
  { value: "day", label: "Today" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
];

export function PeriodTabs({
  base,
  params,
}: {
  base: string;
  params: Record<string, string | undefined>;
}) {
  const current = params.period ?? "week";
  return (
    <div role="group" aria-label="Trending period" className="inline-flex rounded border border-rule bg-surface p-0.5">
      {PERIODS.map((p) => (
        <Link
          key={p.value}
          href={discoverHref(base, params, { period: p.value === "week" ? undefined : p.value })}
          aria-current={current === p.value ? "true" : undefined}
          scroll={false}
          className={`rounded px-2.5 py-1 text-xs ${
            current === p.value ? "bg-accent text-accent-ink" : "text-muted hover:text-ink"
          }`}
        >
          {p.label}
        </Link>
      ))}
    </div>
  );
}
