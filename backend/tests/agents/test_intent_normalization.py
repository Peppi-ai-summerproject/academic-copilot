import pytest

from app.agents.intent_normalization import (
    canonical_intent_keyword,
    normalize_intent_text,
)


@pytest.mark.parametrize(
    ("typo", "expected"),
    [
        ("faild", "failed"),
        ("faiked", "failed"),
        ("acadmic", "academic"),
        ("recomend", "recommend"),
        ("progres", "progress"),
        ("progresing", "progressing"),
    ],
)
def test_clear_single_keyword_typos_are_normalized(typo, expected):
    assert canonical_intent_keyword(typo) == expected


@pytest.mark.parametrize("token", ["DIN24", "DBS24", "S006", "Liisa", "Lissa"])
def test_identifiers_and_names_are_not_intent_keywords(token):
    assert canonical_intent_keyword(token) is None


def test_intent_normalization_is_a_matching_view_not_an_entity_rewrite():
    normalized = normalize_intent_text("Who faild Database Systems in DIN24?")

    assert normalized == "who failed database systems in din24?"
