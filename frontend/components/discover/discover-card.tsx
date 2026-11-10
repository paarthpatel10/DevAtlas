"use client";

import { Clock, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { CompareButton } from "@/components/compare/compare-button";
import { IdeasPanel, WhyPanel } from "@/components/discover/panels";
import { ForksMetric, LicenseLabel, Metric, StarsMetric } from "@/components/repository/meta";
import { RepoName, repoHref } from "@/components/repository/repository-card";
import { SaveButton } from "@/components/repository/save-button";
import { formatDate } from "@/lib/format";
import type { DiscoverItem, FeedLabel } from "@/lib/types";

export const LABEL_TEXT: Record<FeedLabel, string> = {
  trending: "Trending",
  rising: "Rising",
  new: "New",
  hidden_gem: "Hidden gem",
};

type Panel = "why" | "ideas" | null;

export function DiscoverCard({ item }: { item: DiscoverItem }) {
  const [panel, setPanel] = useState<Panel>(null);
  const toggle = (next: Panel) => setPanel((current) => (current === next ? null : next));
  const panelId = `panel-${item.id}`;

  return (
    <article className="flex flex-col gap-3 rounded border border-rule bg-surface p-4">
      <header className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <h3 className="text-[15px]">
          <Link href={repoHref(item)} className="hover:text-accent hover:underline">
            <RepoName repo={item} />
          </Link>
        </h3>
        {item.labels.map((label) => (
          <span key={label} className="rounded border border-accent/40 px-1.5 text-xs text-accent">
            {LABEL_TEXT[label]}
          </span>
        ))}
        <span className="text-xs text-muted">{item.category_label}</span>
      </header>

      {item.one_liner ? (
        <p className="text-sm">
          <span className="mr-1 rounded bg-accent-soft px-1 text-[11px] text-accent">AI summary</span>
          {item.one_liner}
        </p>
      ) : (
        item.description && <p className="line-clamp-2 text-sm">{item.description}</p>
      )}

      {item.signal_text.length > 0 && (
        <ul className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs" aria-label="Signals">
          {item.signal_text.map((text) => (
            <li key={text} className="text-ink">
              {text}
            </li>
          ))}
        </ul>
      )}

      {item.why_explore && (
        <p className="text-xs text-muted">
          <span className="font-medium text-ink">Why explore this? (AI) </span>
          {item.why_explore}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        {item.primary_language && <span className="text-ink">{item.primary_language}</span>}
        <StarsMetric stars={item.stars} />
        <ForksMetric forks={item.forks} />
        <LicenseLabel spdx={item.license_spdx} name={item.license_name} />
        <Metric icon={<Clock aria-hidden size={14} />} label="Last push" value={formatDate(item.pushed_at_github)} />
      </div>

      <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-rule pt-3">
        <Link
          href={repoHref(item)}
          className="rounded bg-accent px-2.5 py-1 text-sm font-medium text-accent-ink hover:opacity-90"
        >
          Explore
        </Link>
        <button
          type="button"
          aria-expanded={panel === "why"}
          aria-controls={panelId}
          onClick={() => toggle("why")}
          className="rounded border border-rule px-2.5 py-1 text-sm hover:border-ink"
        >
          Why is this interesting?
        </button>
        <button
          type="button"
          aria-expanded={panel === "ideas"}
          aria-controls={panelId}
          onClick={() => toggle("ideas")}
          className="rounded border border-rule px-2.5 py-1 text-sm hover:border-ink"
        >
          What can I build?
        </button>
        <SaveButton owner={item.owner} name={item.name} initialSaved={item.is_saved} />
        <CompareButton fullName={item.full_name} />
        <a
          href={item.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 px-1 text-sm text-muted hover:text-ink"
        >
          GitHub <ExternalLink aria-hidden size={13} />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      </div>

      {panel && (
        <section id={panelId} className="rounded bg-paper p-3" aria-live="polite">
          {panel === "why" ? (
            <WhyPanel owner={item.owner} name={item.name} />
          ) : (
            <IdeasPanel owner={item.owner} name={item.name} />
          )}
        </section>
      )}
    </article>
  );
}
