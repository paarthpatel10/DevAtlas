from app.ai.query_understanding import understand_query
from app.ai.vocabulary import match_phrases


def test_extracts_requirements_stack_and_category(vocab):
    i = understand_query(
        "I am building a FastAPI application and need background jobs with retries and scheduling",
        vocab,
    )
    assert i.requirements == ["background jobs", "retries", "scheduling"]
    assert i.known_stack == {"backend": ["FastAPI"]}
    assert i.category == "backend"
    assert i.preferred_license is None
    assert any("backend" in note.lower() for note in i.inferred)
    assert any("Python" in note for note in i.inferred)  # language implied by FastAPI
    assert "task queue" in i.keywords and "FastAPI" in i.keywords


def test_goal_preserves_user_text(vocab):
    assert understand_query("  vector database for embeddings  ", vocab).goal == (
        "vector database for embeddings"
    )


def test_does_not_invent_constraints(vocab):
    assert understand_query("vector database for embeddings", vocab).constraints == []


def test_explicit_constraint_kept(vocab):
    assert understand_query("task queue without Redis", vocab).constraints == ["without Redis"]


def test_short_vague_query_asks_clarifying_question(vocab):
    assert understand_query("help me", vocab).clarifying_question is not None


def test_short_but_specific_query_does_not_ask(vocab):
    assert understand_query("rbac", vocab).clarifying_question is None


def test_dotted_and_cased_stack_terms(vocab):
    assert understand_query("NEXT.JS app with postgres", vocab).known_stack == {
        "frontend": ["Next.js"],
        "database": ["PostgreSQL"],
    }


def test_license_only_when_licensing_is_mentioned(vocab):
    assert understand_query("MIT licensed task queue", vocab).preferred_license == "MIT"
    assert understand_query("task queue from MIT researchers", vocab).preferred_license is None


def test_unknown_vocabulary_gives_empty_intent_without_category(vocab):
    i = understand_query("something to make my thing nicer", vocab)
    assert i.requirements == [] and i.category is None and i.known_stack == {}


def test_match_phrases_word_boundaries():
    assert match_phrases("We support retries.", ["retries", "retry"]) == ["retries"]
    assert match_phrases("Retrying-unrelated", ["retry"]) == []
    assert match_phrases("Built with Next.js and C++", ["next.js", "c++"]) == ["next.js", "c++"]
