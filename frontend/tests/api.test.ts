import { afterEach, expect, test, vi } from "vitest";

import { ApiError, apiFetch, listRepositories, recommend } from "@/lib/api";

function mockFetch(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

test("maps the backend error schema to ApiError", async () => {
  mockFetch(async () =>
    Response.json(
      { error: { code: "not_found", message: "Repository a/b not found", details: null } },
      { status: 404 },
    ),
  );
  await expect(apiFetch("/repositories/a/b")).rejects.toMatchObject({
    name: "ApiError",
    status: 404,
    code: "not_found",
    message: "Repository a/b not found",
  });
});

test("non-JSON error responses become http_error", async () => {
  mockFetch(async () => new Response("Bad gateway", { status: 502 }));
  const error = (await apiFetch("/x").catch((e: unknown) => e)) as ApiError;
  expect(error).toBeInstanceOf(ApiError);
  expect(error.code).toBe("http_error");
  expect(error.status).toBe(502);
});

test("network failure becomes network_error", async () => {
  mockFetch(async () => {
    throw new TypeError("fetch failed");
  });
  const error = (await apiFetch("/x").catch((e: unknown) => e)) as ApiError;
  expect(error).toMatchObject({ status: 0, code: "network_error" });
  expect(error.message).toMatch(/cannot reach the api/i);
});

test("listRepositories builds a query string and omits empty params", async () => {
  const fetchFn = mockFetch(async () =>
    Response.json({ items: [], page: 1, page_size: 20, total: 0 }),
  );
  await listRepositories({ q: "queue", category: "", pageSize: 20, language: undefined });
  const url = new URL(fetchFn.mock.calls[0][0] as string);
  expect(url.pathname).toBe("/api/v1/repositories");
  expect(Object.fromEntries(url.searchParams)).toEqual({ q: "queue", page_size: "20" });
});

test("recommend posts JSON", async () => {
  const fetchFn = mockFetch(async () => Response.json({ results: [] }));
  await recommend({ query: "task queue", max_results: 3 });
  const [, init] = fetchFn.mock.calls[0];
  expect(init?.method).toBe("POST");
  expect(JSON.parse(init?.body as string)).toEqual({ query: "task queue", max_results: 3 });
  expect(new Headers(init?.headers).get("content-type")).toBe("application/json");
});
