"""Analysis node - Analyzes user preferences from feedback history."""

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..state import AgentState
from ..prompts import ANALYSIS_PROMPT

logger = logging.getLogger(__name__)


def analysis_node(state: AgentState) -> dict[str, Any]:
    """
    Analyze user preferences based on feedback history.

    This node examines liked and disliked papers to identify:
    - Main research interests
    - Emerging interests
    - Topics to avoid

    Args:
        state: Current agent state with feedback_history

    Returns:
        Dictionary with interest_analysis and messages
    """
    feedback = state.get("feedback_history", {})
    liked_papers = feedback.get("liked", [])
    disliked_papers = feedback.get("disliked", [])
    config = state.get("config", {})

    # If no feedback history, return empty analysis
    if not liked_papers:
        logger.info("No liked papers found, returning empty analysis")
        return {
            "interest_analysis": {
                "main_interests": [],
                "emerging_interests": [],
                "disliked_topics": [],
                "confidence": 0.0,
            },
            "messages": [
                {
                    "role": "assistant",
                    "content": "No feedback history available for analysis",
                }
            ],
        }

    try:
        # Initialize LLM
        llm = ChatOpenAI(
            model=config.get("model", "gpt-4o"),
            temperature=config.get("temperature", 0.3),
            api_key=config.get("api_key"),
            base_url=config.get("base_url") if config.get("base_url") else None,
        )

        # Prepare input for prompt
        liked_summaries = "\n".join(
            [
                f"- {p.get('title', 'Unknown')}: keywords={p.get('matched_keywords', [])}"
                for p in liked_papers[:10]  # Limit to 10 papers
            ]
        )

        disliked_summaries = "\n".join(
            [f"- {p.get('title', 'Unknown')}" for p in disliked_papers[:5]]
        )

        if not disliked_summaries:
            disliked_summaries = "(None)"

        # Create prompt
        prompt = ChatPromptTemplate.from_template(ANALYSIS_PROMPT)

        # Invoke LLM
        chain = prompt | llm
        response = chain.invoke(
            {
                "liked_papers": liked_summaries,
                "disliked_papers": disliked_summaries,
                "paper_count": len(liked_papers),
            }
        )

        # Parse response
        content = response.content.strip()
        # Remove markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        interest_analysis = json.loads(content)

        logger.info(
            f"Analyzed {len(liked_papers)} liked papers, "
            f"found {len(interest_analysis.get('main_interests', []))} main interests"
        )

        return {
            "interest_analysis": interest_analysis,
            "messages": [
                {
                    "role": "assistant",
                    "content": f"Analyzed {len(liked_papers)} papers. "
                    f"Main interests: {interest_analysis.get('main_interests', [])}",
                }
            ],
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        return {
            "interest_analysis": {
                "main_interests": _extract_keywords_from_feedback(liked_papers),
                "emerging_interests": [],
                "disliked_topics": [],
                "confidence": 0.3,
            },
            "messages": [
                {"role": "assistant", "content": f"Fallback analysis due to parse error"}
            ],
        }

    except Exception as e:
        logger.error(f"Analysis node failed: {e}")
        # Fallback: extract keywords from liked papers
        return {
            "interest_analysis": {
                "main_interests": _extract_keywords_from_feedback(liked_papers),
                "emerging_interests": [],
                "disliked_topics": [],
                "confidence": 0.2,
            },
            "messages": [
                {"role": "assistant", "content": f"Fallback analysis due to error: {e}"}
            ],
        }


def _extract_keywords_from_feedback(liked_papers: list) -> list:
    """Extract top keywords from liked papers as fallback."""
    from collections import Counter

    all_keywords = []
    for paper in liked_papers:
        all_keywords.extend(paper.get("matched_keywords", []))

    # Return top 5 most common keywords
    keyword_counts = Counter(all_keywords)
    return [kw for kw, _ in keyword_counts.most_common(5)]
