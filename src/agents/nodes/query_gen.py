"""Query generation node - Generates dynamic search queries and keywords."""

import json
import logging
from typing import Any
from collections import Counter

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..state import AgentState
from ..prompts import QUERY_GENERATION_PROMPT
from ...secrets import resolve_secret

logger = logging.getLogger(__name__)


def _resolve_api_key(config: dict) -> str | None:
    """Resolve API key from config or configured environment variable."""
    env_name = config.get("api_key_env") or "OPENAI_API_KEY"
    return resolve_secret(
        value=config.get("api_key"),
        env=env_name,
        file_path=config.get("api_key_file"),
        required=False,
        name="API key",
    )


def _default_headers(config: dict) -> dict[str, str] | None:
    """Provider-specific headers (e.g., OpenRouter recommends these)."""
    if (config.get("provider") or "").lower() != "openrouter":
        return None
    return {
        "HTTP-Referer": "https://github.com/arxiv-paper-bot",
        "X-Title": "arXiv Paper Bot",
    }


def query_generation_node(state: AgentState) -> dict[str, Any]:
    """
    Generate dynamic search query and enhanced keywords.

    This node creates:
    - Synthetic arXiv query based on user interests
    - Enhanced keyword weights for better filtering

    Args:
        state: Current agent state with interest_analysis and papers

    Returns:
        Dictionary with synthetic_query, enhanced_keywords, and messages
    """
    interest_analysis = state.get("interest_analysis", {})
    papers = state.get("papers", [])
    config = state.get("config", {})

    # Extract interests
    main_interests = interest_analysis.get("main_interests", [])
    emerging_interests = interest_analysis.get("emerging_interests", [])
    disliked_topics = interest_analysis.get("disliked_topics", [])

    # If no interests identified, skip query generation
    if not main_interests:
        logger.info("No interests identified, skipping query generation")
        return {
            "synthetic_query": None,
            "enhanced_keywords": None,
            "messages": [
                {"role": "assistant", "content": "Skipped query generation - no interests"}
            ],
        }

    try:
        # Initialize LLM
        api_key = _resolve_api_key(config)
        if not api_key:
            raise ValueError(
                f"API key not found (env={config.get('api_key_env') or 'OPENAI_API_KEY'})"
            )

        llm = ChatOpenAI(
            model=config.get("simple_model") or config.get("model", "gpt-4o"),
            temperature=config.get("temperature", 0.5),  # Slightly higher for creativity
            api_key=api_key,
            base_url=config.get("base_url") or None,
            timeout=config.get("timeout"),
            default_headers=_default_headers(config),
        )

        # Extract current hot topics from papers
        current_hot_topics = _extract_hot_topics(papers)

        # Create prompt
        prompt = ChatPromptTemplate.from_template(QUERY_GENERATION_PROMPT)

        # Invoke LLM
        chain = prompt | llm
        response = chain.invoke(
            {
                "main_interests": ", ".join(main_interests),
                "emerging_interests": ", ".join(emerging_interests)
                if emerging_interests
                else "(None)",
                "disliked_topics": ", ".join(disliked_topics)
                if disliked_topics
                else "(None)",
                "current_hot_topics": ", ".join(current_hot_topics),
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

        synthetic_query = result.get("query", "")
        enhanced_keywords = {
            "high_priority": result.get("high_priority_keywords", []),
            "medium_priority": result.get("medium_priority_keywords", []),
            "negative": result.get("negative_keywords", []),
        }

        logger.info(
            f"Generated query: {synthetic_query[:50]}..., "
            f"enhanced keywords: {len(enhanced_keywords['high_priority'])} high, "
            f"{len(enhanced_keywords['medium_priority'])} medium"
        )

        return {
            "synthetic_query": synthetic_query,
            "enhanced_keywords": enhanced_keywords,
            "messages": [
                {
                    "role": "assistant",
                    "content": f"Generated query and {len(enhanced_keywords['high_priority'])} priority keywords",
                }
            ],
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse query generation response: {e}")
        # Fallback: use interests directly as keywords
        return {
            "synthetic_query": _build_simple_query(main_interests),
            "enhanced_keywords": {
                "high_priority": main_interests[:3],
                "medium_priority": emerging_interests[:3] if emerging_interests else [],
                "negative": disliked_topics[:2] if disliked_topics else [],
            },
            "messages": [
                {"role": "assistant", "content": "Used fallback query generation"}
            ],
        }

    except Exception as e:
        logger.error(f"Query generation node failed: {e}")
        return {
            "synthetic_query": _build_simple_query(main_interests),
            "enhanced_keywords": {
                "high_priority": main_interests[:3],
                "medium_priority": [],
                "negative": [],
            },
            "messages": [
                {"role": "assistant", "content": f"Fallback due to error: {e}"}
            ],
        }


def _extract_hot_topics(papers: list, top_n: int = 10) -> list:
    """Extract hot topics from current papers."""
    all_keywords = []
    for paper in papers[:30]:  # Limit papers to analyze
        all_keywords.extend(paper.get("matched_keywords", []))

    keyword_counts = Counter(all_keywords)
    return [kw for kw, _ in keyword_counts.most_common(top_n)]


def _build_simple_query(interests: list) -> str:
    """Build a simple arXiv query from interests."""
    if not interests:
        return ""

    # Quote multi-word terms
    quoted = []
    for term in interests:
        if " " in term:
            quoted.append(f'"{term}"')
        else:
            quoted.append(term)

    return " OR ".join(quoted)
