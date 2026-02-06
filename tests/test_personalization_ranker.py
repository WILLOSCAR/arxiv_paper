"""Tests for PersonalizedRanker hashing fallback."""

from datetime import datetime, timezone

from src.models import Paper
from src.personalization import PersonalizedRanker


def _paper(pid: str, title: str, abstract: str, score: float):
    now = datetime.now(timezone.utc)
    return Paper(
        arxiv_id=pid,
        title=title,
        abstract=abstract,
        authors=[],
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="",
        entry_url="",
        published=now,
        updated=now,
        score=score,
    )


def test_personalized_ranker_reranks_by_similarity():
    liked = [_paper("l1", "Transformer methods", "We study transformer attention.", 0.0)]

    p_sim = _paper("p_sim", "A transformer model", "transformer transformer", 1.0)
    p_other = _paper("p_other", "Database systems", "query optimization indexing", 1.0)
    papers = [p_other, p_sim]  # deliberately reversed

    ranker = PersonalizedRanker(enabled=True)
    ranked = ranker.rank_by_similarity(papers, liked_papers=liked, weight=1.0)

    assert [p.arxiv_id for p in ranked] == ["p_sim", "p_other"]
    assert ranked[0].similarity_score is not None
    assert ranked[0].personalized_score is not None
