"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { IntentSummary } from "@/components/assistant/intent-summary";
import { RecommendationCard } from "@/components/assistant/recommendation-card";
import { EmptyState, ErrorState } from "@/components/states/states";
import { ApiError, recommend } from "@/lib/api";
import type { RecommendResponse } from "@/lib/types";

const EXAMPLES = [
  "I am building a FastAPI application and need background jobs with retries and scheduling",
  "role-based access control for a multi-tenant SaaS using Next.js and FastAPI",
  "vector database for semantic similarity search over embeddings",
  "orchestrate data pipelines with scheduling and retries",
];

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "done"; response: RecommendResponse }
  | { kind: "error"; message: string };

function validate(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed.length < 3) return "Enter at least 3 characters.";
  if (trimmed.length > 1000) return "Keep it under 1,000 characters.";
  return null;
}

export function AskView({ initialQuery }: { initialQuery?: string }) {
  const [text, setText] = useState(initialQuery ?? "");
  const [invalid, setInvalid] = useState<string | null>(null);
  const [state, setState] = useState<State>(
    initialQuery && !validate(initialQuery) ? { kind: "loading" } : { kind: "idle" },
  );
  const [history, setHistory] = useState<string[]>([]);
  const lastQuery = useRef<string>("");
  const started = useRef(false);

  function fetchFor(query: string) {
    lastQuery.current = query;
    recommend({ query }).then(
      (response) => setState({ kind: "done", response }),
      (error: unknown) =>
        setState({
          kind: "error",
          message:
            error instanceof ApiError ? error.message : "The request failed. Try again shortly.",
        }),
    );
  }

  function run(raw: string) {
    const problem = validate(raw);
    setInvalid(problem);
    if (problem) return;
    const query = raw.trim();
    setHistory((h) => [query, ...h.filter((q) => q !== query)].slice(0, 8));
    setState({ kind: "loading" });
    fetchFor(query);
  }

  useEffect(() => {
    if (started.current || !initialQuery || validate(initialQuery)) return;
    started.current = true;
    fetchFor(initialQuery.trim());
  }, [initialQuery]);

  return (
    <div className="space-y-6">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(text);
        }}
        className="space-y-2"
      >
        <label htmlFor="ask-input" className="block text-sm font-medium">
          Describe what you&apos;re trying to build
        </label>
        <textarea
          id="ask-input"
          value={text}
          rows={3}
          maxLength={1000}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              run(text);
            }
          }}
          aria-invalid={invalid ? true : undefined}
          aria-describedby="ask-help"
          placeholder="For example: I need background jobs with retries for a project using FastAPI"
          className="w-full resize-y rounded border border-rule bg-surface px-3 py-2 text-[15px] placeholder:text-muted focus:border-accent"
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p id="ask-help" className={`text-xs ${invalid ? "text-danger" : "text-muted"}`}>
            {invalid ?? "Mention your stack and the requirements that matter. Enter to send, Shift+Enter for a new line."}
          </p>
          <button
            type="submit"
            disabled={state.kind === "loading"}
            className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:opacity-90 disabled:opacity-60"
          >
            {state.kind === "loading" ? "Searching…" : "Find repositories"}
          </button>
        </div>
      </form>

      {state.kind === "idle" && (
        <section aria-label="Example requests">
          <h2 className="text-xs font-semibold text-muted">Try an example</h2>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {EXAMPLES.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  onClick={() => {
                    setText(example);
                    run(example);
                  }}
                  className="h-full w-full rounded border border-rule bg-surface px-3 py-2 text-left text-sm hover:border-accent"
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {history.length > 1 && (
        <section aria-label="Earlier requests in this session" className="text-sm">
          <h2 className="text-xs font-semibold text-muted">This session</h2>
          <ul className="mt-1 flex flex-wrap gap-2">
            {history.slice(1).map((q) => (
              <li key={q}>
                <button
                  type="button"
                  onClick={() => {
                    setText(q);
                    run(q);
                  }}
                  className="max-w-xs truncate rounded border border-rule px-2 py-1 text-xs text-muted hover:text-ink"
                  title={q}
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div aria-live="polite" aria-busy={state.kind === "loading"}>
        {state.kind === "loading" && (
          <div role="status" className="space-y-3">
            <p className="text-sm text-muted">Searching the repository index…</p>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-32 animate-pulse rounded border border-rule bg-surface" />
            ))}
          </div>
        )}

        {state.kind === "error" && (
          <ErrorState
            title="Couldn't get recommendations"
            message={state.message}
            onRetry={() => {
              setState({ kind: "loading" });
              fetchFor(lastQuery.current);
            }}
          />
        )}

        {state.kind === "done" && <Results response={state.response} />}
      </div>
    </div>
  );
}

function Results({ response }: { response: RecommendResponse }) {
  const { results, pipeline } = response;
  return (
    <div className="space-y-4">
      {response.clarifying_question && (
        <p className="rounded border border-amber/50 bg-amber-soft px-4 py-3 text-sm text-amber">
          {response.clarifying_question}
        </p>
      )}
      <IntentSummary intent={response.intent} />
      {results.length === 0 ? (
        <EmptyState
          title="No matching repositories"
          message={
            <ul className="space-y-1">
              {pipeline.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          }
          action={
            <Link href="/explore" className="text-sm text-accent hover:underline">
              Browse Explore
            </Link>
          }
        />
      ) : (
        <>
          <h2 className="text-sm text-muted">
            {results.length} {results.length === 1 ? "repository" : "repositories"} with
            supporting evidence
          </h2>
          {results.map((rec) => (
            <RecommendationCard key={rec.repository.id} rec={rec} />
          ))}
          <ul className="space-y-0.5 text-xs text-muted">
            {pipeline.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
