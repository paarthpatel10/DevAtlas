import pytest


def full_names(response) -> list[str]:
    return [item["full_name"] for item in response.json()["items"]]


def test_list_default_sort_featured_then_stars(api):
    r = api.get("/api/v1/repositories")
    assert r.status_code == 200
    # acme/jobs is featured; then by stars desc with nulls last (searchy 5000, ui 800, bare None)
    assert full_names(r) == ["acme/jobs", "acme/searchy", "acme/ui", "acme/bare"]
    item = r.json()["items"][0]
    assert item["category_label"] == "Backend Engineering"
    assert item["is_saved"] is False
    assert item["data_source"] == "seed_snapshot"


def test_list_keyword_and_filters(api):
    r = api.get("/api/v1/repositories", params={"q": "retries", "language": "python"})
    assert full_names(r) == ["acme/jobs"]


def test_list_category_and_license_filters(api):
    r = api.get("/api/v1/repositories", params={"category": "databases_search"})
    assert full_names(r) == ["acme/searchy"]
    r = api.get("/api/v1/repositories", params={"license": "MIT"})
    assert set(full_names(r)) == {"acme/jobs", "acme/ui"}


def test_list_or_fallback_for_natural_phrase(api):
    r = api.get("/api/v1/repositories", params={"q": "retries banana"})  # AND finds nothing
    assert "acme/jobs" in full_names(r)


@pytest.mark.parametrize("q", ["c++", '"', "&|!:*()", "'; drop table repositories; --"])
def test_list_hostile_query_is_safe(api, q):
    assert api.get("/api/v1/repositories", params={"q": q}).status_code == 200


def test_sort_by_name(api):
    r = api.get("/api/v1/repositories", params={"sort": "name"})
    assert full_names(r) == ["acme/bare", "acme/jobs", "acme/searchy", "acme/ui"]


def test_pagination_metadata(api):
    r = api.get("/api/v1/repositories", params={"page_size": 2, "page": 2})
    body = r.json()
    assert (body["total"], body["page"], body["page_size"]) == (4, 2, 2)
    assert full_names(r) == ["acme/ui", "acme/bare"]


def test_page_size_validation(api):
    r = api.get("/api/v1/repositories", params={"page_size": 500})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_detail_case_insensitive_and_unknown_404(api):
    assert api.get("/api/v1/repositories/ACME/Jobs").json()["full_name"] == "acme/jobs"
    r = api.get("/api/v1/repositories/nobody/nothing")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_detail_content(api):
    d = api.get("/api/v1/repositories/acme/jobs").json()
    assert d["analysis"]["generated_by_label"] == "Extractive demo analyzer (no LLM)"
    assert d["analysis"]["capabilities"][0]["evidence"]
    assert {s["label"] for s in d["sources"]} >= {"GitHub repository", "README"}
    assert any(s["label"] == "Last push" for s in d["maintenance_signals"])
    assert all("snapshot" in s["explanation"] for s in d["maintenance_signals"])


def test_detail_missing_values_are_null_not_invented(api):
    d = api.get("/api/v1/repositories/acme/bare").json()
    assert d["stars"] is None and d["license_spdx"] is None
    assert d["analysis"]["summary"] is None
    assert d["maintenance_signals"] == []
    assert [s["label"] for s in d["sources"]] == ["GitHub repository"]


def test_save_unsave_idempotent_and_listed(api):
    for _ in range(2):
        assert api.post("/api/v1/repositories/acme/jobs/save").json() == {"saved": True}
    assert full_names(api.get("/api/v1/me/saved")) == ["acme/jobs"]
    assert api.get("/api/v1/repositories/acme/jobs").json()["is_saved"] is True
    assert api.get("/api/v1/repositories", params={"q": "retries"}).json()["items"][0]["is_saved"]
    for _ in range(2):
        assert api.delete("/api/v1/repositories/acme/jobs/save").json() == {"saved": False}
    assert api.get("/api/v1/me/saved").json()["total"] == 0


def test_save_unknown_repo_404(api):
    assert api.post("/api/v1/repositories/nobody/nothing/save").status_code == 404


def test_facets_counts(api):
    f = api.get("/api/v1/repositories/facets").json()
    assert {"value": "backend", "label": "Backend Engineering", "count": 2} in f["categories"]
    assert {"value": "Python", "count": 1} in f["languages"]
    assert {"value": "MIT", "count": 2} in f["licenses"]
    assert all(v["value"] is not None for v in f["languages"] + f["licenses"])
