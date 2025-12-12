"""Validation node - Validates ranking and generates explanations."""

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..state import AgentState
from ..prompts import VALIDATION_PROMPT

logger = logging.getLogger(__name__)


def validation_node(state: AgentState) -> dict[str, Any]:
    """
    Validate paper ranking and generate recommendation explanations.

    This node:
    - Reviews the ranking quality
    - Generates explanations for top papers
    - Suggests reordering if needed
    - Decides if another iteration is needed

    Args:
        state: Current agent state with scored_papers

    Returns:
        Dictionary with validated_papers, explanations, and flow control
    """
    scored_papers = state.get("scored_papers", [])
    interest_analysis = state.get("interest_analysis", {})
    config = state.get("config", {})
    iteration = state.get("iteration", 0)

    # If no papers, return empty
    if not scored_papers:
        return {
            "validated_papers": [],
            "explanations": {},
            "should_rerank": False,
            "iteration": iteration + 1,
            "messages": [{"role": "assistant", "content": "No papers to validate"}],
        }

    try:
        # Initialize LLM
        llm = ChatOpenAI(
            model=config.get("model", "gpt-4o"),
            temperature=config.get("temperature", 0.2),  # Lower for consistency
            api_key=config.get("api_key"),
            base_url=config.get("base_url") if config.get("base_url") else None,
        )

        # Prepare top papers for validation
        top_papers = scored_papers[:10]
        papers_text = _format_papers_for_validation(top_papers)

        # Create prompt
        prompt = ChatPromptTemplate.from_template(VALIDATION_PROMPT)

        # Invoke LLM
        chain = prompt | llm
        response = chain.invoke(
            {
                "papers": papers_text,
                "user_interests": ", ".join(
                    interest_analysis.get("main_interests", [])
                ),
                "disliked_topics": ", ".join(
                    interest_analysis.get("disliked_topics", [])
                )
                or "(None)",
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

        result = json.loads(content)

        # Extract validation results
        evaluation_score = result.get("evaluation_score", 0.8)
        confidence = result.get("confidence", 0.7)

        # Build explanations dict
        explanations = {}
        for exp in result.get("explanations", []):
            paper_id = exp.get("paper_id")
            explanation = exp.get("explanation", "")
            if paper_id:
                explanations[paper_id] = explanation

        # Apply suggested reordering if provided
        suggested_reorder = result.get("suggested_reorder")
        if suggested_reorder:
            validated_papers = _apply_reorder(scored_papers, suggested_reorder)
        else:
            validated_papers = scored_papers

        # Decide if we should rerank
        confidence_threshold = config.get("confidence_threshold", 0.7)
        max_iterations = config.get("max_iterations", 2)
        should_rerank = (
            evaluation_score < confidence_threshold and iteration < max_iterations
        )

        logger.info(
            f"Validation complete: score={evaluation_score:.2f}, "
            f"confidence={confidence:.2f}, should_rerank={should_rerank}"
        )

        return {
            "validated_papers": validated_papers,
            "explanations": explanations,
            "should_rerank": should_rerank,
            "iteration": iteration + 1,
            "messages": [
                {
                    "role": "assistant",
                    "content": f"Validated {len(top_papers)} papers, "
                    f"evaluation={evaluation_score:.2f}",
                }
            ],
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse validation response: {e}")
        return _fallback_validation(scored_papers, iteration)

    except Exception as e:
        logger.error(f"Validation node failed: {e}")
        return _fallback_validation(scored_papers, iteration)


def _format_papers_for_validation(papers: list) -> str:
    """Format papers for validation prompt."""
    lines = []
    for i, paper in enumerate(papers, 1):
        lines.append(
            f"{i}. [{paper.get('arxiv_id', 'N/A')}] {paper.get('title', 'Unknown')}\n"
            f"   Score: {paper.get('score', 0):.2f}, "
            f"Keywords: {', '.join(paper.get('matched_keywords', []))}"
        )
    return "\n".join(lines)


def _apply_reorder(papers: list, order: list) -> list:
    """Apply suggested reordering to papers."""
    if not order:
        return papers

    # Create lookup
    paper_lookup = {p.get("arxiv_id"): p for p in papers}

    # Build reordered list
    reordered = []
    seen = set()

    for paper_id in order:
        if paper_id in paper_lookup and paper_id not in seen:
            reordered.append(paper_lookup[paper_id])
            seen.add(paper_id)

    # Add remaining papers that weren't in the reorder list
    for paper in papers:
        if paper.get("arxiv_id") not in seen:
            reordered.append(paper)

    return reordered


def _fallback_validation(papers: list, iteration: int) -> dict[str, Any]:
    """Fallback validation when LLM fails."""
    # Generate simple explanations based on keywords
    explanations = {}
    for paper in papers[:5]:
        paper_id = paper.get("arxiv_id")
        keywords = paper.get("matched_keywords", [])
        if paper_id and keywords:
            explanations[paper_id] = (
                f"Recommended based on matching keywords: {', '.join(keywords[:3])}"
            )

    return {
        "validated_papers": papers,
        "explanations": explanations,
        "should_rerank": False,
        "iteration": iteration + 1,
        "messages": [{"role": "assistant", "content": "Used fallback validation"}],
    }
