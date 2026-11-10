import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { AskPanel } from "@/components/insights/ask-panel";
import { ReportSections } from "@/components/insights/report-sections";
import { ApiError, askRepository } from "@/lib/api";
import type { AskOut, InsightsOut } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  askRepository: vi.fn(),
  getBuildIdeas: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

const cite = {
  id: "C2",
  section_title: "Features",
  source_url: "https://github.com/acme/jobs/blob/main/README.md",
  excerpt: "Automatic retries with exponential backoff",
};

const insights: InsightsOut = {
  report: {
    generated: true,
    what_is_it: { one_line: "A job queue.", explanation: "Runs work outside web requests.", citations: [cite] },
    problem_solved: { text: "Slow work blocking requests.", citations: [cite] },
    why_interesting: [{ point: "Retries with backoff.", citations: [cite] }],
    who_should_care: [{ audience: "Backend developers", reason: "Reliable jobs.", citations: [cite] }],
    use_cases: [],
    build_ideas: [
      { title: "Notification worker", description: "Emails.", how_it_is_used: "Retries.",
        complementary_tech: [], citations: [cite] },
    ],
    technical: { frameworks: [], capabilities: [{ name: "Retries", citations: [cite] }], integrations: [],
                 prerequisites: [], architecture: null },
    limitations: [],
    getting_started: [],
  },
  generated: true,
  model_name: "gemini:gemini-3.5-flash-lite",
  generated_at: "2026-11-10T09:00:00Z",
  stale: false,
  labels: [],
  why_trending: ["Commits in 4 of the last 4 weeks"],
  related: [],
};

test("report renders sections with citations and labels empty ones", async () => {
  render(<ReportSections insights={insights} readmeUrl={cite.source_url} />);
  expect(screen.getByText("Runs work outside web requests.")).toBeInTheDocument();
  expect(screen.getByText("Slow work blocking requests.")).toBeInTheDocument();
  expect(screen.getByText("Commits in 4 of the last 4 weeks")).toBeInTheDocument();
  expect(screen.getByText("Notification worker")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Practical use cases" })).toBeInTheDocument();
  expect(screen.getAllByText(/not established/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/AI-generated with gemini-3.5-flash-lite on 10 Nov 2026/)).toBeInTheDocument();
  await userEvent.click(screen.getAllByText(/sources/i)[0]);
  expect(screen.getAllByText("Automatic retries with exponential backoff")[0]).toBeVisible();
});

test("extractive and stale reports are labelled honestly", () => {
  const extractive = { ...insights, generated: false, model_name: null, generated_at: null,
    report: { ...insights.report, generated: false, why_interesting: [], build_ideas: [] } };
  const { rerender } = render(<ReportSections insights={extractive} readmeUrl={null} />);
  expect(screen.getByText(/no AI report yet/i)).toBeInTheDocument();
  rerender(<ReportSections insights={{ ...insights, stale: true }} readmeUrl={null} />);
  expect(screen.getByText(/README has changed since this report/i)).toBeInTheDocument();
});

const answer: AskOut = {
  covered: true,
  answer: "Yes: failed jobs are retried with backoff.",
  citations: [cite],
  model_name: "gemini:x",
  cached: false,
};

test("suggested question submits and shows a cited answer", async () => {
  vi.mocked(askRepository).mockResolvedValue(answer);
  render(<AskPanel owner="acme" name="jobs" />);
  await userEvent.click(screen.getByRole("button", { name: /explain this repository in simple terms/i }));
  expect(askRepository).toHaveBeenCalledWith("acme", "jobs", "Explain this repository in simple terms.");
  expect(await screen.findByText(answer.answer)).toBeInTheDocument();
  expect(screen.getByText(/sources \(1\)/i)).toBeInTheDocument();
});

test("uncovered questions and rate limits are explained", async () => {
  vi.mocked(askRepository)
    .mockResolvedValueOnce({ ...answer, covered: false, answer: "The repository's documentation doesn't cover this.", citations: [] })
    .mockRejectedValueOnce(new ApiError(429, "rate_limited", "Too many"));
  render(<AskPanel owner="acme" name="jobs" />);
  const input = screen.getByLabelText(/ask about this repository/i);
  await userEvent.type(input, "Which pizza is best?{Enter}");
  expect(await screen.findByText(/doesn't cover this/i)).toBeInTheDocument();
  await userEvent.clear(input);
  await userEvent.type(input, "Is it production ready?{Enter}");
  expect(await screen.findByText(/too many ai requests/i)).toBeInTheDocument();
});

test("short questions are rejected without a request", async () => {
  render(<AskPanel owner="acme" name="jobs" />);
  await userEvent.type(screen.getByLabelText(/ask about this repository/i), "hi{Enter}");
  expect(screen.getByText(/at least 3 characters/i)).toBeInTheDocument();
  expect(askRepository).not.toHaveBeenCalled();
});

test("a slow earlier answer never replaces the newer one", async () => {
  let resolveFirst!: (v: AskOut) => void;
  vi.mocked(askRepository)
    .mockImplementationOnce(() => new Promise((r) => (resolveFirst = r)))
    .mockResolvedValueOnce(answer);
  render(<AskPanel owner="acme" name="jobs" />);
  await userEvent.type(screen.getByLabelText(/ask about this repository/i), "first question{Enter}");
  // While loading, the Ask button is disabled, but suggested questions can still be clicked.
  await userEvent.click(screen.getByRole("button", { name: /how does it work internally/i }));
  expect(await screen.findByText(answer.answer)).toBeInTheDocument();
  resolveFirst({ ...answer, answer: "stale answer" });
  await new Promise((r) => setTimeout(r, 0));
  expect(screen.queryByText("stale answer")).not.toBeInTheDocument();
});
