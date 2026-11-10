"use client";

import { useRouter } from "next/navigation";

import { exploreHref } from "@/components/search/url-state";
import type { Facets } from "@/lib/types";

const SORTS = [
  { value: "", label: "Default order" },
  { value: "stars", label: "Most stars" },
  { value: "recent", label: "Recently pushed" },
  { value: "name", label: "Name (A–Z)" },
];

function Select({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-xs text-muted">
      {label}
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-rule bg-surface px-2 py-1.5 text-sm text-ink"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function FilterBar({
  params,
  facets,
}: {
  params: Record<string, string | undefined>;
  facets: Facets;
}) {
  const router = useRouter();
  const set = (key: string) => (value: string) =>
    router.push(exploreHref(params, { [key]: value || undefined }));
  const active = Boolean(params.category || params.language || params.license || params.sort);

  return (
    <div className="flex flex-wrap items-end gap-3">
      <Select
        id="filter-language"
        label="Language"
        value={params.language ?? ""}
        onChange={set("language")}
        options={[
          { value: "", label: "Any language" },
          ...facets.languages.map((l) => ({ value: l.value, label: `${l.value} (${l.count})` })),
        ]}
      />
      <Select
        id="filter-license"
        label="License"
        value={params.license ?? ""}
        onChange={set("license")}
        options={[
          { value: "", label: "Any license" },
          ...facets.licenses.map((l) => ({ value: l.value, label: `${l.value} (${l.count})` })),
        ]}
      />
      <Select
        id="filter-sort"
        label="Sort"
        value={params.sort ?? ""}
        onChange={set("sort")}
        options={params.q ? [{ value: "", label: "Relevance" }, ...SORTS.slice(1)] : SORTS}
      />
      {active && (
        <button
          type="button"
          onClick={() => router.push(exploreHref({ q: params.q }, {}))}
          className="rounded px-2 py-1.5 text-sm text-accent hover:underline"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
