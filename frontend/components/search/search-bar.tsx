"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { exploreHref } from "@/components/search/url-state";

export function SearchBar({ params }: { params: Record<string, string | undefined> }) {
  const router = useRouter();
  const [value, setValue] = useState(params.q ?? "");

  return (
    <div>
      <form
        role="search"
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          router.push(exploreHref(params, { q: value.trim() || undefined }));
        }}
      >
        <label htmlFor="explore-q" className="sr-only">
          Search repositories
        </label>
        <div className="relative flex-1">
          <Search
            aria-hidden
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
          />
          <input
            id="explore-q"
            type="search"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            maxLength={200}
            placeholder="Search by name, topic, or what you're trying to build"
            className="w-full rounded border border-rule bg-surface py-2 pl-9 pr-3 text-sm placeholder:text-muted focus:border-accent"
          />
        </div>
        <button
          type="submit"
          className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:opacity-90"
        >
          Search
        </button>
      </form>
      <p className="mt-2 text-sm text-muted">
        Have a specific problem?{" "}
        <Link
          href={value.trim() ? `/ask?q=${encodeURIComponent(value.trim())}` : "/ask"}
          className="text-accent underline-offset-2 hover:underline"
        >
          Describe it in Ask AI
        </Link>{" "}
        to get a shortlist with evidence.
      </p>
    </div>
  );
}
