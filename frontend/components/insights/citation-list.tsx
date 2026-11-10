import type { Citation } from "@/lib/types";

/** Collapsible list of the README excerpts a claim is based on. */
export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <details className="mt-1 text-xs text-muted">
      <summary className="cursor-pointer select-none hover:text-ink">
        Sources ({citations.length})
      </summary>
      <ul className="mt-1 space-y-1.5">
        {citations.map((c) => (
          <li key={`${c.id}-${c.excerpt}`}>
            <blockquote className="border-l-2 border-accent pl-2 text-[12px] text-ink">
              {c.excerpt}
            </blockquote>
            <span>
              {c.section_title ? `README — “${c.section_title}”` : "README"}
              {c.source_url && (
                <>
                  {" "}
                  <a
                    href={c.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    View source
                  </a>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function modelLabel(modelName: string | null, generatedAt: string | null): string {
  const model = (modelName ?? "an AI model").replace(/^gemini:/, "");
  const date = generatedAt
    ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
        .format(new Date(generatedAt))
    : null;
  return `AI-generated with ${model}${date ? ` on ${date}` : ""} from the README; not official documentation.`;
}
