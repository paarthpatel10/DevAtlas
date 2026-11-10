import uuid

from app.ai.insights import ModelReport, extractive_report, ground
from app.models import RepositoryAnalysis, RepositoryChunk
from tests.factories import make_repo

SOURCE_URL = "https://github.com/acme/jobs/blob/main/README.md"
ID_MAP = {
    "C1": RepositoryChunk(
        id=uuid.uuid4(),
        position=0,
        section_title="Features",
        source_type="readme",
        content="Automatic retries with exponential backoff. Docs: https://jobs.dev/docs",
        content_hash="a",
        source_url=SOURCE_URL,
    ),
}
SOURCE_TEXT = ID_MAP["C1"].content


def report(**overrides) -> ModelReport:
    data = {
        "what_is_it": {"one_line": "A job queue.", "explanation": "Runs jobs.", "cites": ["C1"]},
        "problem_solved": {"text": "Running work outside requests.", "cites": ["C1"]},
        "why_interesting": [
            {"point": "Built-in retries with backoff.", "cites": ["C1"]},
            {"point": "The fastest queue in the world.", "cites": []},
            {"point": "Used by NASA.", "cites": ["C7"]},
        ],
        "who_should_care": [
            {"audience": "Backend developers", "reason": "Retries.", "cites": ["C1"]}
        ],
        "use_cases": [{"text": "Email sending.", "cites": ["C1"]}],
        "build_ideas": [
            {
                "title": "Notification worker",
                "description": "Send emails in the background.",
                "how_it_is_used": "Enqueue jobs with retries.",
                "complementary_tech": ["Redis"],
                "cites": ["C1"],
            },
            {
                "title": "Uncited idea",
                "description": "x",
                "how_it_is_used": "y",
                "complementary_tech": [],
                "cites": [],
            },
        ],
        "technical": {
            "frameworks": [{"name": "Python", "cites": ["C1"]}],
            "capabilities": [{"name": "Retries", "cites": ["C1"]}, {"name": "Magic", "cites": []}],
            "integrations": [],
            "prerequisites": [],
            "architecture": None,
        },
        "limitations": [{"text": "Not established", "cites": []}],
        "getting_started": [
            {"label": "Docs", "url": "https://jobs.dev/docs", "cites": ["C1"]},
            {"label": "Invented", "url": "https://jobs.dev/invented", "cites": ["C1"]},
            {"label": "Script", "url": "javascript:alert(1)", "cites": ["C1"]},
        ],
    }
    data.update(overrides)
    return ModelReport(**data)


def test_uncited_and_unknown_citations_are_dropped():
    g = ground(report(), ID_MAP, SOURCE_TEXT)
    assert [p.point for p in g.why_interesting] == ["Built-in retries with backoff."]
    assert [i.title for i in g.build_ideas] == ["Notification worker"]
    assert [c.name for c in g.technical.capabilities] == ["Retries"]
    assert g.limitations == []
    assert g.generated is True


def test_citations_resolve_to_source_excerpts():
    g = ground(report(), ID_MAP, SOURCE_TEXT)
    citation = g.why_interesting[0].citations[0]
    assert citation.id == "C1" and citation.section_title == "Features"
    assert citation.source_url == SOURCE_URL
    assert citation.excerpt.startswith("Automatic retries")


def test_getting_started_urls_must_appear_in_sources_and_be_http():
    g = ground(report(), ID_MAP, SOURCE_TEXT)
    assert [link.url for link in g.getting_started] == ["https://jobs.dev/docs"]


def test_uncited_summary_is_not_presented_as_generated():
    g = ground(
        report(what_is_it={"one_line": "Best ever", "explanation": "x", "cites": []}),
        ID_MAP,
        SOURCE_TEXT,
    )
    assert g.what_is_it is None


def test_build_ideas_capped_at_three():
    idea = {
        "title": "t",
        "description": "d",
        "how_it_is_used": "h",
        "complementary_tech": [],
        "cites": ["C1"],
    }
    ideas = [{**idea, "title": f"idea {i}"} for i in range(5)]
    assert len(ground(report(build_ideas=ideas), ID_MAP, SOURCE_TEXT).build_ideas) == 3


def test_extractive_report_without_llm():
    repo = make_repo(description="A job queue for Python")
    repo.analysis = RepositoryAnalysis(
        summary="A job queue for Python",
        capabilities=[],
        analysis_version="v",
        model_name="mock",
        prompt_version="none",
    )
    r = extractive_report(repo)
    assert r.generated is False
    assert r.what_is_it.one_line == "A job queue for Python"
    assert r.build_ideas == [] and r.why_interesting == []
