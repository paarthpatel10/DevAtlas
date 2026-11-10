"use client";

import { useEffect, useState } from "react";

import { CitationList, modelLabel } from "@/components/insights/citation-list";
import { ApiError, getBuildIdeas, getInsights } from "@/lib/api";
import type { Idea, InsightsOut } from "@/lib/types";

export function aiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "rate_limited") return "Too many AI requests right now. Try again in a minute.";
    if (error.code === "ai_unavailable")
      return "This needs an AI provider, and none is available right now. Try again later.";
    return error.message;
  }
  return "Something went wrong. Try again.";
}

export function WhyPanel({ owner, name }: { owner: string; name: string }) {
  const [data, setData] = useState<InsightsOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getInsights(owner, name).then(
      (result) => active && setData(result),
      (err: unknown) => active && setError(aiErrorMessage(err)),
    );
    return () => {
      active = false;
    };
  }, [owner, name]);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data) return <p className="text-sm text-muted">Loading…</p>;
  const points = data.report.why_interesting;
  return (
    <div className="space-y-3 text-sm">
      <div>
        <h4 className="text-xs font-semibold text-muted">Measured signals</h4>
        {data.why_trending.length > 0 ? (
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {data.why_trending.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-muted">No growth or release signals recorded yet.</p>
        )}
      </div>
      <div>
        <h4 className="text-xs font-semibold text-muted">What makes it notable</h4>
        {points.length > 0 ? (
          <ul className="mt-1 space-y-2">
            {points.map((p) => (
              <li key={p.point}>
                {p.point}
                <CitationList citations={p.citations} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-muted">Not established from the README yet.</p>
        )}
        {data.generated && (
          <p className="mt-2 text-xs text-muted">{modelLabel(data.model_name, data.generated_at)}</p>
        )}
      </div>
    </div>
  );
}

function IdeaList({ ideas }: { ideas: Idea[] }) {
  return (
    <ul className="space-y-3">
      {ideas.map((idea) => (
        <li key={idea.title}>
          <p className="font-medium">{idea.title}</p>
          <p>{idea.description}</p>
          <p className="text-muted">
            <span className="text-ink">How it is used:</span> {idea.how_it_is_used}
          </p>
          {idea.complementary_tech.length > 0 && (
            <p className="text-xs text-muted">
              Pairs well with (suggestion): {idea.complementary_tech.join(", ")}
            </p>
          )}
          <CitationList citations={idea.citations} />
        </li>
      ))}
    </ul>
  );
}

export function IdeasPanel({ owner, name }: { owner: string; name: string }) {
  const [ideas, setIdeas] = useState<Idea[] | null>(null);
  const [more, setMore] = useState<Idea[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let active = true;
    getBuildIdeas(owner, name).then(
      (result) => active && setIdeas(result.ideas),
      (err: unknown) => active && setError(aiErrorMessage(err)),
    );
    return () => {
      active = false;
    };
  }, [owner, name]);

  async function generateMore() {
    setPending(true);
    setError(null);
    try {
      const result = await getBuildIdeas(owner, name, true);
      setMore(result.ideas);
    } catch (err) {
      setError(aiErrorMessage(err));
    } finally {
      setPending(false);
    }
  }

  if (ideas === null && !error) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <div className="space-y-3 text-sm">
      {ideas && ideas.length > 0 ? (
        <IdeaList ideas={ideas} />
      ) : (
        ideas && <p className="text-muted">No project ideas stored for this repository yet.</p>
      )}
      {more.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-muted">More ideas</h4>
          <IdeaList ideas={more} />
        </div>
      )}
      {error && <p role="status" className="text-danger">{error}</p>}
      <button
        type="button"
        onClick={generateMore}
        disabled={pending}
        className="rounded border border-rule bg-surface px-2.5 py-1 text-xs hover:border-ink disabled:opacity-60"
      >
        {pending ? "Generating…" : "Generate more ideas"}
      </button>
      <p className="text-xs text-muted">
        Ideas are AI suggestions based on capabilities the README describes.
      </p>
    </div>
  );
}
