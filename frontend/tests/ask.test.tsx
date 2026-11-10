import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { AskView } from "@/components/assistant/ask-view";
import { ApiError, recommend } from "@/lib/api";
import type { RecommendResponse } from "@/lib/types";
import { card } from "./fixtures";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  recommend: vi.fn(),
}));

const response: RecommendResponse = {
  query: "task queue with retries for FastAPI",
  intent: {
    goal: "task queue with retries for FastAPI",
    requirements: ["background jobs", "retries"],
    constraints: [],
    known_stack: { backend: ["FastAPI"] },
    category: "backend",
    preferred_license: null,
    keywords: [],
    inferred: ["Category 'Backend' inferred from: background jobs, retries"],
    clarifying_question: null,
  },
  results: [
    {
      rank: 1,
      repository: card,
      reasons: ["Mentioned in source: background jobs, retries", "Curated category: Backend"],
      requirements: [
        {
          requirement: "retries",
          status: "evidenced",
          evidence: [
            {
              snippet: "Automatic retries with exponential backoff for failed jobs",
              source_url: "https://github.com/acme/jobs/blob/main/README.md",
              section_title: "Features",
              source_type: "readme",
            },
          ],
        },
        { requirement: "scheduling", status: "not_established", evidence: [] },
      ],
      compatibility: [
        {
          stack_item: "FastAPI",
          status: "inferred",
          note: "Same primary language (Python); integration not confirmed by source.",
          evidence: null,
        },
      ],
      limitations: ["Not established from source: scheduling"],
      signals: {
        keyword_rank: 2,
        semantic_rank: 1,
        rrf_score: 0.03252,
        requirements_evidenced: 1,
        requirements_total: 2,
      },
    },
  ],
  pipeline: {
    provider: "mock",
    embedding_model: "mock-hashing-v1",
    rrf_k: 60,
    keyword_candidates: 5,
    semantic_candidates: 50,
    notes: ["Demo mode: lexical (hashed) embeddings and extractive analysis; no LLM involved."],
  },
  clarifying_question: null,
};

beforeEach(() => vi.clearAllMocks());

const textbox = () => screen.getByLabelText(/describe what you're trying to build/i);

test("submits on Enter and renders evidence-backed results", async () => {
  vi.mocked(recommend).mockResolvedValue(response);
  render(<AskView />);
  await userEvent.type(textbox(), "task queue with retries for FastAPI{Enter}");
  expect(recommend).toHaveBeenCalledWith({ query: "task queue with retries for FastAPI" });

  const result = await screen.findByRole("article", { name: /acme\/jobs/ });
  const r = within(result);
  expect(r.getByRole("link", { name: "acme/jobs" })).toHaveAttribute("href", "/repositories/acme/jobs");
  expect(r.getByText("Mentioned in source")).toBeInTheDocument();
  expect(r.getByText("Not established")).toBeInTheDocument();
  expect(r.getByText("Automatic retries with exponential backoff for failed jobs")).toBeInTheDocument();
  expect(r.getByText("Inferred")).toBeInTheDocument();
  expect(r.getByText(/keyword rank 2/i)).toBeInTheDocument();
  expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  expect(screen.getByText(/inferred: category 'backend'/i)).toBeInTheDocument();
  expect(screen.getByText(/demo mode/i)).toBeInTheDocument();
});

test("rejects too-short input without calling the API", async () => {
  render(<AskView />);
  await userEvent.type(textbox(), "hi{Enter}");
  expect(screen.getByText(/at least 3 characters/i)).toBeInTheDocument();
  expect(recommend).not.toHaveBeenCalled();
});

test("Shift+Enter adds a newline instead of submitting", async () => {
  render(<AskView />);
  await userEvent.type(textbox(), "line one{Shift>}{Enter}{/Shift}line two");
  expect(textbox()).toHaveValue("line one\nline two");
  expect(recommend).not.toHaveBeenCalled();
});

test("example prompts fill the box and submit", async () => {
  vi.mocked(recommend).mockResolvedValue({ ...response, results: [] });
  render(<AskView />);
  const example = screen.getAllByRole("button", { name: /fastapi application/i })[0];
  await userEvent.click(example);
  expect(recommend).toHaveBeenCalledTimes(1);
  expect(textbox()).toHaveValue(vi.mocked(recommend).mock.calls[0][0].query);
});

test("shows the clarifying question", async () => {
  vi.mocked(recommend).mockResolvedValue({
    ...response,
    results: [],
    clarifying_question: "What are you building, and what should the tool do?",
  });
  render(<AskView />);
  await userEvent.type(textbox(), "help me{Enter}");
  expect(await screen.findByText(/what are you building/i)).toBeInTheDocument();
});

test("shows a retryable error on API failure", async () => {
  vi.mocked(recommend)
    .mockRejectedValueOnce(new ApiError(503, "database_unavailable", "The database is unavailable."))
    .mockResolvedValueOnce(response);
  render(<AskView />);
  await userEvent.type(textbox(), "task queue with retries{Enter}");
  expect(await screen.findByRole("alert")).toHaveTextContent(/database is unavailable/i);
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("article", { name: /acme\/jobs/ })).toBeInTheDocument();
  expect(recommend).toHaveBeenCalledTimes(2);
});

test("empty results show guidance from the pipeline", async () => {
  vi.mocked(recommend).mockResolvedValue({
    ...response,
    results: [],
    pipeline: { ...response.pipeline, notes: ["No repositories matched with supporting evidence."] },
  });
  render(<AskView />);
  await userEvent.type(textbox(), "qwzxv plorf{Enter}");
  expect(await screen.findByText(/no repositories matched/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /browse explore/i })).toHaveAttribute("href", "/explore");
});

test("initial query from the URL runs once", async () => {
  vi.mocked(recommend).mockResolvedValue(response);
  render(<AskView initialQuery="Alternatives to celery/celery" />);
  expect(await screen.findByRole("article", { name: /acme\/jobs/ })).toBeInTheDocument();
  expect(recommend).toHaveBeenCalledTimes(1);
  expect(textbox()).toHaveValue("Alternatives to celery/celery");
});
