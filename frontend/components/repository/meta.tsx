import { GitFork, Scale, Star } from "lucide-react";
import type { ReactNode } from "react";

import { formatCount, NOT_AVAILABLE } from "@/lib/format";

/** A labelled value. The label is visible to screen readers; the icon is decorative. */
export function Metric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <span className="inline-flex items-center gap-1" title={label}>
      {icon}
      <span className="sr-only">{label}:</span>
      <span className={value === NOT_AVAILABLE ? "text-muted italic" : undefined}>{value}</span>
    </span>
  );
}

export function StarsMetric({ stars }: { stars: number | null }) {
  return <Metric icon={<Star aria-hidden size={14} />} label="Stars" value={formatCount(stars)} />;
}

export function ForksMetric({ forks }: { forks: number | null }) {
  return (
    <Metric icon={<GitFork aria-hidden size={14} />} label="Forks" value={formatCount(forks)} />
  );
}

/** License as GitHub reports it; an unrecognised license is shown as such, never guessed. */
export function LicenseLabel({ spdx, name }: { spdx: string | null; name: string | null }) {
  const value = spdx ?? (name ? `${name} (unverified)` : "License not detected");
  return (
    <span className="inline-flex items-center gap-1" title="License (from GitHub metadata)">
      <Scale aria-hidden size={14} />
      <span className="sr-only">License:</span>
      <span className={spdx ? undefined : "text-muted italic"}>{value}</span>
    </span>
  );
}
