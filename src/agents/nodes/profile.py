"""Profile builder node - builds interest profile from config keywords."""

import logging
from typing import List

from ..state import AgentState

logger = logging.getLogger(__name__)


def build_profile_node(state: AgentState) -> dict:
    """
    Build interest profile from configuration keywords (Cold-Start mode).

    This node creates an interest profile without requiring historical feedback.
    It uses the keywords from config as the primary source of user interests.

    If historical feedback is available, it merges that information to enhance
    the profile.

    Args:
        state: Current agent state

    Returns:
        dict with interest_profile key
    """
    config = state.get("config", {})
    feedback_history = state.get("feedback_history", {})

    # Build base profile from config keywords
    keywords = config.get("keywords", {})

    profile = {
        "main_interests": keywords.get("high_priority", []),
        "secondary_interests": keywords.get("medium_priority", []),
        "general_interests": keywords.get("low_priority", []),
        "avoid_topics": [],  # Can be extended from config
        "source": "config",
        "confidence": 0.7,  # Base confidence for config-only profile
    }

    logger.info(f"Building profile from config: {len(profile['main_interests'])} main interests")

    # Enhance with historical feedback if available
    liked_papers = feedback_history.get("liked", [])
    disliked_papers = feedback_history.get("disliked", [])

    if liked_papers:
        # Extract topics from liked papers
        liked_topics = _extract_topics_from_papers(liked_papers)
        profile = _merge_interests(profile, liked_topics)
        profile["source"] = "config+feedback"
        profile["confidence"] = min(0.9, 0.7 + 0.05 * len(liked_papers))
        logger.info(f"Enhanced profile with {len(liked_papers)} liked papers")

    if disliked_papers:
        # Extract topics to avoid
        avoid_topics = _extract_topics_from_papers(disliked_papers)
        profile["avoid_topics"] = list(set(profile["avoid_topics"] + avoid_topics))
        logger.info(f"Added {len(avoid_topics)} topics to avoid")

    # Add user profile info if available
    user_profile = state.get("user_profile")
    if user_profile:
        profile["research_areas"] = user_profile.get("research_areas", [])
        profile["preferred_categories"] = user_profile.get("categories", [])

    logger.info(
        f"Profile built: source={profile['source']}, "
        f"confidence={profile['confidence']:.2f}, "
        f"interests={len(profile['main_interests']) + len(profile['secondary_interests'])}"
    )

    return {"interest_profile": profile}


def _extract_topics_from_papers(papers: List[dict]) -> List[str]:
    """
    Extract topic keywords from paper titles and abstracts.

    Args:
        papers: List of paper dictionaries

    Returns:
        List of extracted topic strings
    """
    topics = []

    # Common research keywords to look for
    research_keywords = {
        "transformer", "attention", "diffusion", "generative", "multimodal",
        "vision", "language", "detection", "segmentation", "classification",
        "representation", "contrastive", "self-supervised", "pre-training",
        "fine-tuning", "neural", "deep learning", "reinforcement", "policy",
        "optimization", "embedding", "encoder", "decoder", "latent",
    }

    for paper in papers:
        title = paper.get("title", "").lower()
        abstract = paper.get("abstract", "").lower()
        text = f"{title} {abstract}"

        # Extract matching keywords
        for keyword in research_keywords:
            if keyword in text:
                topics.append(keyword)

        # Extract matched_keywords if available
        matched = paper.get("matched_keywords", [])
        topics.extend(matched)

    # Deduplicate and return
    return list(set(topics))


def _merge_interests(profile: dict, new_topics: List[str]) -> dict:
    """
    Merge new topics into existing profile.

    Args:
        profile: Existing interest profile
        new_topics: New topics to merge

    Returns:
        Updated profile
    """
    existing_main = set(profile.get("main_interests", []))
    existing_secondary = set(profile.get("secondary_interests", []))
    existing_general = set(profile.get("general_interests", []))

    for topic in new_topics:
        topic_lower = topic.lower()

        # If topic appears in liked papers but not in config, promote it
        if topic_lower not in existing_main and topic_lower not in existing_secondary:
            # Add to secondary interests
            existing_secondary.add(topic_lower)

    profile["main_interests"] = list(existing_main)
    profile["secondary_interests"] = list(existing_secondary)
    profile["general_interests"] = list(existing_general)

    return profile
