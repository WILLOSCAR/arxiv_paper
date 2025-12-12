"""Tests for LangGraph agent modules."""

import pytest
from unittest.mock import patch, MagicMock

# Test AgentConfig
class TestAgentConfig:
    """Test AgentConfig class."""

    def test_from_dict_basic(self):
        """Test creating AgentConfig from dictionary."""
        from src.agents.config import AgentConfig

        config_dict = {
            "enabled": True,
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.3,
            "api": {
                "api_key_env": "TEST_API_KEY",
            },
            "features": {
                "preference_analysis": True,
                "dynamic_query_generation": True,
            },
            "min_feedback_count": 5,
        }

        config = AgentConfig.from_dict(config_dict)

        assert config.enabled is True
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.min_feedback_count == 5

    def test_to_dict(self):
        """Test converting AgentConfig to dictionary."""
        from src.agents.config import AgentConfig

        config = AgentConfig(
            enabled=True,
            provider="openai",
            model="gpt-4o",
        )

        config_dict = config.to_dict()

        assert config_dict["enabled"] is True
        assert config_dict["provider"] == "openai"


# Test AgentState
class TestAgentState:
    """Test AgentState type."""

    def test_create_state(self):
        """Test creating agent state."""
        from src.agents.state import AgentState

        state: AgentState = {
            "papers": [{"arxiv_id": "123", "title": "Test"}],
            "feedback_history": {"liked": [], "disliked": []},
            "user_profile": None,
            "config": {},
            "interest_analysis": None,
            "synthetic_query": None,
            "enhanced_keywords": None,
            "scored_papers": [],
            "validated_papers": [],
            "explanations": None,
            "messages": [],
            "iteration": 0,
            "should_rerank": False,
        }

        assert len(state["papers"]) == 1
        assert state["iteration"] == 0


# Test Orchestrator
class TestOrchestrator:
    """Test Orchestrator class."""

    def test_static_mode(self):
        """Test orchestrator with static mode."""
        from src.integration.orchestrator import Orchestrator, OrchestratorConfig
        from src.models import FilterConfig

        config = OrchestratorConfig(
            filter_config=FilterConfig(
                enabled=True,
                mode="static",
                keywords={"high_priority": ["test"]},
                min_score=0.0,
                top_k=10,
            ),
            personalization_config={},
            mode="static",
        )

        orchestrator = Orchestrator(config)
        assert orchestrator.config.mode == "static"

    def test_from_dict(self):
        """Test creating OrchestratorConfig from dict."""
        from src.integration.orchestrator import OrchestratorConfig

        config_dict = {
            "filter": {
                "enabled": True,
                "mode": "static",
                "keywords": {},
                "min_score": 1.0,
                "top_k": 20,
            },
            "personalization": {
                "agent": {"enabled": False},
            },
        }

        config = OrchestratorConfig.from_dict(config_dict)
        assert config.mode == "static"


# Test scoring node
class TestScoringNode:
    """Test scoring node logic."""

    def test_keyword_matches(self):
        """Test keyword matching function."""
        from src.agents.nodes.scoring import _keyword_matches

        assert _keyword_matches("transformer", "This paper uses transformer architecture")
        assert _keyword_matches("CLIP", "We propose CLIP-based method")
        assert _keyword_matches("attention", "The patient needs attention")  # word matches
        assert not _keyword_matches("transform", "This paper uses transformer architecture")  # partial no match

    def test_calculate_agent_score(self):
        """Test agent score calculation."""
        from src.agents.nodes.scoring import _calculate_agent_score

        paper = {
            "title": "Vision Transformer for Image Classification",
            "abstract": "We propose a transformer-based model for vision tasks.",
        }

        enhanced_keywords = {
            "high_priority": ["transformer", "vision"],
            "medium_priority": ["classification"],
            "negative": ["reinforcement"],
        }

        interest_analysis = {
            "main_interests": ["transformer"],
            "emerging_interests": [],
            "disliked_topics": [],
        }

        score = _calculate_agent_score(paper, enhanced_keywords, interest_analysis)
        assert score > 0  # Should have positive score


# Test prompts
class TestPrompts:
    """Test prompt templates."""

    def test_analysis_prompt_has_placeholders(self):
        """Test that analysis prompt has required placeholders."""
        from src.agents.prompts import ANALYSIS_PROMPT

        assert "{liked_papers}" in ANALYSIS_PROMPT
        assert "{disliked_papers}" in ANALYSIS_PROMPT
        assert "{paper_count}" in ANALYSIS_PROMPT

    def test_query_generation_prompt_has_placeholders(self):
        """Test that query generation prompt has required placeholders."""
        from src.agents.prompts import QUERY_GENERATION_PROMPT

        assert "{main_interests}" in QUERY_GENERATION_PROMPT
        assert "{emerging_interests}" in QUERY_GENERATION_PROMPT

    def test_validation_prompt_has_placeholders(self):
        """Test that validation prompt has required placeholders."""
        from src.agents.prompts import VALIDATION_PROMPT

        assert "{papers}" in VALIDATION_PROMPT
        assert "{user_interests}" in VALIDATION_PROMPT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
