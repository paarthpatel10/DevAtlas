import { ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { ForksMetric, LicenseLabel, StarsMetric } from "@/components/repository/meta";
import { CompareButton } from "@/components/compare/compare-button";
import { AskPanel } from "@/components/insights/ask-panel";
import { ReportSections } from "@/components/insights/report-sections";
import { RepoName, repoHref } from "@/components/repository/repository-card";
import { SaveButton } from "@/components/repository/save-button";
import { RefreshError } from "@/components/states/refresh-error";
import { ApiError, getInsights, getRepository } from "@/lib/api";
import { formatCount, formatDate, snapshotLabel } from "@/lib/format";
import type { InsightsOut, RepositoryDetail } from "@/lib/types";

type Props = PageProps<"/repositories/[owner]/[name]">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { owner, name } = await props.params;
  return { title: `${decodeURIComponent(owner)}/${decodeURIComponent(name)}` };
}

const NOT_ESTABLISHED = "Not established by the demo analyzer.";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-rule pt-5">
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="mt-2 text-sm">{children}</div>
    </section>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  );
}

function TextList({ items }: { items: string[] }) {
  if (items.length === 0) return <p className="italic text-muted">{NOT_ESTABLISHED}</p>;
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function languageShares(languages: Record<string, number>) {
  const total = Object.values(languages).reduce((a, b) => a + b, 0);
  if (total === 0) return [];
  return Object.entries(languages)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, bytes]) => ({ name, percent: (bytes / total) * 100 }));
}

export default async function RepositoryPage(props: Props) {
  const { owner, name } = await props.params;
  let repo: RepositoryDetail;
  let insights: InsightsOut | null = null;
  try {
    const [o, n] = [decodeURIComponent(owner), decodeURIComponent(name)];
    // Insights are optional: if they fail, the page still shows the repository facts.
    [repo, insights] = await Promise.all([getRepository(o, n), getInsights(o, n).catch(() => null)]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    const message = error instanceof ApiError ? error.message : "The repository could not load.";
    return <RefreshError title="This repository couldn't load" message={message} />;
  }
  const analysis = repo.analysis;
  const readmeUrl = repo.readme_url ?? repo.html_url;

  return (
    <article className="space-y-6">
      <header className="space-y-3">
        <p className="text-sm">
          <Link href="/explore" className="text-muted hover:text-ink hover:underline">
            Explore
          </Link>
          <span className="text-muted"> / {repo.category_label}</span>
        </p>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h1 className="text-2xl tracking-tight">
            <RepoName repo={repo} />
          </h1>
          <div className="flex items-center gap-2">
            <SaveButton owner={repo.owner} name={repo.name} initialSaved={repo.is_saved} />
            <CompareButton fullName={repo.full_name} />
            <a
              href={repo.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded border border-rule bg-surface px-2.5 py-1 text-sm hover:border-ink"
            >
              View on GitHub <ExternalLink aria-hidden size={13} />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          </div>
        </div>
        {repo.description ? (
          <p className="max-w-3xl">{repo.description}</p>
        ) : (
          <p className="italic text-muted">No description on GitHub.</p>
        )}
        {repo.archived && (
          <p className="rounded border border-amber/50 bg-amber-soft px-3 py-2 text-sm text-amber">
            This repository is archived on GitHub and is read-only.
          </p>
        )}
        <dl className="grid grid-cols-2 gap-4 rounded border border-rule bg-surface p-4 sm:grid-cols-4 lg:grid-cols-7">
          <Fact label="Stars">
            <StarsMetric stars={repo.stars} />
          </Fact>
          <Fact label="Forks">
            <ForksMetric forks={repo.forks} />
          </Fact>
          <Fact label="Open issues">{formatCount(repo.open_issues)}</Fact>
          <Fact label="Language">{repo.primary_language ?? "Not available"}</Fact>
          <Fact label="License">
            <LicenseLabel spdx={repo.license_spdx} name={repo.license_name} />
          </Fact>
          <Fact label="Last push">{formatDate(repo.pushed_at_github)}</Fact>
          <Fact label="Data">{snapshotLabel(repo.data_source, repo.source_fetched_at)}</Fact>
        </dl>
      </header>

      <div className="grid gap-8 lg:grid-cols-[1fr_18rem]">
        {insights ? (
          <div className="space-y-6">
            <ReportSections insights={insights} readmeUrl={readmeUrl} owner={repo.owner} name={repo.name} />
            <AskPanel owner={repo.owner} name={repo.name} />
          </div>
        ) : (
        <div className="space-y-6">
          <Section title="Overview">
            {analysis?.summary ? (
              <p className="max-w-prose">{analysis.summary}</p>
            ) : (
              <p className="italic text-muted">{NOT_ESTABLISHED}</p>
            )}
            {analysis && (
              <p className="mt-2 text-xs text-muted">
                {analysis.generated_by_label}. Generated analysis, not official project
                documentation.
              </p>
            )}
          </Section>

          <Section title="Capabilities">
            {analysis && analysis.capabilities.length > 0 ? (
              <ul className="space-y-3">
                {analysis.capabilities.map((cap) => (
                  <li key={cap.name}>
                    <p className="font-medium">{cap.name}</p>
                    {cap.evidence.map((quote) => (
                      <blockquote
                        key={quote}
                        className="mt-1 border-l-2 border-accent pl-3 text-muted"
                      >
                        {quote}
                      </blockquote>
                    ))}
                    <a
                      href={readmeUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 inline-block text-xs text-accent hover:underline"
                    >
                      Source: README
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="italic text-muted">
                No feature list found in the README. Read it on GitHub for details.
              </p>
            )}
          </Section>

          <Section title="Problem it solves">
            {analysis?.problem_solved ? (
              <p>{analysis.problem_solved}</p>
            ) : (
              <p className="italic text-muted">{NOT_ESTABLISHED}</p>
            )}
          </Section>
          <Section title="Common use cases">
            <TextList items={analysis?.use_cases ?? []} />
          </Section>
          <Section title="Limitations and considerations">
            <TextList items={analysis?.limitations ?? []} />
          </Section>
        </div>

        )}

        <aside className="space-y-6">
          <Section title="Maintenance signals">
            {repo.maintenance_signals.length > 0 ? (
              <ul className="space-y-2">
                {repo.maintenance_signals.map((s) => (
                  <li key={s.label}>
                    <p>
                      <span className="text-muted">{s.label}:</span> {s.value}
                    </p>
                    <p className="text-xs text-muted">{s.explanation}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="italic text-muted">No maintenance data available.</p>
            )}
          </Section>

          <Section title="Languages">
            {languageShares(repo.languages).length > 0 ? (
              <ul className="space-y-1.5">
                {languageShares(repo.languages).map((l) => (
                  <li key={l.name}>
                    <div className="flex justify-between text-xs">
                      <span>{l.name}</span>
                      <span className="text-muted">{l.percent.toFixed(1)}%</span>
                    </div>
                    <div className="mt-0.5 h-1 rounded bg-rule">
                      <div className="h-1 rounded bg-accent" style={{ width: `${l.percent}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="italic text-muted">Not available.</p>
            )}
          </Section>

          <Section title="Sources">
            <ul className="space-y-1">
              {repo.sources.map((s) => (
                <li key={s.url}>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    {s.label}
                  </a>
                </li>
              ))}
            </ul>
            {repo.readme_truncated && (
              <p className="mt-2 text-xs text-muted">
                Only the first 40,000 characters of the README were indexed.
              </p>
            )}
          </Section>

          {insights && insights.related.length > 0 && (
            <Section title="Related in the index">
              <ul className="space-y-1.5">
                {insights.related.map((r) => (
                  <li key={r.id}>
                    <Link href={repoHref(r)} className="hover:text-accent hover:underline">
                      <RepoName repo={r} />
                    </Link>
                    {r.description && <p className="line-clamp-2 text-xs text-muted">{r.description}</p>}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">Similar projects in the same category, not ranked as better.</p>
            </Section>
          )}

          <Section title="Looking for alternatives?">
            <Link
              href={`/ask?q=${encodeURIComponent(`Alternatives to ${repo.full_name}`)}`}
              className="text-accent hover:underline"
            >
              Ask AI for alternatives to {repo.name}
            </Link>
          </Section>
        </aside>
      </div>
    </article>
  );
}
