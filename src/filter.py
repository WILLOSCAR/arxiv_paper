"""Paper filtering and ranking module based on keywords."""

import logging
import re
from typing import List, Dict

from .models import Paper, FilterConfig

logger = logging.getLogger(__name__)


class PaperFilter:
    """Filters and ranks papers based on keyword matching."""

    def __init__(self, config: FilterConfig):
        """
        Initialize the filter with configuration.

        Args:
            config: FilterConfig object with filtering parameters
        """
        self.config = config
        self.keyword_weights = self._build_keyword_weights()

    def _build_keyword_weights(self) -> Dict[str, float]:
        """
        Build a dictionary mapping keywords to their weights.

        Returns:
            Dictionary mapping keywords (lowercase) to weights
        """
        weights = {}

        # High priority keywords (weight: 3.0)
        for keyword in self.config.keywords.get("high_priority", []):
            weights[keyword.lower()] = 3.0

        # Medium priority keywords (weight: 2.0)
        for keyword in self.config.keywords.get("medium_priority", []):
            weights[keyword.lower()] = 2.0

        # Low priority keywords (weight: 1.0)
        for keyword in self.config.keywords.get("low_priority", []):
            weights[keyword.lower()] = 1.0

        logger.info(f"Built keyword weights: {len(weights)} keywords")
        return weights

    def filter_and_rank(self, papers: List[Paper]) -> List[Paper]:
        """
        Filter and rank papers based on keyword matching.

        Args:
            papers: List of Paper objects to filter and rank

        Returns:
            List of filtered and ranked Paper objects (sorted by score descending)
        """
        if not self.config.enabled:
            logger.info("Filtering disabled, returning all papers")
            return papers

        # Score each paper
        for paper in papers:
            score, matched = self._score_paper(paper)
            paper.score = score
            paper.matched_keywords = matched

        # Filter by minimum score
        filtered = [
            p for p in papers if p.score >= self.config.min_score
        ]

        logger.info(
            f"Filtered {len(filtered)}/{len(papers)} papers "
            f"(min_score={self.config.min_score})"
        )

        # Sort by score (descending)
        ranked = sorted(filtered, key=lambda p: p.score, reverse=True)

        # Keep only top_k papers
        if self.config.top_k and len(ranked) > self.config.top_k:
            ranked = ranked[: self.config.top_k]
            logger.info(f"Keeping top {self.config.top_k} papers")

        return ranked

    def _score_paper(self, paper: Paper) -> tuple[float, List[str]]:
        """
        Calculate relevance score for a paper based on keyword matching.

        Args:
            paper: Paper object to score

        Returns:
            Tuple of (score, list of matched keywords)
        """
        # Combine title and abstract for matching
        text = f"{paper.title} {paper.abstract}".lower()

        score = 0.0
        matched_keywords = []

        for keyword, weight in self.keyword_weights.items():
            # Use word boundary regex for better matching
            pattern = r"\b" + re.escape(keyword) + r"\b"

            if re.search(pattern, text):
                score += weight
                matched_keywords.append(keyword)

        return score, matched_keywords

    def get_statistics(self, papers: List[Paper]) -> Dict:
        """
        Calculate statistics about the filtered papers.

        Args:
            papers: List of filtered Paper objects

        Returns:
            Dictionary with statistics
        """
        if not papers:
            return {
                "total_papers": 0,
                "avg_score": 0.0,
                "max_score": 0.0,
                "min_score": 0.0,
            }

        scores = [p.score for p in papers]

        # Count keyword occurrences
        keyword_counts = {}
        for paper in papers:
            for kw in paper.matched_keywords:
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

        # Sort keywords by frequency
        top_keywords = sorted(
            keyword_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        return {
            "total_papers": len(papers),
            "avg_score": sum(scores) / len(scores),
            "max_score": max(scores),
            "min_score": min(scores),
            "top_keywords": top_keywords,
        }


class DynamicFilter(PaperFilter):
    """
    Extended filter with preference learning (placeholder for future implementation).

    This class can be extended to include:
    - User feedback processing
    - Preference vector updates
    - Personalized ranking based on historical interactions
    """

    def __init__(self, config: FilterConfig):
        super().__init__(config)
        # Placeholder for preference model
        self.preference_vector = None

    def update_preferences(self, paper_id: str, feedback: str):
        """
        Update preference model based on user feedback.

        Args:
            paper_id: arXiv ID of the paper
            feedback: "like" or "dislike"
        """
        # TODO: Implement preference learning
        logger.info(f"Received feedback for {paper_id}: {feedback}")
        pass

    def load_preference_model(self, path: str):
        """Load a saved preference model."""
        # TODO: Implement model loading
        pass

    def save_preference_model(self, path: str):
        """Save the current preference model."""
        # TODO: Implement model saving
        pass
