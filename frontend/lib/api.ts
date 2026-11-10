import type {
  ApiErrorBody,
  AskOut,
  BuildIdeasOut,
  CategorySummary,
  CompareOut,
  FeedName,
  FeedPage,
  InsightsOut,
  Period,
  Facets,
  Health,
  Page,
  RecommendResponse,
  RepositoryDetail,
  RepositorySummary,
} from "@/lib/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  override name = "ApiError";

  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: unknown = null,
  ) {
    super(message);
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ApiErrorBody).error?.code === "string"
  );
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the API. Is the backend running?");
  }
  if (response.ok) {
    return (await response.json()) as T;
  }
  const body: unknown = await response.json().catch(() => null);
  if (isErrorBody(body)) {
    throw new ApiError(response.status, body.error.code, body.error.message, body.error.details);
  }
  throw new ApiError(response.status, "http_error", `Request failed (HTTP ${response.status}).`);
}

function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export type RepositoryListParams = {
  q?: string;
  category?: string;
  language?: string;
  license?: string;
  sort?: string;
  page?: number;
  pageSize?: number;
};

export const getHealth = () => apiFetch<Health>("/health");

export const listRepositories = (p: RepositoryListParams = {}) =>
  apiFetch<Page<RepositorySummary>>(
    `/repositories${query({
      q: p.q,
      category: p.category,
      language: p.language,
      license: p.license,
      sort: p.sort,
      page: p.page,
      page_size: p.pageSize,
    })}`,
  );

export const getFacets = () => apiFetch<Facets>("/repositories/facets");

const repoPath = (owner: string, name: string) =>
  `/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`;

export const getRepository = (owner: string, name: string) =>
  apiFetch<RepositoryDetail>(repoPath(owner, name));

export const saveRepository = (owner: string, name: string) =>
  apiFetch<{ saved: boolean }>(`${repoPath(owner, name)}/save`, { method: "POST" });

export const unsaveRepository = (owner: string, name: string) =>
  apiFetch<{ saved: boolean }>(`${repoPath(owner, name)}/save`, { method: "DELETE" });

export const listSaved = (page = 1) =>
  apiFetch<Page<RepositorySummary>>(`/me/saved${query({ page })}`);

export const recommend = (body: { query: string; max_results?: number }) =>
  apiFetch<RecommendResponse>("/assistant/recommend", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

export const getFeed = (
  feed: FeedName,
  p: { period?: Period; category?: string; language?: string; page?: number; pageSize?: number } = {},
) =>
  apiFetch<FeedPage>(
    `/discover/${feed}${query({
      period: feed === "trending" ? p.period : undefined,
      category: p.category,
      language: p.language,
      page: p.page,
      page_size: p.pageSize,
    })}`,
  );

export const getDiscoverCategories = (language?: string) =>
  apiFetch<CategorySummary[]>(`/discover/categories${query({ language })}`);

export const getInsights = (owner: string, name: string) =>
  apiFetch<InsightsOut>(`${repoPath(owner, name)}/insights`);

const postJson = <T,>(path: string, body: unknown) =>
  apiFetch<T>(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

export const getBuildIdeas = (owner: string, name: string, more = false) =>
  postJson<BuildIdeasOut>(`${repoPath(owner, name)}/build-ideas`, { more });

export const askRepository = (owner: string, name: string, question: string) =>
  postJson<AskOut>(`${repoPath(owner, name)}/ask`, { question });

export const compareRepositories = (repositories: string[]) =>
  postJson<CompareOut>("/repositories/compare", { repositories });
