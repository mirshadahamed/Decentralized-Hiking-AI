"""Regression and integration tests using real FTS5 evidence."""
import pytest

from research.rag.scripts.context_builder import normalize_country_context, prepare_bounded_localized_context
from research.rag.scripts.retrieval import retrieve_offline_knowledge


ALLERGIC_QUESTION = "What should I do if a hiker develops a serious allergic reaction?"
INSECT_QUESTION = "What should I do for insect bites or stings while hiking?"


def test_allergic_top_four_retrieval_and_bounded_continuity():
    seeds = retrieve_offline_knowledge(ALLERGIC_QUESTION, "allergic_reaction", limit=4)
    prepared = prepare_bounded_localized_context(seeds, neighbor_distance=1, max_words=1200)
    bounded = prepared["bounded_results"]
    assert len(seeds) == 4
    assert set(seeds["chunk_id"]).issubset(set(bounded["chunk_id"]))
    assert "CHK_01792" in set(bounded["chunk_id"])
    assert int(bounded["word_count"].sum()) <= 1200
    assert len(bounded) == 7
    assert int(bounded["word_count"].sum()) == 1002


def test_real_foreign_evidence_is_localized_without_losing_allergic_terms():
    prepared = prepare_bounded_localized_context(
        retrieve_offline_knowledge(ALLERGIC_QUESTION, "allergic_reaction", limit=4)
    )
    context = prepared["localized_context"].lower()
    assert not any(value in context for value in ("999", "111", "nhs"))
    assert "adrenaline" in context
    assert "auto-injector" in context


def test_missing_category_regression_uses_real_exp_sources():
    assert set(retrieve_offline_knowledge(INSECT_QUESTION, "insect_bites_stings", 4)["source_id"]) == {"EXP_016"}
    assert set(retrieve_offline_knowledge(ALLERGIC_QUESTION, "allergic_reaction", 4)["source_id"]) == {"EXP_017"}


@pytest.mark.parametrize(("value", "expected"), [
    ("United Kingdom", "united kingdom"), ("United Kingdom (England)", "united kingdom"),
    ("United States", "united states"), ("New Zealand", "new zealand"),
    ("Sri Lanka", "sri lanka"), ("International", "international"), (None, "not specified"),
])
def test_country_normalization(value, expected):
    assert normalize_country_context(value) == expected
