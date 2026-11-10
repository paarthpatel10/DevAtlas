"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { RepoName, repoHref } from "@/components/repository/repository-card";
import { ErrorState } from "@/components/states/states";
import { ApiError, compareRepositories } from "@/lib/api";
import { toggleCompare, useCompareList } from "@/lib/compare-store";
import type { CompareOut } from "@/lib/types";

type Loaded = { key: string; data?: CompareOut; error?: string };

function Value({ value }: { value: string | null }) {
  return value ? <>{value}</> : <span className="italic text-muted">Not established</span>;
}

export function CompareView() {
  const list = useCompareList();
  const key = list.join(",");
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (list.length < 2) return;
    let active = true;
    compareRepositories(list).then(
      (data) => active && setLoaded({ key, data }),
      (error: unknown) =>
        active &&
        setLoaded({
          key,
          error: error instanceof ApiError ? error.message : "The comparison could not load.",
        }),
    );
    return () => {
      active = false;
    };
    // `key` captures the list contents; `attempt` re-runs after Retry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  if (list.length < 2) {
    return (
      <div className="rounded border border-dashed border-rule px-6 py-10 text-center text-sm">
        <p className="font-semibold">Add at least two repositories to compare.</p>
        <p className="mt-1 text-muted">
          Use the Compare button on any repository in{" "}
          <Link href="/discover" className="text-accent hover:underline">
            Discover
          </Link>{" "}
          or on a repository page. You can compare up to four.
        </p>
        {list.length === 1 && <p className="mt-2 text-muted">Selected so far: {list[0]}</p>}
      </div>
    );
  }
  const current = loaded?.key === key ? loaded : null;
  if (current?.error) {
    return <ErrorState title="Comparison couldn't load" message={current.error} onRetry={() => setAttempt((a) => a + 1)} />;
  }
  if (!current?.data) {
    return <p role="status" className="text-sm text-muted">Comparing {list.length} repositories…</p>;
  }
  const { dimensions, rows } = current.data;
  const remove = (fullName: string) => (
    <button
      type="button"
      aria-label={`Remove ${fullName}`}
      onClick={() => toggleCompare(fullName)}
      className="rounded p-1 text-muted hover:text-ink"
    >
      <X aria-hidden size={14} />
    </button>
  );

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        No overall winner: each repository fits different situations. Values come from GitHub
        metadata and the repositories&apos; own READMEs.
      </p>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th scope="col" className="w-40 border-b border-rule p-2 text-left text-xs text-muted">
                Dimension
              </th>
              {rows.map((row) => (
                <th key={row.repository.id} scope="col" className="border-b border-rule p-2 text-left align-top">
                  <div className="flex items-start justify-between gap-2">
                    <Link href={repoHref(row.repository)} className="hover:text-accent hover:underline">
                      <RepoName repo={row.repository} />
                    </Link>
                    {remove(row.repository.full_name)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dimensions.map((dimension) => (
              <tr key={dimension} className="align-top">
                <th scope="row" className="border-b border-rule p-2 text-left text-xs font-medium text-muted">
                  {dimension}
                </th>
                {rows.map((row) => (
                  <td key={row.repository.id} className="border-b border-rule p-2">
                    <Value value={row.values[dimension] ?? null} />
                  </td>
                ))}
              </tr>
            ))}
            <tr className="align-top">
              <th scope="row" className="p-2 text-left text-xs font-medium text-muted">
                Fits when
              </th>
              {rows.map((row) => (
                <td key={row.repository.id} className="p-2">
                  {row.fits_when.length > 0 ? (
                    <ul className="list-disc space-y-0.5 pl-4">
                      {row.fits_when.map((f) => (
                        <li key={f}>{f}</li>
                      ))}
                    </ul>
                  ) : (
                    <Value value={null} />
                  )}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="space-y-4 md:hidden">
        {rows.map((row) => (
          <section key={row.repository.id} className="rounded border border-rule bg-surface p-4 text-sm">
            <div className="flex items-start justify-between gap-2">
              <Link href={repoHref(row.repository)} className="hover:text-accent hover:underline">
                <RepoName repo={row.repository} />
              </Link>
              {remove(row.repository.full_name)}
            </div>
            <dl className="mt-3 space-y-2">
              {dimensions.map((dimension) => (
                <div key={dimension}>
                  <dt className="text-xs text-muted">{dimension}</dt>
                  <dd>
                    <Value value={row.values[dimension] ?? null} />
                  </dd>
                </div>
              ))}
              <div>
                <dt className="text-xs text-muted">Fits when</dt>
                <dd>{row.fits_when.length > 0 ? row.fits_when.join("; ") : <Value value={null} />}</dd>
              </div>
            </dl>
          </section>
        ))}
      </div>
    </div>
  );
}
