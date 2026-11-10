import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { DiscoverCard } from "@/components/discover/discover-card";
import { PeriodTabs } from "@/components/discover/discover-filters";
import { FeedSection } from "@/components/discover/feed-section";
import { ApiError, getBuildIdeas, getInsights } from "@/lib/api";
import { clearCompare, getCompareList, toggleCompare } from "@/lib/compare-store";
import type { DiscoverItem, FeedPage, InsightsOut } from "@/lib/types";
import { card } from "./fixtures";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getInsights: vi.fn(),
  getBuildIdeas: vi.fn(),
  saveRepository: vi.fn(),
  unsaveRepository: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  clearCompare();
});

const item: DiscoverItem = {
  ...card,
  labels: ["trending", "hidden_gem"],
  signals: { stars_gained: 100 },
  signal_text: ["+100 stars in 7 days", "Commits in 4 of the last 4 weeks"],
  one_liner: "A background job queue for Python apps.",
  why_explore: "Simple API with built-in retries.",
};

const citation = {
  id: "C2",
  section_title: "Features",
  source_url: "https://github.com/acme/jobs/blob/main/README.md",
  excerpt: "Automatic retries with exponential backoff for failed jobs",
};

const insights: InsightsOut = {
  report: {
    generated: true,
    what_is_it: { one_line: "A job queue.", explanation: "Runs jobs.", citations: [citation] },
    problem_solved: null,
    why_interesting: [{ point: "Retries with exponential backoff.", citations: [citation] }],
    who_should_care: [],
    use_cases: [],
    build_ideas: [
      {
        title: "Notification worker",
        description: "Send emails in the background.",
        how_it_is_used: "Enqueue jobs that retry.",
        complementary_tech: ["Redis"],
        citations: [citation],
      },
    ],
    technical: { frameworks: [], capabilities: [], integrations: [], prerequisites: [], architecture: null },
    limitations: [],
    getting_started: [],
  },
  generated: true,
  model_name: "gemini:gemini-3.5-flash-lite",
  generated_at: "2026-11-10T09:00:00Z",
  stale: false,
  labels: ["trending"],
  why_trending: ["Trending this week: +100 stars in 7 days"],
  related: [],
};

test("card shows labels as text, signals, AI summary and actions", () => {
  render(<DiscoverCard item={item} />);
  expect(screen.getByText("Trending")).toBeInTheDocument();
  expect(screen.getByText("Hidden gem")).toBeInTheDocument();
  expect(screen.getByText("+100 stars in 7 days")).toBeInTheDocument();
  expect(screen.getByText("A background job queue for Python apps.")).toBeInTheDocument();
  expect(screen.getByText(/AI summary/i)).toBeInTheDocument();
  expect(screen.getByText(/why explore this\? \(AI\)/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /explore/i })).toHaveAttribute("href", "/repositories/acme/jobs");
  expect(screen.getByRole("button", { name: /why is this interesting/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /what can i build/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /compare/i })).toBeInTheDocument();
});

test("card without signals shows no growth claims", () => {
  render(<DiscoverCard item={{ ...item, signal_text: [], labels: [], one_liner: null }} />);
  expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();
  expect(screen.queryByText(/AI summary/i)).not.toBeInTheDocument();
  expect(screen.getByText(card.description!)).toBeInTheDocument();
});

test("why panel loads measured reasons and cited points", async () => {
  vi.mocked(getInsights).mockResolvedValue(insights);
  render(<DiscoverCard item={item} />);
  await userEvent.click(screen.getByRole("button", { name: /why is this interesting/i }));
  expect(await screen.findByText("Trending this week: +100 stars in 7 days")).toBeInTheDocument();
  expect(screen.getByText("Retries with exponential backoff.")).toBeInTheDocument();
  expect(screen.getByText(/AI-generated with gemini-3.5-flash-lite/i)).toBeInTheDocument();
  await userEvent.click(screen.getByText(/sources/i));
  expect(screen.getByText(/Automatic retries with exponential backoff/)).toBeInTheDocument();
});

test("ideas panel shows stored ideas and explains AI errors", async () => {
  vi.mocked(getBuildIdeas)
    .mockResolvedValueOnce({ ideas: insights.report.build_ideas, generated: true, model_name: "m", cached: true })
    .mockRejectedValueOnce(new ApiError(429, "rate_limited", "Too many"))
    .mockRejectedValueOnce(new ApiError(503, "ai_unavailable", "AI features need an AI provider."));
  render(<DiscoverCard item={item} />);
  await userEvent.click(screen.getByRole("button", { name: /what can i build/i }));
  expect(await screen.findByText("Notification worker")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /generate more ideas/i }));
  expect(await screen.findByText(/too many ai requests/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /generate more ideas/i }));
  expect(await screen.findByText(/needs an AI provider/i)).toBeInTheDocument();
});

test("compare store keeps at most four and persists", () => {
  ["a/1", "a/2", "a/3", "a/4"].forEach((n) => toggleCompare(n));
  expect(getCompareList()).toEqual(["a/1", "a/2", "a/3", "a/4"]);
  expect(() => toggleCompare("a/5")).toThrow(/four/i);
  toggleCompare("a/2");
  expect(getCompareList()).toEqual(["a/1", "a/3", "a/4"]);
  expect(JSON.parse(localStorage.getItem("devatlas.compare")!)).toEqual(["a/1", "a/3", "a/4"]);
});

test("compare button toggles membership", async () => {
  render(<DiscoverCard item={item} />);
  await userEvent.click(screen.getByRole("button", { name: /compare/i }));
  expect(getCompareList()).toEqual(["acme/jobs"]);
  expect(screen.getByRole("button", { name: /compare/i })).toHaveAttribute("aria-pressed", "true");
});

function page(basis: FeedPage["basis"], items: DiscoverItem[] = [item]): FeedPage {
  return { items, page: 1, page_size: 6, total: items.length, feed: "trending", period: "week",
           basis, computed_at: "2026-11-10T09:00:00Z", note: null };
}

test("feed section credits GitHub Trending and shows the observation note", () => {
  render(
    <FeedSection
      title="Trending this week"
      feed="trending"
      data={{ ...page("github_trending"), note: "Based on 1 day of GitHub Trending observations so far." }}
    />,
  );
  expect(screen.getByText(/from github trending/i)).toBeInTheDocument();
  expect(screen.getByText(/based on 1 day of github trending observations/i)).toBeInTheDocument();
});

test("period tabs offer today, this week and this month only", () => {
  render(<PeriodTabs base="/discover" params={{}} />);
  expect(screen.getByRole("link", { name: "Today" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "This month" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /all time/i })).not.toBeInTheDocument();
});

test("feed section explains insufficient history and not computed", () => {
  const { rerender } = render(
    <FeedSection title="Rising" feed="rising" data={page("insufficient_history", [])} />,
  );
  expect(screen.getByText(/not enough history yet/i)).toBeInTheDocument();
  rerender(
    <FeedSection
      title="Rising"
      feed="rising"
      data={{ ...page("insufficient_history", []), note: "Rising needs GitHub Trending observations on at least 2 days (1 day so far)." }}
    />,
  );
  expect(screen.getByText(/1 day so far/i)).toBeInTheDocument();
  rerender(<FeedSection title="Rising" feed="rising" data={{ ...page("not_computed", []), computed_at: null }} />);
  expect(screen.getByText(/hasn't been computed yet/i)).toBeInTheDocument();
});
