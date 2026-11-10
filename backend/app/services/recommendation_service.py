"""Evidence-backed recommendation pipeline (spec 6.5).

Understand -> Expand -> Retrieve (keyword + semantic) -> Merge (RRF) -> Rerank by evidenced
requirement coverage -> Verify stack compatibility against stored text -> Explain.
Popularity (stars) is never used for ranking. Explanations are templated from facts.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.mock_providers import tokenize
from app.ai.provider import Providers
from app.ai.query_understanding import understand_query
from app.ai.vocabulary import Vocabulary
from app.config import Settings
from app.models import Repository
from app.schemas.recommendation import (
    CompatibilityNote,
    PipelineInfo,
    QueryIntent,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
    RequirementCheck,
    RetrievalSignals,
)
from app.services.evidence import find_evidence
from app.services.ranking import FusedHit, rrf_fuse
from app.services.repository_service import category_label, saved_ids, to_card
from app.services.search_service import SearchFilters, keyword_search, semantic_search

CANDIDATE_LIMIT = 50
FUSED_POOL = 30
STALE_AFTER = timedelta(days=365)

# Words that describe the request rather than the problem; kept out of keyword retrieval.
_FILLER = frozenset(
    "need needs looking find app apps application applications project projects build "
    "building built something thing things tool tools library libraries way help good best "
    "great simple easy make makes like recommend recommendation please".split()
)


def limitations_for(repo: Repository, uncovered: list[str]) -> list[str]:
    limitations: list[str] = []
    if repo.archived:
        limitations.append("Archived on GitHub (read-only)")
    if repo.license_spdx is None:
        if repo.license_name:
            limitations.append(
                f"License not identified by GitHub (listed as '{repo.license_name}'); "
                "check the repository's license file"
            )
        else:
            limitations.append("No license detected in GitHub metadata")
    limitations += [f"Not established from source: {req}" for req in uncovered]
    if repo.pushed_at_github and repo.source_fetched_at - repo.pushed_at_github > STALE_AFTER:
        limitations.append(
            f"No push in over 12 months as of snapshot {repo.source_fetched_at:%Y-%m-%d}"
        )
    return limitations


def _requirement_checks(
    repo: Repository, intent: QueryIntent, vocab: Vocabulary
) -> list[RequirementCheck]:
    checks: list[RequirementCheck] = []
    for requirement in intent.requirements:
        concept = vocab.capability_by_label(requirement)
        phrases = concept.evidence_phrases if concept else (requirement,)
        evidence = find_evidence(repo.chunks, phrases)
        checks.append(
            RequirementCheck(
                requirement=requirement,
                status="evidenced" if evidence else "not_established",
                evidence=evidence,
            )
        )
    return checks


def _compatibility(
    repo: Repository, intent: QueryIntent, vocab: Vocabulary
) -> list[CompatibilityNote]:
    notes: list[CompatibilityNote] = []
    repo_language = (repo.primary_language or "").lower()
    for names in intent.known_stack.values():
        for name in names:
            term = vocab.stack_term(name)
            if term is None:
                continue
            if term.role == "language":
                if repo_language == name.lower():
                    notes.append(
                        CompatibilityNote(
                            stack_item=name,
                            status="evidenced",
                            evidence=None,
                            note=f"Primary language on GitHub is {repo.primary_language}.",
                        )
                    )
                else:
                    notes.append(
                        CompatibilityNote(
                            stack_item=name,
                            status="not_established",
                            evidence=None,
                            note=(
                                "Primary language on GitHub is "
                                f"{repo.primary_language or 'unknown'}; "
                                f"{name} support is not established from source."
                            ),
                        )
                    )
                continue
            evidence = find_evidence(repo.chunks, term.aliases, max_items=1)
            if evidence:
                notes.append(
                    CompatibilityNote(
                        stack_item=name,
                        status="evidenced",
                        evidence=evidence[0],
                        note=f"{name} is mentioned in the repository's own text.",
                    )
                )
            elif term.language and repo_language == term.language.lower():
                notes.append(
                    CompatibilityNote(
                        stack_item=name,
                        status="inferred",
                        evidence=None,
                        note=f"Same primary language ({term.language}); integration not "
                        "confirmed by source.",
                    )
                )
            else:
                notes.append(
                    CompatibilityNote(
                        stack_item=name,
                        status="not_established",
                        evidence=None,
                        note=f"No mention of {name} found in the README or metadata.",
                    )
                )
    return notes


def _reasons(repo: Repository, checks: list[RequirementCheck], hit: FusedHit) -> list[str]:
    reasons: list[str] = []
    covered = [c.requirement for c in checks if c.status == "evidenced"]
    if covered:
        reasons.append(f"Mentioned in source: {', '.join(covered)}")
    reasons.append(f"Curated category: {category_label(repo.category)}")
    found_by = []
    if hit.ranks.get("keyword"):
        found_by.append(f"keyword search (rank {hit.ranks['keyword']})")
    if hit.ranks.get("semantic"):
        found_by.append(f"semantic search (rank {hit.ranks['semantic']})")
    reasons.append("Found by " + " and ".join(found_by))
    return reasons


def recommend(
    session: Session,
    request: RecommendRequest,
    providers: Providers,
    vocab: Vocabulary,
    settings: Settings,
    user_id: uuid.UUID,
) -> RecommendResponse:
    # 1. Understand
    intent = understand_query(request.query, vocab)

    # 2. Expand
    expansions = [
        e
        for label in intent.requirements
        for e in (vocab.capability_by_label(label).expansions)  # type: ignore[union-attr]
    ]
    semantic_text = " ".join([intent.goal, *intent.requirements, *expansions])
    query_terms = [t for t in tokenize(intent.goal) if t not in _FILLER]
    keyword_terms = list(dict.fromkeys([*intent.keywords, *query_terms]))

    # 3. Retrieve
    f = request.filters
    filters = SearchFilters(
        category=f.category if f else None,
        language=f.language if f else None,
        license_spdx=f.license if f else None,
    )
    keyword_hits = keyword_search(
        session, terms=keyword_terms, filters=filters, limit=CANDIDATE_LIMIT
    )
    (query_vector,) = providers.embeddings.embed_texts([semantic_text])
    semantic_hits = semantic_search(session, query_vector, filters=filters, limit=CANDIDATE_LIMIT)

    # 4. Merge
    fused = rrf_fuse(
        {
            "keyword": [h.repository_id for h in keyword_hits],
            "semantic": [h.repository_id for h in semantic_hits],
        },
        k=settings.rrf_k,
    )[:FUSED_POOL]
    if not intent.requirements:
        # Without recognised requirements there is nothing to verify against, so require
        # lexical overlap: semantic-only neighbours of an unknown query are not evidence.
        fused = [h for h in fused if h.ranks.get("keyword")]

    repos = {
        r.id: r
        for r in session.scalars(
            select(Repository)
            .options(selectinload(Repository.chunks), selectinload(Repository.analysis))
            .where(Repository.id.in_([h.repository_id for h in fused]))
        )
    }

    # 5. Rerank + 6. Verify
    scored: list[tuple[int, FusedHit, list[RequirementCheck]]] = []
    for hit in fused:
        repo = repos.get(hit.repository_id)
        if repo is None:
            continue
        checks = _requirement_checks(repo, intent, vocab)
        coverage = sum(c.status == "evidenced" for c in checks)
        if intent.requirements and coverage == 0:
            continue
        scored.append((coverage, hit, checks))
    scored.sort(key=lambda item: (-item[0], -item[1].score))
    top = scored[: request.max_results]

    # 7. Explain
    saved = saved_ids(session, user_id, (h.repository_id for _, h, _ in top))
    results: list[Recommendation] = []
    for rank, (coverage, hit, checks) in enumerate(top, start=1):
        repo = repos[hit.repository_id]
        uncovered = [c.requirement for c in checks if c.status == "not_established"]
        results.append(
            Recommendation(
                rank=rank,
                repository=to_card(repo, repo.id in saved),
                reasons=_reasons(repo, checks, hit),
                requirements=checks,
                compatibility=_compatibility(repo, intent, vocab),
                limitations=limitations_for(repo, uncovered),
                signals=RetrievalSignals(
                    keyword_rank=hit.ranks.get("keyword"),
                    semantic_rank=hit.ranks.get("semantic"),
                    rrf_score=round(hit.score, 5),
                    requirements_evidenced=coverage,
                    requirements_total=len(intent.requirements),
                ),
            )
        )

    notes: list[str] = []
    if providers.embeddings.model_name.startswith("mock"):
        notes.append(
            "Demo mode: lexical (hashed) embeddings and extractive analysis; no LLM involved."
        )
    if not results:
        notes.append(
            "No repositories matched with supporting evidence. Try describing the problem "
            "differently, or remove filters."
        )
    notes.append("Feedback capture arrives in milestone M4.")

    # 8. Learn: deferred to M4 (feedback capture).
    return RecommendResponse(
        query=request.query,
        intent=intent,
        results=results,
        pipeline=PipelineInfo(
            provider=providers.llm.model_name,
            embedding_model=providers.embeddings.model_name,
            rrf_k=settings.rrf_k,
            keyword_candidates=len(keyword_hits),
            semantic_candidates=len(semantic_hits),
            notes=notes,
        ),
        clarifying_question=intent.clarifying_question,
    )
