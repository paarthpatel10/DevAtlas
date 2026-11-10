"use client";

import { useState } from "react";

import { aiErrorMessage } from "@/components/discover/panels";
import { CitationList } from "@/components/insights/citation-list";
import { getBuildIdeas } from "@/lib/api";
import type { Idea } from "@/lib/types";

export function MoreIdeas({ owner, name }: { owner: string; name: string }) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function load() {
    setPending(true);
    setError(null);
    try {
      setIdeas((await getBuildIdeas(owner, name, true)).ideas);
    } catch (err) {
      setError(aiErrorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-2">
      {ideas.length > 0 && (
        <ul className="space-y-3">
          {ideas.map((idea) => (
            <li key={idea.title}>
              <p className="font-medium">{idea.title}</p>
              <p>{idea.description}</p>
              <p className="text-muted">
                <span className="text-ink">How it is used:</span> {idea.how_it_is_used}
              </p>
              <CitationList citations={idea.citations} />
            </li>
          ))}
        </ul>
      )}
      {error && <p role="status" className="text-danger">{error}</p>}
      <button
        type="button"
        onClick={load}
        disabled={pending}
        className="rounded border border-rule bg-surface px-2.5 py-1 text-xs hover:border-ink disabled:opacity-60"
      >
        {pending ? "Generating…" : "Generate more ideas"}
      </button>
    </div>
  );
}
