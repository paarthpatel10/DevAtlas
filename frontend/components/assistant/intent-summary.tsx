import type { QueryIntent } from "@/lib/types";

export function IntentSummary({ intent }: { intent: QueryIntent }) {
  const stack = Object.values(intent.known_stack).flat();
  const nothing =
    intent.requirements.length === 0 && stack.length === 0 && intent.constraints.length === 0;
  return (
    <section
      aria-label="How your request was read"
      className="rounded border border-rule bg-surface px-4 py-3 text-sm"
    >
      <h2 className="text-xs font-semibold text-muted">How I read your request</h2>
      {nothing ? (
        <p className="mt-1 text-muted">
          No specific requirements or technologies recognised; results are matched on your
          wording.
        </p>
      ) : (
        <dl className="mt-1.5 grid gap-x-6 gap-y-1 sm:grid-cols-[auto_1fr]">
          {intent.requirements.length > 0 && (
            <>
              <dt className="text-muted">Requirements</dt>
              <dd>{intent.requirements.join(", ")}</dd>
            </>
          )}
          {stack.length > 0 && (
            <>
              <dt className="text-muted">Your stack</dt>
              <dd>{stack.join(", ")}</dd>
            </>
          )}
          {intent.constraints.length > 0 && (
            <>
              <dt className="text-muted">Constraints</dt>
              <dd>{intent.constraints.join("; ")}</dd>
            </>
          )}
        </dl>
      )}
      {intent.inferred.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-amber">
          {intent.inferred.map((note) => (
            <li key={note}>Inferred: {note}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
