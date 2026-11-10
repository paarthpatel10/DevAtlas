import re

import pytest

from app.services.search_service import build_or_tsquery


@pytest.mark.parametrize(
    "terms", [["c++"], ['"'], ["&|!:*()"], ["'; drop table"], [], ["   "], ["a:*", "b&c"]]
)
def test_hostile_terms_never_produce_invalid_syntax(terms):
    q = build_or_tsquery(terms)
    assert q is None or re.fullmatch(r"[a-z0-9 |()<\->]+", q)


def test_multiword_terms_become_phrases():
    assert build_or_tsquery(["task queue", "retries"]) == "(task <-> queue) | retries"


def test_duplicate_terms_collapsed():
    assert build_or_tsquery(["Retries", "retries", "retries "]) == "retries"


def test_dotted_tokens_split_into_parts():
    # next.js is not a valid tsquery lexeme; its alphanumeric parts are kept as a phrase.
    assert build_or_tsquery(["next.js"]) == "(next <-> js)"
