// Mirrors of the backend API schemas (backend/app/schemas). Unknown values are null.

export type Page<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

/** Mirrors backend `RepositoryCard` (renamed so it doesn't clash with the component). */
export type RepositorySummary = {
  id: string;
  owner: string;
  name: string;
  full_name: string;
  description: string | null;
  html_url: string;
  primary_language: string | null;
  topics: string[];
  license_spdx: string | null;
  license_name: string | null;
  stars: number | null;
  forks: number | null;
  pushed_at_github: string | null;
  archived: boolean;
  category: string;
  category_label: string;
  featured: boolean;
  data_source: string;
  source_fetched_at: string;
  is_saved: boolean;
};

export type Capability = {
  name: string;
  description: string;
  evidence: string[];
  confidence: "high" | "medium" | "low";
};

export type AnalysisView = {
  summary: string | null;
  problem_solved: string | null;
  category: string | null;
  subcategory: string | null;
  capabilities: Capability[];
  use_cases: string[];
  supported_languages: string[];
  integrations: string[];
  requirements: string[];
  limitations: string[];
  maturity: "unknown" | "experimental" | "active" | "mature" | "inactive";
  target_users: string[];
  keywords: string[];
  analysis_version: string;
  model_name: string;
  prompt_version: string;
  generated_by_label: string;
};

export type Signal = { label: string; value: string; explanation: string };
export type SourceRef = { label: string; url: string };

export type RepositoryDetail = RepositorySummary & {
  homepage_url: string | null;
  readme_url: string | null;
  languages: Record<string, number>;
  open_issues: number | null;
  created_at_github: string | null;
  updated_at_github: string | null;
  default_branch: string | null;
  readme_truncated: boolean;
  analysis: AnalysisView | null;
  maintenance_signals: Signal[];
  sources: SourceRef[];
};

export type Facets = {
  categories: { value: string; label: string; count: number }[];
  languages: { value: string; count: number }[];
  licenses: { value: string; count: number }[];
};

export type Health = {
  status: "ok" | "degraded";
  app_env: string;
  ai_provider: string;
  demo_mode: boolean;
  database: "ok" | "unavailable" | "not_configured";
};

export type QueryIntent = {
  goal: string;
  requirements: string[];
  constraints: string[];
  known_stack: Record<string, string[]>;
  category: string | null;
  preferred_license: string | null;
  keywords: string[];
  inferred: string[];
  clarifying_question: string | null;
};

export type Evidence = {
  snippet: string;
  source_url: string | null;
  section_title: string | null;
  source_type: string;
};

export type RequirementCheck = {
  requirement: string;
  status: "evidenced" | "not_established";
  evidence: Evidence[];
};

export type CompatibilityNote = {
  stack_item: string;
  status: "evidenced" | "inferred" | "not_established";
  note: string;
  evidence: Evidence | null;
};

export type RetrievalSignals = {
  keyword_rank: number | null;
  semantic_rank: number | null;
  rrf_score: number;
  requirements_evidenced: number;
  requirements_total: number;
};

export type Recommendation = {
  rank: number;
  repository: RepositorySummary;
  reasons: string[];
  requirements: RequirementCheck[];
  compatibility: CompatibilityNote[];
  limitations: string[];
  signals: RetrievalSignals;
};

export type RecommendResponse = {
  query: string;
  intent: QueryIntent;
  results: Recommendation[];
  pipeline: {
    provider: string;
    embedding_model: string;
    rrf_k: number;
    keyword_candidates: number;
    semantic_candidates: number;
    notes: string[];
  };
  clarifying_question: string | null;
};

export type ApiErrorBody = {
  error: { code: string; message: string; details: unknown };
};

// ---- Discover ---------------------------------------------------------------------------

export type FeedName = "trending" | "rising" | "new" | "hidden-gems" | "weekly";
export type Period = "day" | "week" | "month" | "all";
export type FeedLabel = "trending" | "rising" | "new" | "hidden_gem";
export type FeedBasis = "growth" | "popularity_activity" | "insufficient_history" | "not_computed";

export type DiscoverItem = RepositorySummary & {
  labels: FeedLabel[];
  signals: Record<string, unknown>;
  signal_text: string[];
  one_liner: string | null;
  why_explore: string | null;
};

export type FeedPage = {
  items: DiscoverItem[];
  page: number;
  page_size: number;
  total: number;
  feed: string;
  period: string | null;
  basis: FeedBasis;
  computed_at: string | null;
};

export type CategorySummary = { value: string; label: string; count: number; top: DiscoverItem[] };

// ---- Intelligence reports ---------------------------------------------------------------

export type Citation = {
  id: string;
  section_title: string | null;
  source_url: string | null;
  excerpt: string;
};
export type CitedText = { text: string; citations: Citation[] };
export type Idea = {
  title: string;
  description: string;
  how_it_is_used: string;
  complementary_tech: string[];
  citations: Citation[];
};
export type GroundedReport = {
  generated: boolean;
  what_is_it: { one_line: string; explanation: string; citations: Citation[] } | null;
  problem_solved: CitedText | null;
  why_interesting: { point: string; citations: Citation[] }[];
  who_should_care: { audience: string; reason: string; citations: Citation[] }[];
  use_cases: CitedText[];
  build_ideas: Idea[];
  technical: {
    frameworks: { name: string; citations: Citation[] }[];
    capabilities: { name: string; citations: Citation[] }[];
    integrations: { name: string; citations: Citation[] }[];
    prerequisites: CitedText[];
    architecture: CitedText | null;
  };
  limitations: CitedText[];
  getting_started: { label: string; url: string; citations: Citation[] }[];
};
export type InsightsOut = {
  report: GroundedReport;
  generated: boolean;
  model_name: string | null;
  generated_at: string | null;
  stale: boolean;
  labels: FeedLabel[];
  why_trending: string[];
  related: RepositorySummary[];
};
export type BuildIdeasOut = {
  ideas: Idea[];
  generated: boolean;
  model_name: string | null;
  cached: boolean;
};
export type AskOut = {
  covered: boolean;
  answer: string;
  citations: Citation[];
  model_name: string | null;
  cached: boolean;
};
export type CompareOut = {
  dimensions: string[];
  rows: { repository: RepositorySummary; values: Record<string, string | null>; fits_when: string[] }[];
};
