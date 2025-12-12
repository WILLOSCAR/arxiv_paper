"""LangGraph Agent state definition."""

from typing import TypedDict, List, Optional, Annotated
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Shared state for LangGraph Agent Pipeline.

    This state flows through all nodes in the agent graph,
    accumulating results from each processing step.

    Supports Cold-Start mode: works without historical feedback
    by using config keywords as the interest profile source.
    """

    # ===== Input Data =====
    papers: List[dict]
    """List of paper dictionaries from ArxivFetcher"""

    feedback_history: dict
    """User feedback history: {"liked": [...], "disliked": [...]}"""

    user_profile: Optional[dict]
    """User profile from FeedbackCollector (preferred keywords, stats, etc.)"""

    config: dict
    """Agent configuration parameters"""

    # ===== Interest Profile (Cold-Start compatible) =====
    interest_profile: Optional[dict]
    """
    Interest profile built from config keywords + optional feedback.
    This is the primary source for Cold-Start mode.
    {
        "main_interests": ["transformer", "multimodal"],
        "secondary_interests": ["detection", "classification"],
        "general_interests": ["deep learning"],
        "avoid_topics": [],
        "source": "config" | "config+feedback",
        "confidence": 0.7
    }
    """

    # ===== Analysis Results (from AnalysisAgent - legacy) =====
    interest_analysis: Optional[dict]
    """
    User interest analysis result (legacy, used when feedback available):
    {
        "main_interests": ["transformer", "multimodal"],
        "emerging_interests": ["diffusion"],
        "disliked_topics": ["reinforcement learning"],
        "confidence": 0.85
    }
    """

    # ===== Query Generation Results (from QueryGenAgent) =====
    synthetic_query: Optional[str]
    """Generated arXiv query string, e.g., "(transformer OR CLIP) AND vision" """

    enhanced_keywords: Optional[dict]
    """
    Enhanced keyword weights:
    {
        "high_priority": ["CLIP", "vision-language"],
        "medium_priority": ["attention"],
        "negative": ["game", "robotics"]
    }
    """

    # ===== Scoring Results =====
    scored_papers: List[dict]
    """Papers with computed scores"""

    # ===== Validation Results (from ValidationAgent) =====
    validated_papers: List[dict]
    """Final ranked papers after validation"""

    explanations: Optional[dict]
    """Recommendation explanations: {paper_id: "explanation text"}"""

    # ===== Message History =====
    messages: Annotated[list, add_messages]
    """Message history for agent communication"""

    # ===== Flow Control =====
    iteration: int
    """Current iteration count for re-ranking loop"""

    should_rerank: bool
    """Flag indicating if re-ranking is needed"""
