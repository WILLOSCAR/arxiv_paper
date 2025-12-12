"""Scoring node - Computes paper relevance scores."""

import logging
import re
from typing import Any

from ..state import AgentState

logger = logging.getLogger(__name__)


def score_papers_node(state: AgentState) -> dict[str, Any]:
    """
    Score papers based on interest profile and enhanced keywords.

    This node combines:
    - Original keyword matching scores
    - Interest profile alignment (from config + optional feedback)
    - Enhanced keyword weights from agent (if available)

    Works in Cold-Start mode: doesn't require historical feedback.

    Args:
        state: Current agent state with papers and interest_profile

    Returns:
        Dictionary with scored_papers and messages
    """
    papers = state.get("papers", [])
    interest_profile = state.get("interest_profile", {})
    enhanced_keywords = state.get("enhanced_keywords")
    config = state.get("config", {})

    # Get weight configuration
    keyword_weight = config.get("keyword_weight", 0.5)
    agent_weight = config.get("agent_weight", 0.5)

    scored_papers = []

    for paper in papers:
        # Original score from PaperFilter
        original_score = paper.get("score", 0.0)

        # Calculate agent score using interest profile
        agent_score = _calculate_profile_score(
            paper, interest_profile, enhanced_keywords
        )

        # Combine scores
        if interest_profile or enhanced_keywords:
            combined_score = (
                original_score * keyword_weight + agent_score * agent_weight * 10
            )  # Scale agent score to match keyword score range
        else:
            combined_score = original_score

        # Create scored paper
        scored_paper = paper.copy()
        scored_paper["original_score"] = original_score
        scored_paper["agent_score"] = agent_score
        scored_paper["combined_score"] = combined_score
        scored_paper["score"] = combined_score  # Override score for ranking

        scored_papers.append(scored_paper)

    # Sort by combined score
    scored_papers.sort(key=lambda p: p.get("score", 0), reverse=True)

    logger.info(
        f"Scored {len(scored_papers)} papers, "
        f"top score: {scored_papers[0]['score']:.2f}" if scored_papers else "no papers"
    )

    return {
        "scored_papers": scored_papers,
        "messages": [
            {"role": "assistant", "content": f"Scored {len(scored_papers)} papers"}
        ],
    }


def _calculate_profile_score(
    paper: dict, interest_profile: dict, enhanced_keywords: dict | None = None
) -> float:
    """
    Calculate relevance score based on interest profile.

    Works with interest_profile from build_profile_node (Cold-Start compatible).

    Args:
        paper: Paper dictionary
        interest_profile: Interest profile from profile node
        enhanced_keywords: Optional enhanced keywords

    Returns:
        Score between 0.0 and 1.0
    """
    if not interest_profile and not enhanced_keywords:
        return 0.0

    score = 0.0
    text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()

    # Score based on interest profile
    if interest_profile:
        # Main interests: +0.3 each (max 0.9)
        for interest in interest_profile.get("main_interests", []):
            if _keyword_matches(interest.lower(), text):
                score += 0.3

        # Secondary interests: +0.15 each (max 0.45)
        for interest in interest_profile.get("secondary_interests", []):
            if _keyword_matches(interest.lower(), text):
                score += 0.15

        # General interests: +0.05 each (max 0.15)
        for interest in interest_profile.get("general_interests", []):
            if _keyword_matches(interest.lower(), text):
                score += 0.05

        # Avoid topics: -0.3 each
        for topic in interest_profile.get("avoid_topics", []):
            if _keyword_matches(topic.lower(), text):
                score -= 0.3

    # Additional scoring from enhanced keywords (if available)
    if enhanced_keywords:
        # High priority keywords: +0.2 each
        for kw in enhanced_keywords.get("high_priority", []):
            if _keyword_matches(kw.lower(), text):
                score += 0.2

        # Medium priority keywords: +0.1 each
        for kw in enhanced_keywords.get("medium_priority", []):
            if _keyword_matches(kw.lower(), text):
                score += 0.1

        # Negative keywords: -0.2 each
        for kw in enhanced_keywords.get("negative", []):
            if _keyword_matches(kw.lower(), text):
                score -= 0.2

    # Clamp score to [0.0, 1.0]
    return max(0.0, min(1.0, score))


# Legacy function for backward compatibility
def _calculate_agent_score(
    paper: dict, enhanced_keywords: dict | None, interest_analysis: dict
) -> float:
    """Legacy: Calculate agent score using interest_analysis."""
    # Convert interest_analysis to interest_profile format
    profile = {
        "main_interests": interest_analysis.get("main_interests", []),
        "secondary_interests": interest_analysis.get("emerging_interests", []),
        "avoid_topics": interest_analysis.get("disliked_topics", []),
    }
    return _calculate_profile_score(paper, profile, enhanced_keywords)


def _keyword_matches(keyword: str, text: str) -> bool:
    """Check if keyword matches in text using word boundary."""
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return bool(re.search(pattern, text, re.IGNORECASE))
