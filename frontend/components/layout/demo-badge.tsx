import { getHealth } from "@/lib/api";

/** Shows whether the app runs on mock AI, and whether the API is reachable. */
export async function DemoBadge() {
  const health = await getHealth().catch(() => null);
  if (health === null) {
    return (
      <span
        className="rounded border border-danger/40 bg-danger-soft px-2 py-1 text-xs text-danger"
        title="The frontend cannot reach the backend API. Start it with: uv run uvicorn app.main:app"
      >
        API unreachable
      </span>
    );
  }
  if (health.database !== "ok") {
    return (
      <span className="rounded border border-amber/40 bg-amber-soft px-2 py-1 text-xs text-amber">
        Database unavailable
      </span>
    );
  }
  if (!health.demo_mode) return null;
  return (
    <span
      className="rounded border border-rule px-2 py-1 text-xs text-muted"
      title="Mock AI provider: lexical embeddings and extractive analysis, no LLM."
    >
      Demo mode: mock AI
    </span>
  );
}
