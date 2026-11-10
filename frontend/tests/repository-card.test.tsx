import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { RepositoryCard } from "@/components/repository/repository-card";
import { card } from "./fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

test("card shows Not available for missing metrics and a license fallback", () => {
  render(
    <RepositoryCard
      repo={{ ...card, stars: null, forks: null, license_spdx: null, license_name: null }}
    />,
  );
  expect(screen.getAllByText("Not available").length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText("License not detected")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /github/i })).toHaveAttribute("href", card.html_url);
  expect(screen.getByRole("link", { name: card.full_name })).toHaveAttribute(
    "href",
    "/repositories/acme/jobs",
  );
});

test("card shows verified metadata and at most four topics", () => {
  render(<RepositoryCard repo={card} />);
  expect(screen.getByText("1.2k")).toBeInTheDocument();
  expect(screen.getByText("MIT")).toBeInTheDocument();
  expect(screen.getByText("Python")).toBeInTheDocument();
  expect(screen.getByText("task-queue")).toBeInTheDocument();
  expect(screen.queryByText("extra-topic")).not.toBeInTheDocument();
});

test("unrecognised license shows GitHub's label, not a guess", () => {
  render(<RepositoryCard repo={{ ...card, license_spdx: null, license_name: "Other" }} />);
  expect(screen.getByText("Other (unverified)")).toBeInTheDocument();
});

test("README-derived text is rendered as plain text", () => {
  const description = "<img src=x onerror=alert(1)>";
  const { container } = render(<RepositoryCard repo={{ ...card, description }} />);
  expect(screen.getByText(description)).toBeInTheDocument();
  expect(container.querySelector("img")).toBeNull();
});
