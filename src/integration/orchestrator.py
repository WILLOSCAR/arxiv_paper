"""Orchestrator - Flow orchestration using strategy pattern."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Protocol

from ..models import Paper, FilterConfig
from ..filter import PaperFilter, DynamicFilter
from ..feedback import FeedbackCollector

logger = logging.getLogger(__name__)


class RankingStrategy(Protocol):
    """Protocol for ranking strategies."""

    def filter_and_rank(
        self, papers: List[Paper], context: Optional[dict] = None
    ) -> List[Paper]:
        """Filter and rank papers."""
        ...

    def get_statistics(self, papers: List[Paper]) -> dict:
        """Get ranking statistics."""
        ...


@dataclass
class OrchestratorConfig:
    """Configuration for Orchestrator."""

    filter_config: FilterConfig
    personalization_config: dict
    mode: str  # "static" | "dynamic" | "agent"

    @classmethod
    def from_dict(cls, config: dict) -> "OrchestratorConfig":
        """Create OrchestratorConfig from dictionary."""
        filter_dict = config.get("filter", {})

        filter_config = FilterConfig(
            enabled=filter_dict.get("enabled", True),
            mode=filter_dict.get("mode", "static"),
            keywords=filter_dict.get("keywords", {}),
            min_score=filter_dict.get("min_score", 0.0),
            top_k=filter_dict.get("top_k", 20),
        )

        personalization_config = config.get("personalization", {})
        mode = filter_dict.get("mode", "static")

        return cls(
            filter_config=filter_config,
            personalization_config=personalization_config,
            mode=mode,
        )


class Orchestrator:
    """
    Flow orchestrator using strategy pattern.

    Selects and executes the appropriate ranking strategy based on configuration:
    - "static": Use PaperFilter (keyword-only matching)
    - "dynamic": Use DynamicFilter (feedback-aware preference learning)
    - "agent": Use AgentFilter (LangGraph-enhanced filtering)
    """

    def __init__(self, config: OrchestratorConfig):
        """
        Initialize orchestrator with configuration.

        Args:
            config: OrchestratorConfig with filter and personalization settings
        """
        self.config = config
        self._strategy: Optional[RankingStrategy] = None
        self._feedback_collector: Optional[FeedbackCollector] = None
        self._explanations: dict = {}

        # Initialize feedback collector
        feedback_config = config.personalization_config.get("feedback", {})
        feedback_dir = feedback_config.get("feedback_dir", "data/feedback")
        self._feedback_collector = FeedbackCollector(feedback_dir)

        # Create strategy based on mode
        self._strategy = self._create_strategy()

    def _create_strategy(self) -> RankingStrategy:
        """Create the appropriate strategy based on configuration."""
        mode = self.config.mode

        if mode == "static":
            logger.info("Using static filter strategy")
            return PaperFilter(self.config.filter_config)

        elif mode == "dynamic":
            logger.info("Using dynamic filter strategy")
            return DynamicFilter(self.config.filter_config)

        elif mode == "agent":
            # Check if agent is enabled
            agent_config = self.config.personalization_config.get("agent", {})
            if agent_config.get("enabled", False):
                logger.info("Using agent filter strategy")
                from .agent_filter import AgentFilter

                return AgentFilter(
                    filter_config=self.config.filter_config,
                    agent_config=agent_config,
                )
            else:
                logger.warning(
                    "Agent mode selected but agent not enabled, falling back to static"
                )
                return PaperFilter(self.config.filter_config)

        else:
            logger.warning(f"Unknown mode '{mode}', using static filter")
            return PaperFilter(self.config.filter_config)

    def process(self, papers: List[Paper]) -> List[Paper]:
        """
        Process papers through the selected strategy.

        Args:
            papers: List of Paper objects from ArxivFetcher

        Returns:
            Filtered and ranked list of Paper objects
        """
        # Build context with feedback data
        context = self._build_context()

        # Execute strategy
        if hasattr(self._strategy, "filter_and_rank"):
            # Check if strategy accepts context
            import inspect

            sig = inspect.signature(self._strategy.filter_and_rank)
            if "context" in sig.parameters:
                result = self._strategy.filter_and_rank(papers, context=context)
            else:
                result = self._strategy.filter_and_rank(papers)
        else:
            result = papers

        # Optional vector-based re-ranking (lightweight hashing fallback if deps missing).
        result = self._maybe_apply_vector_ranking(result, context=context)

        # Store explanations if available
        if hasattr(self._strategy, "get_explanations"):
            self._explanations = self._strategy.get_explanations()

        return result

    def get_statistics(self, papers: List[Paper]) -> dict:
        """
        Get statistics about the filtered papers.

        Args:
            papers: List of filtered Paper objects

        Returns:
            Statistics dictionary
        """
        if hasattr(self._strategy, "get_statistics"):
            stats = self._strategy.get_statistics(papers)
        else:
            stats = {
                "total_papers": len(papers),
                "avg_score": sum(p.score for p in papers) / len(papers)
                if papers
                else 0,
            }

        # Add mode information
        stats["filter_mode"] = self.config.mode

        return stats

    def get_explanations(self) -> dict:
        """Get recommendation explanations (if available from agent mode)."""
        return self._explanations

    def _build_context(self) -> dict:
        """Build context dictionary with feedback and profile data."""
        context = {
            "feedback": {
                "liked": [],
                "disliked": [],
            },
            "profile": None,
        }

        if self._feedback_collector:
            try:
                context["feedback"]["liked"] = self._feedback_collector.get_liked_papers()
                context["feedback"]["disliked"] = (
                    self._feedback_collector.get_disliked_papers()
                )
                context["profile"] = self._load_user_profile()
            except Exception as e:
                logger.warning(f"Failed to load feedback data: {e}")

        return context

    def _load_user_profile(self) -> Optional[dict]:
        """Load user profile from feedback collector."""
        if not self._feedback_collector:
            return None

        profile_path = self._feedback_collector.profile_file
        if profile_path.exists():
            import json

            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load user profile: {e}")

        return None

    def _maybe_apply_vector_ranking(self, papers: List[Paper], *, context: dict) -> List[Paper]:
        vector_cfg = (self.config.personalization_config or {}).get("vector_ranking") or {}
        if not vector_cfg.get("enabled", False):
            return papers

        feedback = (context or {}).get("feedback") or {}
        liked_entries = feedback.get("liked") or []
        if not liked_entries:
            return papers

        try:
            from ..personalization import PersonalizedRanker
        except Exception:
            logger.debug("PersonalizedRanker import failed; skipping vector ranking", exc_info=True)
            return papers

        now = datetime.now(timezone.utc)
        liked_papers: List[Paper] = []
        for entry in liked_entries:
            if not isinstance(entry, dict):
                continue
            pid = entry.get("paper_id") or entry.get("arxiv_id") or ""
            title = entry.get("title") or ""
            abstract = entry.get("abstract") or ""
            cats = entry.get("categories") or []
            if not isinstance(cats, list):
                cats = []
            primary = entry.get("primary_category") or (cats[0] if cats else "")

            if not pid or not title:
                continue

            liked_papers.append(
                Paper(
                    arxiv_id=str(pid),
                    title=str(title),
                    abstract=str(abstract),
                    authors=[],
                    primary_category=str(primary),
                    categories=[str(c) for c in cats if c],
                    pdf_url=str(entry.get("pdf_url") or ""),
                    entry_url=str(entry.get("entry_url") or ""),
                    published=now,
                    updated=now,
                )
            )

        if not liked_papers:
            return papers

        ranker = PersonalizedRanker(
            model_name=str(vector_cfg.get("model") or "allenai/specter"),
            enabled=True,
        )
        weight = float(vector_cfg.get("weight", 0.4))
        try:
            return ranker.rank_by_similarity(papers, liked_papers, weight=weight)
        except Exception:
            logger.debug("Vector ranking failed; skipping", exc_info=True)
            return papers
