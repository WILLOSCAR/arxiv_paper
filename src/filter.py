"""Paper filtering and ranking module based on keywords."""

import logging
import math
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

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
    Extended filter with lightweight preference learning (feedback-aware).

    This class can be extended to include:
    - User feedback processing
    - Preference vector updates (implemented as keyword counters)
    - Personalized ranking based on historical interactions (implemented as weight adjustments)
    """

    def __init__(self, config: FilterConfig):
        super().__init__(config)
        # Simple preference model: keyword -> like/dislike counts.
        # This is intentionally lightweight and file-serializable.
        self.preference_vector: dict[str, Counter[str]] = {
            "liked": Counter(),
            "disliked": Counter(),
        }

        # Default persistence location (can be overridden via save/load_preference_model).
        self._default_model_path = Path("data") / "feedback" / "preference_model.json"

        # Tuning knobs (kept conservative; can be extended to config later).
        self._like_boost = 1.0
        self._dislike_penalty = 1.5

    def update_preferences(self, paper_id: str, feedback: str):
        """
        Update preference model based on user feedback.

        Args:
            paper_id: arXiv ID of the paper
            feedback: "like" or "dislike"
        """
        feedback = (feedback or "").strip().lower()
        if feedback not in {"like", "dislike"}:
            raise ValueError("feedback must be 'like' or 'dislike'")

        # Best-effort: load paper metadata from the most recent output if available.
        # This avoids changing the public API while still making the method usable.
        keywords: list[str] = []
        try:
            papers_path = Path("data") / "papers.json"
            if papers_path.exists():
                items = json.loads(papers_path.read_text(encoding="utf-8") or "[]")
                for item in items:
                    if str(item.get("arxiv_id")) == str(paper_id):
                        kws = item.get("matched_keywords") or []
                        if isinstance(kws, list):
                            keywords = [str(k).lower() for k in kws if k]
                        break
        except Exception:
            # Never fail on preference update due to file parsing issues.
            keywords = []

        if not keywords:
            logger.info("Preference update: no keywords found for paper %s (skipped)", paper_id)
            return

        bucket = "liked" if feedback == "like" else "disliked"
        self.preference_vector[bucket].update(keywords)
        logger.info("Updated preferences: %s (+%s keywords)", feedback, len(keywords))

        # Persist best-effort so dynamic ranking can pick it up across runs.
        try:
            self.save_preference_model(str(self._default_model_path))
        except Exception:
            # Keep feedback updates non-fatal.
            logger.debug("Failed to persist preference model (ignored)", exc_info=True)

    def filter_and_rank(
        self, papers: List[Paper], context: Optional[dict] = None
    ) -> List[Paper]:
        """
        Filter and rank papers using keyword matching + lightweight preference learning.

        The Orchestrator passes `context` containing feedback history:
          context = {"feedback": {"liked": [...], "disliked": [...]}, "profile": ...}

        Behavior:
        - Starts from the configured keyword weights.
        - Boosts keywords frequently appearing in liked papers.
        - Penalizes keywords frequently appearing in disliked papers.
        - Works even without any feedback (falls back to base PaperFilter behavior).
        """
        if not self.config.enabled:
            logger.info("Filtering disabled, returning all papers")
            return papers

        # Refresh preference counts from context (best-effort).
        try:
            fb = (context or {}).get("feedback") or {}
            liked = fb.get("liked") or []
            disliked = fb.get("disliked") or []
            if isinstance(liked, list):
                self.preference_vector["liked"] = Counter(
                    _iter_feedback_keywords(liked)
                )
            if isinstance(disliked, list):
                self.preference_vector["disliked"] = Counter(
                    _iter_feedback_keywords(disliked)
                )
        except Exception:
            logger.debug("Failed to build preference vector from context (ignored)", exc_info=True)

        adjusted_weights = self._build_adjusted_weights()

        # Score each paper with adjusted weights.
        for paper in papers:
            score, matched = self._score_paper_with_weights(paper, adjusted_weights)
            paper.score = score
            paper.matched_keywords = matched

        # Filter by minimum score
        filtered = [p for p in papers if p.score >= self.config.min_score]

        logger.info(
            "DynamicFilter kept %s/%s papers (min_score=%s, likes=%s, dislikes=%s)",
            len(filtered),
            len(papers),
            self.config.min_score,
            sum(self.preference_vector["liked"].values()),
            sum(self.preference_vector["disliked"].values()),
        )

        ranked = sorted(filtered, key=lambda p: p.score, reverse=True)

        if self.config.top_k and len(ranked) > self.config.top_k:
            ranked = ranked[: self.config.top_k]
            logger.info("Keeping top %s papers", self.config.top_k)

        return ranked

    def _build_adjusted_weights(self) -> Dict[str, float]:
        """Return keyword->weight after applying feedback-based adjustments."""
        adjusted: Dict[str, float] = dict(self.keyword_weights)

        liked = self.preference_vector.get("liked") or Counter()
        disliked = self.preference_vector.get("disliked") or Counter()

        # Apply adjustments to keywords already in config.
        for kw, base in list(adjusted.items()):
            lc = liked.get(kw, 0)
            dc = disliked.get(kw, 0)
            delta = self._like_boost * math.log1p(lc) - self._dislike_penalty * math.log1p(dc)
            adjusted[kw] = max(0.0, base + delta)

        # Add "learned" keywords from feedback (only if they look reasonable).
        # These can help when liked papers contain terms not pre-configured.
        for kw, lc in liked.most_common(30):
            if kw in adjusted:
                continue
            if not kw or len(kw) < 3:
                continue
            # Treat learned keywords as medium-ish by default, scaled by frequency.
            adjusted[kw] = max(0.0, 1.5 + self._like_boost * math.log1p(lc))

        # Penalize learned keywords seen in dislikes (even if not in config).
        for kw, dc in disliked.items():
            if kw not in adjusted:
                continue
            adjusted[kw] = max(0.0, adjusted[kw] - self._dislike_penalty * math.log1p(dc))

        return adjusted

    def _score_paper_with_weights(self, paper: Paper, weights: Dict[str, float]) -> tuple[float, List[str]]:
        """Score a paper with provided weights using the same matching rules as PaperFilter."""
        text = f"{paper.title} {paper.abstract}".lower()

        score = 0.0
        matched_keywords: list[str] = []

        for keyword, weight in weights.items():
            if weight <= 0:
                continue
            if _match_keyword(keyword, text):
                score += float(weight)
                matched_keywords.append(keyword)

        return score, matched_keywords

    def load_preference_model(self, path: str):
        """Load a saved preference model."""
        p = Path(path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        liked = raw.get("liked") or {}
        disliked = raw.get("disliked") or {}

        if not isinstance(liked, dict) or not isinstance(disliked, dict):
            raise ValueError("Invalid preference model format")

        self.preference_vector["liked"] = Counter({str(k): int(v) for k, v in liked.items() if k})
        self.preference_vector["disliked"] = Counter({str(k): int(v) for k, v in disliked.items() if k})

    def save_preference_model(self, path: str):
        """Save the current preference model."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "liked": dict(self.preference_vector.get("liked") or {}),
            "disliked": dict(self.preference_vector.get("disliked") or {}),
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _iter_feedback_keywords(items: list[dict]) -> list[str]:
    """Extract matched_keywords from FeedbackCollector entries (best-effort)."""
    out: list[str] = []
    for it in items:
        kws = it.get("matched_keywords") or []
        if isinstance(kws, list):
            out.extend([str(k).lower() for k in kws if k])
    return out


def _match_keyword(keyword: str, text: str) -> bool:
    """Match keyword against text with word boundaries for single tokens and substring for phrases."""
    kw = (keyword or "").strip().lower()
    if not kw:
        return False
    if " " in kw or "-" in kw or "+" in kw:
        return kw in text
    pattern = r"\b" + re.escape(kw) + r"\b"
    return bool(re.search(pattern, text))
