import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { CompareView } from "@/components/compare/compare-view";
import { compareRepositories } from "@/lib/api";
import { clearCompare, getCompareList, toggleCompare } from "@/lib/compare-store";
import type { CompareOut } from "@/lib/types";
import { card } from "./fixtures";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  compareRepositories: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  clearCompare();
});

const result: CompareOut = {
  dimensions: ["Primary purpose", "License", "Integrations"],
  rows: [
    {
      repository: card,
      values: { "Primary purpose": "A job queue.", License: "MIT", Integrations: null },
      fits_when: ["Backend developers: reliable jobs"],
    },
    {
      repository: { ...card, id: "2", name: "searchy", full_name: "acme/searchy" },
      values: { "Primary purpose": "A search engine.", License: "Apache-2.0", Integrations: "REST API" },
      fits_when: [],
    },
  ],
};

test("fewer than two repositories shows guidance", () => {
  toggleCompare("acme/jobs");
  render(<CompareView />);
  expect(screen.getByText(/add at least two repositories/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /discover/i })).toHaveAttribute("href", "/discover");
  expect(compareRepositories).not.toHaveBeenCalled();
});

test("renders dimensions, missing values and no winner", async () => {
  toggleCompare("acme/jobs");
  toggleCompare("acme/searchy");
  vi.mocked(compareRepositories).mockResolvedValue(result);
  render(<CompareView />);
  expect(await screen.findAllByText("A job queue.")).not.toHaveLength(0);
  expect(compareRepositories).toHaveBeenCalledWith(["acme/jobs", "acme/searchy"]);
  expect(screen.getAllByText("Not established").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Backend developers: reliable jobs").length).toBeGreaterThan(0);
  expect(screen.getByText(/no overall winner/i)).toBeInTheDocument();
});

test("remove takes a repository out of the comparison", async () => {
  toggleCompare("acme/jobs");
  toggleCompare("acme/searchy");
  vi.mocked(compareRepositories).mockResolvedValue(result);
  render(<CompareView />);
  await screen.findAllByText("A job queue.");
  await userEvent.click(screen.getAllByRole("button", { name: /remove acme\/searchy/i })[0]);
  expect(getCompareList()).toEqual(["acme/jobs"]);
  expect(await screen.findByText(/add at least two repositories/i)).toBeInTheDocument();
});
