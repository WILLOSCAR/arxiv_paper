"""LangGraph graph construction for agent pipeline."""

import logging
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .config import AgentConfig
from .nodes import (
    build_profile_node,
    score_papers_node,
    validation_node,
    # Legacy nodes (for enhanced mode with feedback)
    analysis_node,
    query_generation_node,
)

logger = logging.getLogger(__name__)


def build_agent_graph(config: AgentConfig) -> StateGraph:
    """
    Build the LangGraph agent pipeline.

    Cold-Start Mode (default):
    ```
    START
      │
      ▼
    build_profile (from config keywords)
      │
      ▼
    score_papers (using interest_profile)
      │
      ▼
    validate_ranking
      │
      ▼
    END
    ```

    This flow works without historical feedback by using
    config keywords as the interest profile source.

    Args:
        config: AgentConfig with pipeline settings

    Returns:
        Compiled StateGraph ready for invocation
    """
    logger.info(f"Building agent graph with config: model={config.model}")

    # Create state graph builder
    builder = StateGraph(AgentState)

    # ===== Add Nodes (Cold-Start flow) =====
    builder.add_node("build_profile", build_profile_node)
    builder.add_node("score_papers", score_papers_node)
    builder.add_node("validate_ranking", validation_node)

    # ===== Define Edges (Linear flow, no conditions) =====
    builder.add_edge(START, "build_profile")
    builder.add_edge("build_profile", "score_papers")
    builder.add_edge("score_papers", "validate_ranking")
    builder.add_edge("validate_ranking", END)

    # ===== Compile Graph =====
    # Use MemorySaver for checkpointing (enables state persistence)
    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory)

    logger.info("Agent graph built successfully (Cold-Start mode)")
    return graph


def build_enhanced_agent_graph(config: AgentConfig) -> StateGraph:
    """
    Build enhanced agent graph with feedback analysis.

    Enhanced Mode (requires historical feedback):
    ```
    START
      │
      ▼
    analyze_preferences
      │
      ├─[has feedback]─► generate_query ─┐
      │                                   │
      └─[no feedback]─────────────────────►build_profile
                                                │
                                                ▼
                                          score_papers
                                                │
                                                ▼
                                          validate_ranking
                                                │
                                          ┌─[rerank]────┤
                                          │             │
                                          ▼             ▼
                                    score_papers       END
    ```

    Args:
        config: AgentConfig with pipeline settings

    Returns:
        Compiled StateGraph with enhanced capabilities
    """
    logger.info(f"Building enhanced agent graph: model={config.model}")

    builder = StateGraph(AgentState)

    # Add all nodes
    builder.add_node("analyze_preferences", analysis_node)
    builder.add_node("generate_query", query_generation_node)
    builder.add_node("build_profile", build_profile_node)
    builder.add_node("score_papers", score_papers_node)
    builder.add_node("validate_ranking", validation_node)

    # Define edges with conditions
    builder.add_edge(START, "analyze_preferences")

    # Conditional: generate query or skip to profile
    builder.add_conditional_edges(
        "analyze_preferences",
        _should_generate_query,
        {
            "generate": "generate_query",
            "skip": "build_profile",
        },
    )

    builder.add_edge("generate_query", "build_profile")
    builder.add_edge("build_profile", "score_papers")
    builder.add_edge("score_papers", "validate_ranking")

    # Conditional: rerank or end
    builder.add_conditional_edges(
        "validate_ranking",
        _should_continue,
        {
            "rerank": "score_papers",
            "end": END,
        },
    )

    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory)

    logger.info("Enhanced agent graph built successfully")
    return graph


def _should_generate_query(state: AgentState) -> Literal["generate", "skip"]:
    """Conditional: whether to generate dynamic query."""
    feedback = state.get("feedback_history", {})
    liked_count = len(feedback.get("liked", []))
    config = state.get("config", {})
    min_feedback = config.get("min_feedback_count", 3)

    interest_analysis = state.get("interest_analysis", {})
    has_interests = bool(interest_analysis.get("main_interests"))

    if liked_count >= min_feedback and has_interests:
        logger.debug(f"Generating query: {liked_count} liked papers")
        return "generate"

    logger.debug(f"Skipping query gen: {liked_count} liked papers")
    return "skip"


def _should_continue(state: AgentState) -> Literal["rerank", "end"]:
    """Conditional: whether to continue re-ranking."""
    should_rerank = state.get("should_rerank", False)
    iteration = state.get("iteration", 0)
    config = state.get("config", {})
    max_iterations = config.get("max_iterations", 2)

    if should_rerank and iteration < max_iterations:
        logger.debug(f"Re-ranking: iteration {iteration}/{max_iterations}")
        return "rerank"

    return "end"


def create_initial_state(
    papers: list,
    feedback_history: dict,
    user_profile: dict | None,
    config: AgentConfig,
) -> AgentState:
    """
    Create initial state for graph invocation.

    Args:
        papers: List of paper dictionaries
        feedback_history: User feedback {liked: [], disliked: []}
        user_profile: User profile dictionary
        config: Agent configuration

    Returns:
        Initial AgentState for Cold-Start mode
    """
    return AgentState(
        papers=papers,
        feedback_history=feedback_history,
        user_profile=user_profile,
        config=config.to_dict(),
        # Cold-Start: interest_profile will be built by build_profile_node
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
