"use client";

import { useRef, useState } from "react";

import { aiErrorMessage } from "@/components/discover/panels";
import { CitationList } from "@/components/insights/citation-list";
import { askRepository } from "@/lib/api";
import type { AskOut } from "@/lib/types";

const SUGGESTED = [
  "Explain this repository in simple terms.",
  "How does it work internally?",
  "What makes it different from existing alternatives?",
  "Can I use it in my FastAPI project?",
  "Can I integrate it with Next.js?",
  "What can I build using this?",
  "Is it suitable for production?",
  "What should I know before adopting it?",
];

type State =
  | { kind: "idle" }
  | { kind: "loading"; question: string }
  | { kind: "done"; question: string; result: AskOut }
  | { kind: "error"; question: string; message: string };

export function AskPanel({ owner, name }: { owner: string; name: string }) {
  const [text, setText] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);
  const [state, setState] = useState<State>({ kind: "idle" });
  const latest = useRef(0);

  function ask(raw: string) {
    const question = raw.trim();
    if (question.length < 3) return setInvalid("Enter at least 3 characters.");
    if (question.length > 500) return setInvalid("Keep it under 500 characters.");
    setInvalid(null);
    const id = ++latest.current;
    setState({ kind: "loading", question });
    askRepository(owner, name, question).then(
      (result) => id === latest.current && setState({ kind: "done", question, result }),
      (error: unknown) =>
        id === latest.current && setState({ kind: "error", question, message: aiErrorMessage(error) }),
    );
  }

  return (
    <section aria-labelledby="ask-repo-heading" className="space-y-3 rounded border border-rule bg-surface p-4">
      <h2 id="ask-repo-heading" className="text-sm font-semibold">
        Ask AI about this repository
      </h2>
      <p className="text-xs text-muted">
        Answers use only this repository&apos;s README and GitHub metadata, with sources.
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {SUGGESTED.map((q) => (
          <li key={q}>
            <button
              type="button"
              onClick={() => {
                setText(q);
                ask(q);
              }}
              className="rounded border border-rule px-2 py-1 text-xs hover:border-accent"
            >
              {q}
            </button>
          </li>
        ))}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
        className="flex flex-col gap-2 sm:flex-row"
      >
        <label htmlFor="ask-repo-input" className="sr-only">
          Ask about this repository
        </label>
        <input
          id="ask-repo-input"
          value={text}
          maxLength={500}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask a question about this repository"
          className="flex-1 rounded border border-rule bg-paper px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={state.kind === "loading"}
          className="rounded bg-accent px-3 py-2 text-sm font-medium text-accent-ink disabled:opacity-60"
        >
          Ask
        </button>
      </form>
      {invalid && <p className="text-xs text-danger">{invalid}</p>}

      <div aria-live="polite">
        {state.kind === "loading" && <p className="text-sm text-muted">Reading the documentation…</p>}
        {state.kind === "error" && <p className="text-sm text-danger">{state.message}</p>}
        {state.kind === "done" && (
          <div className="space-y-1 text-sm">
            <p className="text-xs text-muted">Q: {state.question}</p>
            <p className={state.result.covered ? "" : "italic text-muted"}>{state.result.answer}</p>
            <CitationList citations={state.result.citations} />
          </div>
        )}
      </div>
    </section>
  );
}
