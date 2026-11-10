import { expect, test } from "vitest";

import { formatCount, formatDate, snapshotLabel } from "@/lib/format";

test("formatCount never invents values", () => {
  expect(formatCount(null)).toBe("Not available");
  expect(formatCount(undefined)).toBe("Not available");
  expect(formatCount(0)).toBe("0");
  expect(formatCount(999)).toBe("999");
  expect(formatCount(1234)).toBe("1.2k");
  expect(formatCount(29166)).toBe("29.2k");
  expect(formatCount(1_250_000)).toBe("1.3M");
});

test("formatDate uses UTC day-month-year and handles missing values", () => {
  expect(formatDate(null)).toBe("Not available");
  expect(formatDate("2026-03-12T23:30:00Z")).toBe("12 Mar 2026");
});

test("snapshotLabel distinguishes snapshot from live data", () => {
  expect(snapshotLabel("seed_snapshot", "2026-11-10T09:00:00Z")).toBe("Snapshot · 10 Nov 2026");
  expect(snapshotLabel("github_live", "2026-11-10T09:00:00Z")).toBe("Live · 10 Nov 2026");
});
