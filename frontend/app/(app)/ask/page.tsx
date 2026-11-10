import type { Metadata } from "next";

import { AskView } from "@/components/assistant/ask-view";

export const metadata: Metadata = { title: "Ask AI" };

export default async function AskPage(props: PageProps<"/ask">) {
  const { q } = await props.searchParams;
  const initialQuery = typeof q === "string" ? q : undefined;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ask AI</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Describe a problem in your own words. You get a short list of repositories from the
          index, with quotes from each project&apos;s own README showing which of your
          requirements it mentions.
        </p>
      </div>
      <AskView key={initialQuery ?? ""} initialQuery={initialQuery} />
    </div>
  );
}
