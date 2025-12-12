"""AgentFilter - LangGraph-enhanced paper filtering (Cold-Start compatible)."""

import logging
from typing import List, Optional
import uuid

from ..models import Paper, FilterConfig
from ..filter import PaperFilter
from ..agents import AgentConfig, build_agent_graph
from ..agents.graph import create_initial_state

logger = logging.getLogger(__name__)


class AgentFilter(PaperFilter):
    """
    LangGraph-enhanced paper filter with Cold-Start support.

    This filter works without requiring historical feedback by using
    config keywords as the interest profile source.

    Features:
    - Cold-Start mode: Works on first use without feedback history
    - Config-driven interests: Uses filter keywords as interest profile
    - Optional feedback enhancement: Merges feedback when available
    - Graceful degradation: Falls back to base filter on errors

    Extends PaperFilter with agent-based:
    - Interest profile building (from config)
    - Personalized scoring
    - Recommendation explanations
    """

    def __init__(self, filter_config: FilterConfig, agent_config: dict):
        """
        Initialize AgentFilter.

        Args:
            filter_config: Base filter configuration (provides keywords)
            agent_config: Agent pipeline configuration
        """
        super().__init__(filter_config)

        self.agent_config = AgentConfig.from_dict(agent_config)
        self._agent_graph = None  # Lazy initialization
        self._explanations: dict = {}
        self._last_profile: Optional[dict] = None

        # Merge filter keywords into agent config for Cold-Start
        if not agent_config.get("keywords"):
            self.agent_config.keywords = filter_config.keywords

        logger.info(
            f"AgentFilter initialized: Cold-Start enabled, "
            f"model={self.agent_config.model}"
        )

    def _ensure_graph(self):
        """Ensure agent graph is initialized."""
        if self._agent_graph is None:
            logger.info("Initializing agent graph...")
            try:
                # Set API key in config
                self.agent_config.api_key = self.agent_config.get_api_key()
                self._agent_graph = build_agent_graph(self.agent_config)
                logger.info("Agent graph initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize agent graph: {e}")
                raise

    def filter_and_rank(
        self, papers: List[Paper], context: Optional[dict] = None
    ) -> List[Paper]:
        """
        Filter and rank papers using agent pipeline (Cold-Start mode).

        Unlike the previous version, this method does NOT require
        historical feedback to activate the agent. It works on first use.

        Args:
            papers: List of Paper objects to filter
            context: Optional context with feedback and profile data

        Returns:
            Filtered and ranked list of Paper objects
        """
        # First, apply base filtering
        base_filtered = super().filter_and_rank(papers)

        if not base_filtered:
            logger.info("No papers after base filtering")
            return base_filtered

        # Initialize agent graph
        try:
            self._ensure_graph()
        except Exception as e:
            logger.error(f"Agent graph initialization failed: {e}")
            return base_filtered

        # Convert papers to dict format for agent
        papers_dict = [p.to_dict() for p in base_filtered]

        # Build context (can be empty for Cold-Start)
        if context is None:
            context = {"feedback": {"liked": [], "disliked": []}, "profile": None}

        # Create initial state with config keywords
        initial_state = create_initial_state(
            papers=papers_dict,
            feedback_history=context.get("feedback", {}),
            user_profile=context.get("profile"),
            config=self.agent_config,
        )

        # Add keywords to config for profile building
        initial_state["config"]["keywords"] = self.config.keywords

        # Execute agent pipeline
        try:
            logger.info(f"Executing agent pipeline for {len(papers_dict)} papers")

            # Generate unique thread ID for this invocation
            thread_id = str(uuid.uuid4())

            result = self._agent_graph.invoke(
                initial_state,
                config={
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": 50,
                },
            )

            # Store results
            self._explanations = result.get("explanations", {})
            self._last_profile = result.get("interest_profile")

            # Log profile info
            if self._last_profile:
                logger.info(
                    f"Profile built: source={self._last_profile.get('source')}, "
                    f"interests={len(self._last_profile.get('main_interests', []))}"
                )

            # Convert back to Paper objects
            validated_papers = result.get("validated_papers", [])
            if validated_papers:
                return self._convert_to_papers(validated_papers, base_filtered)
            else:
                # Fall back to scored_papers if validation didn't produce results
                scored_papers = result.get("scored_papers", [])
                if scored_papers:
                    return self._convert_to_papers(scored_papers, base_filtered)
                logger.warning("Agent returned no papers, using base filter")
                return base_filtered

        except Exception as e:
            logger.error(f"Agent pipeline failed: {e}")
            return base_filtered

    def _convert_to_papers(
        self, paper_dicts: List[dict], original_papers: List[Paper]
    ) -> List[Paper]:
        """
        Convert paper dictionaries back to Paper objects.

        Preserves original Paper objects while updating scores and order.

        Args:
            paper_dicts: List of paper dictionaries from agent
            original_papers: Original Paper objects for reference

        Returns:
            List of Paper objects in new order with updated scores
        """
        # Create lookup from original papers
        paper_lookup = {p.arxiv_id: p for p in original_papers}

        result = []
        for paper_dict in paper_dicts:
            arxiv_id = paper_dict.get("arxiv_id")
            if arxiv_id and arxiv_id in paper_lookup:
                paper = paper_lookup[arxiv_id]
                # Update score if agent modified it
                if "score" in paper_dict:
                    paper.score = paper_dict["score"]
                # Store agent score separately
                if "agent_score" in paper_dict:
                    paper.personalized_score = paper_dict.get("combined_score")
                result.append(paper)
            else:
                logger.warning(f"Paper {arxiv_id} not found in original list")

        # Add any remaining papers that weren't in agent output
        seen_ids = {p.arxiv_id for p in result}
        for paper in original_papers:
            if paper.arxiv_id not in seen_ids:
                result.append(paper)

        return result

    def get_explanations(self) -> dict:
        """Get recommendation explanations from last run."""
        return self._explanations

    def get_last_profile(self) -> Optional[dict]:
        """Get the last interest profile (Cold-Start compatible)."""
        return self._last_profile

    def get_statistics(self, papers: List[Paper]) -> dict:
        """
        Get extended statistics including agent info.

        Args:
            papers: List of filtered Paper objects

        Returns:
            Statistics dictionary with agent information
        """
        base_stats = super().get_statistics(papers)

        # Add agent-specific stats
        base_stats["agent_enabled"] = True
        base_stats["cold_start_mode"] = True
        base_stats["explanations_count"] = len(self._explanations)

        if self._last_profile:
            base_stats["profile_source"] = self._last_profile.get("source", "unknown")
            base_stats["detected_interests"] = self._last_profile.get(
                "main_interests", []
            )
            base_stats["profile_confidence"] = self._last_profile.get(
                "confidence", 0.0
            )

        return base_stats
