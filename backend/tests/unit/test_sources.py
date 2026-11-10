from app.services.repository_service import build_sources
from tests.factories import make_repo


def test_only_http_links_are_emitted_for_untrusted_urls():
    repo = make_repo(
        homepage_url="javascript:alert(1)",
        readme_url="https://github.com/acme/example/blob/main/README.md",
    )
    assert [s.label for s in build_sources(repo)] == ["GitHub repository", "README"]


def test_http_homepage_is_kept():
    repo = make_repo(homepage_url="https://docs.example.dev")
    assert [s.url for s in build_sources(repo)][-1] == "https://docs.example.dev"
