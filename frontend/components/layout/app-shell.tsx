import Link from "next/link";
import type { ReactNode } from "react";

import { DemoBadge } from "@/components/layout/demo-badge";
import { SiteNav } from "@/components/layout/site-nav";
import { BRAND_NAME } from "@/lib/brand";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <>
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="relative border-b border-rule bg-surface">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
          <Link href="/explore" className="flex items-center gap-2 font-semibold tracking-tight">
            <svg aria-hidden width="18" height="18" viewBox="0 0 18 18" className="text-accent">
              <circle cx="9" cy="9" r="7.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path d="M1.5 9h15M9 1.5c2.2 2 3.3 4.5 3.3 7.5S11.2 14.5 9 16.5C6.8 14.5 5.7 12 5.7 9S6.8 3.5 9 1.5Z" fill="none" stroke="currentColor" strokeWidth="1.2" />
            </svg>
            {BRAND_NAME}
          </Link>
          <SiteNav />
          <div className="ml-auto">
            <DemoBadge />
          </div>
        </div>
      </header>
      <main id="content" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:py-8">
        {children}
      </main>
      <footer className="border-t border-rule py-4 text-xs text-muted">
        <div className="mx-auto max-w-6xl px-4">
          Repository data comes from the GitHub API. Generated analysis is not official project
          documentation.
        </div>
      </footer>
    </>
  );
}
