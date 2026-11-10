import pytest
from sqlalchemy import select

from app.models import Repository
from app.services.search_service import SearchFilters, keyword_search, semantic_search


def names(session, hits) -> list[str]:
    by_id = dict(session.execute(select(Repository.id, Repository.full_name)).all())
    return [by_id[h.repository_id] for h in hits]


def test_keyword_text_search_finds_readme_term(seeded):
    hits = keyword_search(seeded, text="retries", filters=SearchFilters())
    assert names(seeded, hits)[0] == "acme/jobs"
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))


def test_keyword_text_search_uses_and_semantics(seeded):
    assert keyword_search(seeded, text="retries typo", filters=SearchFilters()) == []


def test_keyword_or_terms_search(seeded):
    hits = keyword_search(seeded, terms=["retries", "typo tolerance"], filters=SearchFilters())
    assert set(names(seeded, hits)) == {"acme/jobs", "acme/searchy"}


@pytest.mark.parametrize(
    "text", ["c++", '"unbalanced', "a & | ! b", "'; drop table repositories; --", "   "]
)
def test_keyword_search_tolerates_hostile_text(seeded, text):
    keyword_search(seeded, text=text, filters=SearchFilters())  # must not raise


def test_filters_restrict_results(seeded):
    hits = keyword_search(
        seeded, terms=["accessible", "retries"], filters=SearchFilters(language="typescript")
    )
    assert names(seeded, hits) == ["acme/ui"]
    hits = keyword_search(
        seeded, terms=["retries", "typo"], filters=SearchFilters(category="databases_search")
    )
    assert names(seeded, hits) == ["acme/searchy"]
    hits = keyword_search(
        seeded, terms=["retries", "typo"], filters=SearchFilters(license_spdx="apache-2.0")
    )
    assert names(seeded, hits) == ["acme/searchy"]


def test_semantic_search_ranks_related_repo_first(seeded, providers):
    (vector,) = providers.embeddings.embed_texts(["background job queue with retries"])
    hits = semantic_search(seeded, vector, filters=SearchFilters())
    assert names(seeded, hits)[0] == "acme/jobs"
    assert hits[0].chunk_id is not None or hits[0].score > 0
    assert len(set(names(seeded, hits))) == len(hits)  # one hit per repository


def test_semantic_search_respects_filters(seeded, providers):
    (vector,) = providers.embeddings.embed_texts(["background job queue with retries"])
    hits = semantic_search(seeded, vector, filters=SearchFilters(category="frontend"))
    assert names(seeded, hits) == ["acme/ui"]


def test_semantic_search_zero_vector_returns_empty(seeded):
    assert semantic_search(seeded, [0.0] * 1024, filters=SearchFilters()) == []
