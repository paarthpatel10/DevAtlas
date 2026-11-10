import type { Metadata } from "next";

import { CategoryTabs, LanguageSelect, PeriodTabs } from "@/components/discover/discover-filters";
import { FeedSection } from "@/components/discover/feed-section";
import { RefreshError } from "@/components/states/refresh-error";
import { ApiError, getDiscoverCategories, getFacets, getFeed } from "@/lib/api";
import type { Period } from "@/lib/types";

export const metadata: Metadata = { title: "Discover" };

const PERIODS: Period[] = ["day", "week", "month", "all"];
const PERIOD_TEXT: Record<Period, string> = {
  day: "today",
  week: "this week",
  month: "this month",
  all: "of all time",
};

function str(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

export default async function DiscoverPage(props: PageProps<"/discover">) {
  const raw = await props.searchParams;
  const params = { period: str(raw.period), category: str(raw.category), language: str(raw.language) };
  const period: Period = PERIODS.includes(params.period as Period) ? (params.period as Period) : "week";
  const filters = { category: params.category, language: params.language, pageSize: 6 };

  let data;
  try {
    const [trending, rising, fresh, gems, weekly, categories, facets] = await Promise.all([
      getFeed("trending", { ...filters, period }),
      getFeed("rising", filters),
      getFeed("new", filters),
      getFeed("hidden-gems", filters),
      getFeed("weekly", filters),
      getDiscoverCategories(params.language),
      getFacets(),
    ]);
    data = { trending, rising, fresh, gems, weekly, categories, facets };
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "The discovery feeds could not load.";
    return <RefreshError title="Discover couldn't load" message={message} />;
  }
  const seeAll = (feed: string) => {
    const search = new URLSearchParams();
    if (feed === "trending" && period !== "week") search.set("period", period);
    if (params.category) search.set("category", params.category);
    if (params.language) search.set("language", params.language);
    const text = search.toString();
    return `/discover/${feed}${text ? `?${text}` : ""}`;
  };

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Discover</h1>
        <p className="max-w-2xl text-sm text-muted">
          Projects worth your attention: what&apos;s gaining stars, what&apos;s new, and capable
          tools that are still little known. Every placement shows the numbers behind it.
          Popularity is not a measure of quality.
        </p>
      </div>
      <div className="space-y-3">
        <CategoryTabs base="/discover" params={params} categories={data.categories} />
        <LanguageSelect
          base="/discover"
          params={params}
          languages={data.facets.languages.map((l) => l.value)}
        />
      </div>

      <div className="space-y-3">
        <PeriodTabs base="/discover" params={params} />
        <FeedSection
          title={`Trending ${PERIOD_TEXT[period]}`}
          description="Repositories gaining the most stars in the period."
          feed="trending"
          data={data.trending}
          seeAllHref={seeAll("trending")}
        />
      </div>
      <FeedSection
        title="Rising"
        description="Sustained growth relative to size, with steady development activity."
        feed="rising"
        data={data.rising}
        seeAllHref={seeAll("rising")}
      />
      <FeedSection
        title="New and recently discovered"
        description="Created recently, newly found by search, or just shipped a first release."
        feed="new"
        data={data.fresh}
        seeAllHref={seeAll("new")}
      />
      <FeedSection
        title="Hidden gems"
        description="Fewer stars than most projects in their category, but documented, licensed and maintained."
        feed="hidden-gems"
        data={data.gems}
        seeAllHref={seeAll("hidden-gems")}
      />
      <FeedSection
        title="This week's discoveries"
        description="A short mix from the feeds above, across categories."
        feed="weekly"
        data={data.weekly}
        seeAllHref={seeAll("weekly")}
      />
    </div>
  );
}
