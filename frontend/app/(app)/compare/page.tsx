import type { Metadata } from "next";

import { CompareView } from "@/components/compare/compare-view";

export const metadata: Metadata = { title: "Compare" };

export default function ComparePage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Compare repositories</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          The same dimensions for every repository, so differences are easy to scan.
        </p>
      </div>
      <CompareView />
    </div>
  );
}
