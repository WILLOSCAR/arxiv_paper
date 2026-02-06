"""Tests for DynamicFilter (preference learning)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.filter import DynamicFilter
from src.models import FilterConfig, Paper


@pytest.fixture
def _now():
    return datetime.now(timezone.utc)


def test_dynamic_filter_boosts_liked_and_penalizes_disliked(_now):
    cfg = FilterConfig(
        enabled=True,
        mode="dynamic",
        keywords={
            "high_priority": ["transformer"],
            "medium_priority": ["diffusion"],
        },
        min_score=0.0,
        top_k=10,
    )

    papers = [
        Paper(
            arxiv_id="p1",
            title="Transformer models for vision",
            abstract="We study transformer architectures.",
            authors=[],
            primary_category="cs.CV",
            categories=["cs.CV"],
            pdf_url="",
            entry_url="",
            published=_now,
            updated=_now,
        ),
        Paper(
            arxiv_id="p2",
            title="Diffusion models for generation",
            abstract="We study diffusion.",
            authors=[],
            primary_category="cs.CV",
            categories=["cs.CV"],
            pdf_url="",
            entry_url="",
            published=_now,
            updated=_now,
        ),
    ]

    f = DynamicFilter(cfg)
    ranked = f.filter_and_rank(
        papers,
        context={
            "feedback": {
                "liked": [{"matched_keywords": ["diffusion"]}],
                "disliked": [{"matched_keywords": ["transformer"]}],
            }
        },
    )

    assert [p.arxiv_id for p in ranked][:2] == ["p2", "p1"]
    scores = {p.arxiv_id: p.score for p in ranked}
    assert scores["p2"] > scores["p1"]


def test_dynamic_filter_save_and_load_model(tmp_path: Path, _now):
    cfg = FilterConfig(enabled=True, mode="dynamic", keywords={}, min_score=0.0, top_k=10)
    f = DynamicFilter(cfg)
    f.preference_vector["liked"].update(["transformer", "diffusion"])
    f.preference_vector["disliked"].update(["survey"])

    path = tmp_path / "pref.json"
    f.save_preference_model(str(path))

    f2 = DynamicFilter(cfg)
    f2.load_preference_model(str(path))

    assert f2.preference_vector["liked"]["transformer"] == 1
    assert f2.preference_vector["liked"]["diffusion"] == 1
    assert f2.preference_vector["disliked"]["survey"] == 1

