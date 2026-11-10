import json

URL = "/api/v1/assistant/recommend"


def result_names(body) -> list[str]:
    return [r["repository"]["full_name"] for r in body["results"]]


def test_recommend_returns_evidenced_shortlist(api):
    r = api.post(URL, json={"query": "Python task queue with retries and scheduling for FastAPI"})
    assert r.status_code == 200
    body = r.json()
    top = body["results"][0]
    assert top["repository"]["full_name"] == "acme/jobs"
    statuses = {c["requirement"]: c["status"] for c in top["requirements"]}
    assert statuses["retries"] == "evidenced" and statuses["scheduling"] == "evidenced"
    retries = next(c for c in top["requirements"] if c["requirement"] == "retries")
    assert "retries" in retries["evidence"][0]["snippet"].lower()
    assert retries["evidence"][0]["source_url"].endswith("README.md")
    fastapi = next(c for c in top["compatibility"] if c["stack_item"] == "FastAPI")
    assert fastapi["status"] == "evidenced"  # the fixture README mentions FastAPI
    assert "%" not in json.dumps(body["results"])  # no match percentages anywhere
    assert top["signals"]["requirements_evidenced"] >= 2
    assert body["intent"]["known_stack"] == {"backend": ["FastAPI"], "language": ["Python"]}
    assert body["pipeline"]["provider"] == "mock"


def test_unrelated_repos_filtered_out_when_requirements_known(api):
    body = api.post(URL, json={"query": "task queue with retries and scheduling"}).json()
    assert "acme/ui" not in result_names(body)
    assert "acme/bare" not in result_names(body)


def test_inferred_compatibility_from_language(api):
    body = api.post(URL, json={"query": "background jobs with retries for a Django app"}).json()
    top = body["results"][0]
    django = next(c for c in top["compatibility"] if c["stack_item"] == "Django")
    assert django["status"] == "evidenced"  # README says "Works with FastAPI and Django apps"
    body = api.post(URL, json={"query": "background jobs with retries for a Flask app"}).json()
    flask = next(c for c in body["results"][0]["compatibility"] if c["stack_item"] == "Flask")
    assert flask["status"] == "inferred" and "not confirmed" in flask["note"]


def test_unknown_vocabulary_query_still_returns_hybrid_results(api):
    r = api.post(URL, json={"query": "something for searching my products"})
    assert r.status_code == 200
    assert "acme/searchy" in result_names(r.json())


def test_nonsense_query_returns_empty_with_note(api):
    body = api.post(URL, json={"query": "qwzxv plorf"}).json()
    assert body["results"] == []
    assert any("No repositories matched" in n for n in body["pipeline"]["notes"])


def test_max_results_and_filters(api):
    body = api.post(
        URL,
        json={"query": "retries scheduling typo tolerance search engine", "max_results": 1},
    ).json()
    assert len(body["results"]) == 1
    body = api.post(
        URL,
        json={"query": "retries and typo tolerance", "filters": {"category": "databases_search"}},
    ).json()
    assert result_names(body) == ["acme/searchy"]


def test_query_validation(api):
    r = api.post(URL, json={"query": "  "})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert api.post(URL, json={"query": "x" * 1001}).status_code == 422
    assert api.post(URL, json={"query": "queue", "max_results": 11}).status_code == 422


def test_saved_state_reflected(api):
    api.post("/api/v1/repositories/acme/jobs/save")
    body = api.post(URL, json={"query": "task queue with retries"}).json()
    assert body["results"][0]["repository"]["is_saved"] is True
