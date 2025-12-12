"""Tests for static flow pipeline (Fetcher → Filter → Storage)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.models import Paper, FetchConfig, FilterConfig
from src.fetcher import ArxivFetcher
from src.filter import PaperFilter
from src.validators import StageValidator, ValidationResult, validate_pipeline_stage
from src.integration.orchestrator import Orchestrator, OrchestratorConfig


# ===== Test Fixtures =====


@pytest.fixture
def sample_papers():
    """Create sample papers for testing."""
    now = datetime.now(timezone.utc)
    return [
        Paper(
            arxiv_id="2401.00001",
            title="Vision Transformer for Image Classification",
            abstract="We propose a transformer-based model for image classification tasks.",
            authors=["Author A", "Author B"],
            primary_category="cs.CV",
            categories=["cs.CV", "cs.AI"],
            pdf_url="https://arxiv.org/pdf/2401.00001",
            entry_url="https://arxiv.org/abs/2401.00001",
            published=now,
            updated=now,
        ),
        Paper(
            arxiv_id="2401.00002",
            title="Diffusion Models for Text Generation",
            abstract="We explore diffusion models for natural language generation.",
            authors=["Author C"],
            primary_category="cs.CL",
            categories=["cs.CL"],
            pdf_url="https://arxiv.org/pdf/2401.00002",
            entry_url="https://arxiv.org/abs/2401.00002",
            published=now,
            updated=now,
        ),
        Paper(
            arxiv_id="2401.00003",
            title="Reinforcement Learning Survey",
            abstract="A comprehensive survey of reinforcement learning methods.",
            authors=["Author D"],
            primary_category="cs.LG",
            categories=["cs.LG"],
            pdf_url="https://arxiv.org/pdf/2401.00003",
            entry_url="https://arxiv.org/abs/2401.00003",
            published=now,
            updated=now,
        ),
    ]


@pytest.fixture
def filter_config():
    """Create filter configuration for testing."""
    return FilterConfig(
        enabled=True,
        mode="static",
        keywords={
            "high_priority": ["transformer", "diffusion"],
            "medium_priority": ["classification", "generation"],
            "low_priority": ["deep learning"],
        },
        min_score=1.0,
        top_k=10,
    )


# ===== Test Validators =====


class TestStageValidator:
    """Test stage validators."""

    def test_validate_fetch_result_success(self, sample_papers):
        """Test successful fetch validation."""
        result = StageValidator.validate_fetch_result(sample_papers)
        assert result.success
        assert result.details["total_count"] == 3
        assert result.details["valid_count"] == 3

    def test_validate_fetch_result_empty(self):
        """Test fetch validation with empty result."""
        result = StageValidator.validate_fetch_result([])
        assert result.success  # Empty is valid when expected_min=0
        assert result.details["total_count"] == 0

    def test_validate_fetch_result_missing_fields(self):
        """Test fetch validation with missing fields."""
        now = datetime.now(timezone.utc)
        papers = [
            Paper(
                arxiv_id="123",
                title="",  # Missing title
                abstract="test",
                authors=[],
                primary_category="cs.CV",
                categories=["cs.CV"],
                pdf_url="",
                entry_url="",
                published=now,
                updated=now,
            )
        ]
        result = StageValidator.validate_fetch_result(papers)
        assert len(result.details["missing_fields"]) > 0

    def test_validate_filter_result_success(self, sample_papers, filter_config):
        """Test successful filter validation."""
        # Score the papers first
        paper_filter = PaperFilter(filter_config)
        filtered = paper_filter.filter_and_rank(sample_papers)

        result = StageValidator.validate_filter_result(filtered, filter_config)
        assert result.success
        assert result.details["scored_count"] == len(filtered)

    def test_validate_api_response_success(self):
        """Test API response validation."""
        response = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100},
        }
        result = StageValidator.validate_api_response(response)
        assert result.success

    def test_validate_api_response_error(self):
        """Test API response validation with error."""
        response = {"error": {"message": "Rate limit exceeded"}}
        result = StageValidator.validate_api_response(response)
        assert not result.success
        assert "error" in result.message.lower()

    def test_validate_pipeline_stage(self, sample_papers):
        """Test convenience function."""
        result = validate_pipeline_stage("fetch", sample_papers)
        assert result.success


# ===== Test Filter =====


class TestPaperFilter:
    """Test PaperFilter functionality."""

    def test_filter_basic(self, sample_papers, filter_config):
        """Test basic filtering."""
        paper_filter = PaperFilter(filter_config)
        filtered = paper_filter.filter_and_rank(sample_papers)

        # Should filter based on keywords
        assert len(filtered) > 0
        for paper in filtered:
            assert paper.score >= filter_config.min_score
            assert len(paper.matched_keywords) > 0

    def test_filter_scoring(self, sample_papers, filter_config):
        """Test scoring is applied correctly."""
        paper_filter = PaperFilter(filter_config)
        filtered = paper_filter.filter_and_rank(sample_papers)

        # Papers are sorted by score
        if len(filtered) > 1:
            for i in range(len(filtered) - 1):
                assert filtered[i].score >= filtered[i + 1].score

    def test_filter_top_k(self, sample_papers, filter_config):
        """Test top_k limiting."""
        filter_config.top_k = 2
        paper_filter = PaperFilter(filter_config)
        filtered = paper_filter.filter_and_rank(sample_papers)

        assert len(filtered) <= 2

    def test_filter_disabled(self, sample_papers, filter_config):
        """Test filter when disabled."""
        filter_config.enabled = False
        paper_filter = PaperFilter(filter_config)
        filtered = paper_filter.filter_and_rank(sample_papers)

        # Should return all papers when disabled
        assert len(filtered) == len(sample_papers)

    def test_filter_statistics(self, sample_papers, filter_config):
        """Test statistics calculation."""
        paper_filter = PaperFilter(filter_config)
        filtered = paper_filter.filter_and_rank(sample_papers)
        stats = paper_filter.get_statistics(filtered)

        assert "total_papers" in stats
        assert "avg_score" in stats
        assert "top_keywords" in stats


# ===== Test Orchestrator =====


class TestOrchestrator:
    """Test Orchestrator functionality."""

    def test_static_mode(self, filter_config):
        """Test orchestrator in static mode."""
        config = OrchestratorConfig(
            filter_config=filter_config,
            personalization_config={},
            mode="static",
        )
        orchestrator = Orchestrator(config)
        assert orchestrator.config.mode == "static"

    def test_process_static(self, sample_papers, filter_config):
        """Test processing in static mode."""
        config = OrchestratorConfig(
            filter_config=filter_config,
            personalization_config={"feedback": {"feedback_dir": "/tmp/test"}},
            mode="static",
        )

        with patch.object(
            Orchestrator, "_build_context", return_value={"feedback": {}, "profile": None}
        ):
            orchestrator = Orchestrator(config)
            result = orchestrator.process(sample_papers)

            assert len(result) > 0
            for paper in result:
                assert paper.score >= filter_config.min_score

    def test_get_statistics(self, sample_papers, filter_config):
        """Test statistics retrieval."""
        config = OrchestratorConfig(
            filter_config=filter_config,
            personalization_config={},
            mode="static",
        )

        with patch.object(
            Orchestrator, "_build_context", return_value={"feedback": {}, "profile": None}
        ):
            orchestrator = Orchestrator(config)
            result = orchestrator.process(sample_papers)
            stats = orchestrator.get_statistics(result)

            assert "filter_mode" in stats
            assert stats["filter_mode"] == "static"


# ===== Test Profile Building (Cold-Start) =====


class TestColdStartProfile:
    """Test Cold-Start profile building."""

    def test_build_profile_from_config(self):
        """Test profile building from config keywords."""
        from src.agents.nodes.profile import build_profile_node
        from src.agents.state import AgentState

        state = AgentState(
            papers=[],
            feedback_history={"liked": [], "disliked": []},
            user_profile=None,
            config={
                "keywords": {
                    "high_priority": ["transformer", "diffusion"],
                    "medium_priority": ["classification"],
                    "low_priority": ["deep learning"],
                }
            },
            interest_profile=None,
            interest_analysis=None,
            synthetic_query=None,
            enhanced_keywords=None,
            scored_papers=[],
            validated_papers=[],
            explanations=None,
            messages=[],
            iteration=0,
            should_rerank=False,
        )

        result = build_profile_node(state)

        assert "interest_profile" in result
        profile = result["interest_profile"]
        assert profile["source"] == "config"
        assert "transformer" in profile["main_interests"]
        assert profile["confidence"] == 0.7

    def test_build_profile_with_feedback(self):
        """Test profile building with feedback enhancement."""
        from src.agents.nodes.profile import build_profile_node
        from src.agents.state import AgentState

        state = AgentState(
            papers=[],
            feedback_history={
                "liked": [
                    {"title": "CLIP paper", "abstract": "contrastive learning"},
                ],
                "disliked": [],
            },
            user_profile=None,
            config={
                "keywords": {
                    "high_priority": ["transformer"],
                    "medium_priority": [],
                    "low_priority": [],
                }
            },
            interest_profile=None,
            interest_analysis=None,
            synthetic_query=None,
            enhanced_keywords=None,
            scored_papers=[],
            validated_papers=[],
            explanations=None,
            messages=[],
            iteration=0,
            should_rerank=False,
        )

        result = build_profile_node(state)

        profile = result["interest_profile"]
        assert profile["source"] == "config+feedback"
        assert profile["confidence"] > 0.7  # Higher with feedback


# ===== Test Scoring with Profile =====


class TestProfileScoring:
    """Test scoring with interest profile."""

    def test_calculate_profile_score(self):
        """Test profile-based scoring."""
        from src.agents.nodes.scoring import _calculate_profile_score

        paper = {
            "title": "Vision Transformer for Image Classification",
            "abstract": "We propose a transformer-based approach.",
        }

        profile = {
            "main_interests": ["transformer", "vision"],
            "secondary_interests": ["classification"],
            "avoid_topics": ["reinforcement"],
        }

        score = _calculate_profile_score(paper, profile)
        assert score > 0  # Should have positive score


# ===== Integration Test =====


class TestFullStaticPipeline:
    """Integration test for full static pipeline."""

    def test_full_pipeline_mock(self, sample_papers, filter_config):
        """Test full pipeline with mocked fetcher."""
        # Mock the fetcher
        with patch.object(ArxivFetcher, "fetch_latest_papers", return_value=sample_papers):
            fetch_config = FetchConfig(
                categories=["cs.CV"],
                max_results=10,
            )
            fetcher = ArxivFetcher(fetch_config)
            papers = fetcher.fetch_latest_papers(days=1)

            # Validate fetch
            fetch_result = StageValidator.validate_fetch_result(papers)
            assert fetch_result.success

            # Filter
            paper_filter = PaperFilter(filter_config)
            filtered = paper_filter.filter_and_rank(papers)

            # Validate filter
            filter_result = StageValidator.validate_filter_result(filtered, filter_config)
            assert filter_result.success

            # Verify output
            assert len(filtered) > 0
            assert all(p.score >= filter_config.min_score for p in filtered)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
