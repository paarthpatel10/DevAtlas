import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { SavedList } from "@/components/repository/saved-list";
import { unsaveRepository } from "@/lib/api";
import { card } from "./fixtures";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  unsaveRepository: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

const second = { ...card, id: "id-2", name: "ui", full_name: "acme/ui", is_saved: true };

test("lists saved repositories and removes one after unsaving", async () => {
  vi.mocked(unsaveRepository).mockResolvedValueOnce({ saved: false });
  render(<SavedList initial={[{ ...card, is_saved: true }, second]} />);
  expect(screen.getByRole("link", { name: "acme/jobs" })).toBeInTheDocument();
  await userEvent.click(screen.getAllByRole("button", { name: "Saved" })[0]);
  expect(await screen.findByRole("link", { name: "acme/ui" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "acme/jobs" })).not.toBeInTheDocument();
});

test("empty state links to Explore and Ask AI", () => {
  render(<SavedList initial={[]} />);
  expect(screen.getByText(/nothing saved yet/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /explore/i })).toHaveAttribute("href", "/explore");
  expect(screen.getByRole("link", { name: /ask ai/i })).toHaveAttribute("href", "/ask");
});

test("unsaving the last item shows the empty state", async () => {
  vi.mocked(unsaveRepository).mockResolvedValueOnce({ saved: false });
  render(<SavedList initial={[{ ...card, is_saved: true }]} />);
  await userEvent.click(screen.getByRole("button", { name: "Saved" }));
  expect(await screen.findByText(/nothing saved yet/i)).toBeInTheDocument();
});
