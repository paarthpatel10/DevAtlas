import { Clock, ExternalLink } from "lucide-react";
import Link from "next/link";

import { ForksMetric, LicenseLabel, Metric, StarsMetric } from "@/components/repository/meta";
import { SaveButton } from "@/components/repository/save-button";
import { formatDate } from "@/lib/format";
import type { RepositorySummary } from "@/lib/types";

export function repoHref(repo: Pick<RepositorySummary, "owner" | "name">) {
  return `/repositories/${encodeURIComponent(repo.owner)}/${encodeURIComponent(repo.name)}`;
}

export function RepoName({ repo }: { repo: Pick<RepositorySummary, "owner" | "name"> }) {
  return (
    <span className="font-mono">
      <span className="text-muted">{repo.owner}/</span>
      <span className="font-semibold">{repo.name}</span>
    </span>
  );
}

/** One gazetteer entry: identity, what it is, verifiable facts, then actions. */
export function RepositoryCard({
  repo,
  onSavedChange,
}: {
  repo: RepositorySummary;
  onSavedChange?: (saved: boolean) => void;
}) {
  return (
    <article className="grid gap-3 border-b border-rule py-4 last:border-b-0 sm:grid-cols-[1fr_auto]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-[15px]">
            <Link href={repoHref(repo)} className="hover:text-accent hover:underline">
              <RepoName repo={repo} />
            </Link>
          </h3>
          <span className="text-xs text-muted">{repo.category_label}</span>
          {repo.archived && (
            <span className="rounded border border-amber/50 px-1.5 text-xs text-amber">
              Archived
            </span>
          )}
        </div>
        {repo.description && (
          <p className="mt-1 line-clamp-2 max-w-3xl text-sm">{repo.description}</p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          {repo.primary_language && <span className="text-ink">{repo.primary_language}</span>}
          <StarsMetric stars={repo.stars} />
          <ForksMetric forks={repo.forks} />
          <LicenseLabel spdx={repo.license_spdx} name={repo.license_name} />
          <Metric
            icon={<Clock aria-hidden size={14} />}
            label="Last push"
            value={formatDate(repo.pushed_at_github)}
          />
        </div>
        {repo.topics.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Topics">
            {repo.topics.slice(0, 4).map((topic) => (
              <li key={topic} className="rounded bg-accent-soft px-1.5 py-0.5 text-xs text-accent">
                {topic}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex items-start gap-2 sm:flex-col sm:items-end">
        <SaveButton
          owner={repo.owner}
          name={repo.name}
          initialSaved={repo.is_saved}
          onChange={onSavedChange}
        />
        <a
          href={repo.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 px-1 py-1 text-sm text-muted hover:text-ink"
        >
          GitHub
          <ExternalLink aria-hidden size={13} />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      </div>
    </article>
  );
}
