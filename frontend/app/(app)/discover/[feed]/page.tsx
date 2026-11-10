import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PeriodTabs } from "@/components/discover/discover-filters";
import { FeedSection } from "@/components/discover/feed-section";
import { Pagination } from "@/components/search/pagination";
import { RefreshError } from "@/components/states/refresh-error";
import { ApiError, getFeed } from "@/lib/api";
import type { FeedName, FeedPage, Period } from "@/lib/types";

const FEEDS: Record<FeedName, { title: string; description: string }> = {
  trending: { title: "Trending", description: "What's gaining stars on GitHub right now, from GitHub Trending." },
  rising: {
    title: "Rising",
    description: "Repeatedly on GitHub Trending this week: momentum, not a one-day spike.",
  },
  new: { title: "New and recently discovered", description: "Created recently, newly found, or newly released." },
  "hidden-gems": {
    title: "Hidden gems",
    description: "Fewer stars than most projects in their category, but documented and maintained.",
  },
  weekly: { title: "This week's discoveries", description: "A short mix across feeds and categories." },
};
const PERIODS: Period[] = ["day", "week", "month"];
const PAGE_SIZE = 20;

type Props = PageProps<"/discover/[feed]">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { feed } = await props.params;
  return { title: FEEDS[feed as FeedName]?.title ?? "Discover" };
}

function str(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

export default async function FeedPageView(props: Props) {
  const { feed } = await props.params;
  if (!(feed in FEEDS)) notFound();
  const name = feed as FeedName;
  const raw = await props.searchParams;
  const params = {
    period: str(raw.period),
    category: str(raw.category),
    language: str(raw.language),
    page: str(raw.page),
  };
  const period: Period = PERIODS.includes(params.period as Period) ? (params.period as Period) : "week";
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  let data: FeedPage;
  try {
    data = await getFeed(name, {
      period,
      category: params.category,
      language: params.language,
      page,
      pageSize: PAGE_SIZE,
    });
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "This feed could not load.";
    return <RefreshError title="Feed couldn't load" message={message} />;
  }

  const base = `/discover/${name}`;
  return (
    <div className="space-y-5">
      <p className="text-sm">
        <Link href="/discover" className="text-muted hover:text-ink hover:underline">
          Discover
        </Link>
      </p>
      {name === "trending" && <PeriodTabs base={base} params={params} />}
      <FeedSection title={FEEDS[name].title} description={FEEDS[name].description} feed={name} data={data} />
      <Pagination params={{ ...params, page: undefined }} page={page} pageSize={PAGE_SIZE} total={data.total} basePath={base} />
    </div>
  );
}
