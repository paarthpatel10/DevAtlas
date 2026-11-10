import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { SaveButton } from "@/components/repository/save-button";
import { ApiError, saveRepository, unsaveRepository } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  saveRepository: vi.fn(),
  unsaveRepository: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

test("saves and reports the new state", async () => {
  vi.mocked(saveRepository).mockResolvedValueOnce({ saved: true });
  const onChange = vi.fn();
  render(<SaveButton owner="acme" name="jobs" initialSaved={false} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("button", { name: "Saved" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(saveRepository).toHaveBeenCalledWith("acme", "jobs");
  expect(onChange).toHaveBeenCalledWith(true);
});

test("unsaves a saved repository", async () => {
  vi.mocked(unsaveRepository).mockResolvedValueOnce({ saved: false });
  render(<SaveButton owner="acme" name="jobs" initialSaved />);
  await userEvent.click(screen.getByRole("button", { name: "Saved" }));
  expect(await screen.findByRole("button", { name: "Save" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  expect(unsaveRepository).toHaveBeenCalledWith("acme", "jobs");
});

test("is optimistic and rolls back on failure", async () => {
  vi.mocked(saveRepository).mockRejectedValueOnce(
    new ApiError(503, "database_unavailable", "down"),
  );
  render(<SaveButton owner="acme" name="jobs" initialSaved={false} />);
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText(/couldn't save/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("aria-pressed", "false");
});
