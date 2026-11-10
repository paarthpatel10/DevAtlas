import { Check, CircleHelp, ExternalLink, Minus } from "lucide-react";
import Link from "next/link";

import { LicenseLabel, StarsMetric } from "@/components/repository/meta";
import { RepoName, repoHref } from "@/components/repository/repository-card";
import { SaveButton } from "@/components/repository/save-button";
import type { CompatibilityNote, Evidence, Recommendation } from "@/lib/types";

function EvidenceQuote({ evidence }: { evidence: Evidence }) {
  const where = evidence.source_type === "metadata" ? "GitHub metadata" : "README";
  return (
    <figure className="mt-1.5">
      <blockquote className="border-l-2 border-accent bg-accent-soft/50 py-1 pl-3 pr-2 text-[13px] leading-relaxed">
        {evidence.snippet}
      </blockquote>
      <figcaption className="mt-0.5 text-xs text-muted">
        {where}
        {evidence.section_title && evidence.source_type !== "metadata" && (
          <> — section “{evidence.section_title}”</>
        )}
        {evidence.source_url && (
          <>
            {" "}
            <a
              href={evidence.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              View source
            </a>
          </>
        )}
      </figcaption>
    </figure>
  );
}

const COMPAT_LABEL: Record<CompatibilityNote["status"], string> = {
  evidenced: "Evidenced",
  inferred: "Inferred",
  not_established: "Not established",
};

const COMPAT_STYLE: Record<CompatibilityNote["status"], string> = {
  evidenced: "border-accent/50 text-accent",
  inferred: "border-amber/50 bg-amber-soft text-amber",
  not_established: "border-rule text-muted",
};

export function RecommendationCard({ rec }: { rec: Recommendation }) {
  const repo = rec.repository;
  const headingId = `rec-${rec.rank}-${repo.id}`;
  const { signals } = rec;
  return (
    <article aria-labelledby={headingId} className="rounded border border-rule bg-surface p-4 sm:p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id={headingId} className="flex items-baseline gap-2 text-base">
            <span className="text-sm text-muted" aria-label={`Rank ${rec.rank}`}>
              {rec.rank}.
            </span>
            <Link href={repoHref(repo)} className="hover:text-accent hover:underline">
              <RepoName repo={repo} />
            </Link>
          </h3>
          {repo.description && <p className="mt-1 max-w-2xl text-sm">{repo.description}</p>}
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            {repo.primary_language && <span className="text-ink">{repo.primary_language}</span>}
            <StarsMetric stars={repo.stars} />
            <LicenseLabel spdx={repo.license_spdx} name={repo.license_name} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <SaveButton owner={repo.owner} name={repo.name} initialSaved={repo.is_saved} />
          <a
            href={repo.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 px-1 text-sm text-muted hover:text-ink"
          >
            GitHub <ExternalLink aria-hidden size={13} />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </div>
      </header>

      <div className="mt-4 grid gap-5 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-label="Requirements checked against the source">
          <h4 className="text-xs font-semibold text-muted">Your requirements</h4>
          {rec.requirements.length === 0 ? (
            <p className="mt-1 text-sm text-muted">
              No specific requirements recognised in the request; matched on your wording.
            </p>
          ) : (
            <ul className="mt-1.5 space-y-3">
              {rec.requirements.map((req) => (
                <li key={req.requirement}>
                  <div className="flex items-center gap-2 text-sm">
                    {req.status === "evidenced" ? (
                      <Check aria-hidden size={15} className="text-accent" />
                    ) : (
                      <Minus aria-hidden size={15} className="text-muted" />
                    )}
                    <span className="font-medium">{req.requirement}</span>
                    <span
                      className={`text-xs ${req.status === "evidenced" ? "text-accent" : "text-muted"}`}
                    >
                      {req.status === "evidenced" ? "Mentioned in source" : "Not established"}
                    </span>
                  </div>
                  {req.evidence.map((ev) => (
                    <EvidenceQuote key={`${ev.source_url}-${ev.snippet}`} evidence={ev} />
                  ))}
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="space-y-4 text-sm">
          <section aria-label="Why it fits">
            <h4 className="text-xs font-semibold text-muted">Why it fits</h4>
            <ul className="mt-1 space-y-0.5">
              {rec.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </section>
          {rec.compatibility.length > 0 && (
            <section aria-label="Compatibility with your stack">
              <h4 className="text-xs font-semibold text-muted">With your stack</h4>
              <ul className="mt-1 space-y-1.5">
                {rec.compatibility.map((c) => (
                  <li key={c.stack_item}>
                    <span className="font-medium">{c.stack_item}</span>{" "}
                    <span
                      className={`ml-1 rounded border px-1.5 text-xs ${COMPAT_STYLE[c.status]}`}
                    >
                      {COMPAT_LABEL[c.status]}
                    </span>
                    <p className="text-xs text-muted">{c.note}</p>
                    {c.evidence && <EvidenceQuote evidence={c.evidence} />}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {rec.limitations.length > 0 && (
            <section aria-label="Limitations">
              <h4 className="text-xs font-semibold text-muted">Limitations and unknowns</h4>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted">
                {rec.limitations.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>

      <details className="mt-4 border-t border-rule pt-2 text-xs text-muted">
        <summary className="flex cursor-pointer items-center gap-1.5">
          <CircleHelp aria-hidden size={13} />
          <span>
            Keyword rank {signals.keyword_rank ?? "none"}, semantic rank{" "}
            {signals.semantic_rank ?? "none"}, {signals.requirements_evidenced} of{" "}
            {signals.requirements_total} requirements evidenced
          </span>
        </summary>
        <p className="mt-1.5 max-w-prose">
          Results from keyword search and semantic search are merged with Reciprocal Rank Fusion
          (score {signals.rrf_score.toFixed(4)}), then ordered by how many of your requirements
          the repository&apos;s own text mentions. The score is for ordering only, not a measure
          of fit. Popularity is not used.
        </p>
      </details>
    </article>
  );
}
