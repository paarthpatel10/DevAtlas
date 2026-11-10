"use client";

import Link from "next/link";
import { useState } from "react";

import { RepositoryCard } from "@/components/repository/repository-card";
import { EmptyState } from "@/components/states/states";
import type { RepositorySummary } from "@/lib/types";

export function SavedList({ initial }: { initial: RepositorySummary[] }) {
  const [items, setItems] = useState(initial);

  if (items.length === 0) {
    return (
      <EmptyState
        title="Nothing saved yet"
        message="Save repositories from Explore or Ask AI and they will appear here."
        action={
          <>
            <Link href="/explore" className="text-sm text-accent hover:underline">
              Go to Explore
            </Link>
            <Link href="/ask" className="text-sm text-accent hover:underline">
              Open Ask AI
            </Link>
          </>
        }
      />
    );
  }
  return (
    <section aria-label="Saved repositories" className="rounded border border-rule bg-surface px-4">
      {items.map((repo) => (
        <RepositoryCard
          key={repo.id}
          repo={repo}
          onSavedChange={(saved) => {
            if (!saved) setItems((current) => current.filter((r) => r.id !== repo.id));
          }}
        />
      ))}
    </section>
  );
}
