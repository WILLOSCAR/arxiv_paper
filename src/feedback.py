"""User feedback collection and management (预留接口)."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FeedbackCollector:
    """
    收集和管理用户对论文的反馈.

    功能:
    - 记录 like/dislike/skip
    - 统计用户偏好关键词
    - 构建用户画像

    状态: 🔲 预留接口，部分实现
    """

    def __init__(self, feedback_dir: str = "data/feedback"):
        """
        Initialize feedback collector.

        Args:
            feedback_dir: Directory to store feedback data
        """
        self.feedback_dir = Path(feedback_dir)
        self.feedback_dir.mkdir(parents=True, exist_ok=True)

        self.liked_file = self.feedback_dir / "liked_papers.json"
        self.disliked_file = self.feedback_dir / "disliked_papers.json"
        self.profile_file = self.feedback_dir / "user_profile.json"

    def record_feedback(
        self,
        paper_id: str,
        feedback_type: str,
        paper_data: Optional[dict] = None,
    ) -> None:
        """
        Record user feedback for a paper.

        Args:
            paper_id: arXiv ID of the paper
            feedback_type: "like" or "dislike"
            paper_data: Optional paper metadata (title, keywords, etc.)
        """
        if feedback_type not in ["like", "dislike"]:
            raise ValueError(f"Invalid feedback type: {feedback_type}")

        # Load existing feedback
        feedback_file = (
            self.liked_file if feedback_type == "like" else self.disliked_file
        )

        if feedback_file.exists():
            with open(feedback_file, "r", encoding="utf-8") as f:
                feedback_list = json.load(f)
        else:
            feedback_list = []

        # Add new feedback
        feedback_entry = {
            "paper_id": paper_id,
            "feedback_type": feedback_type,
            "timestamp": datetime.now().isoformat(),
        }

        if paper_data:
            feedback_entry.update(paper_data)

        feedback_list.append(feedback_entry)

        # Save
        with open(feedback_file, "w", encoding="utf-8") as f:
            json.dump(feedback_list, f, indent=2, ensure_ascii=False)

        logger.info(f"Recorded {feedback_type} for paper {paper_id}")

        # Update user profile
        self._update_user_profile()

    def get_liked_papers(self) -> List[dict]:
        """
        Get all liked papers.

        Returns:
            List of liked paper metadata
        """
        if not self.liked_file.exists():
            return []

        with open(self.liked_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_disliked_papers(self) -> List[dict]:
        """Get all disliked papers."""
        if not self.disliked_file.exists():
            return []

        with open(self.disliked_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_user_keywords(self) -> Dict[str, int]:
        """
        Analyze user's preferred keywords from liked papers.

        Returns:
            Dictionary mapping keywords to frequency
        """
        liked_papers = self.get_liked_papers()

        keyword_freq = {}
        for paper in liked_papers:
            keywords = paper.get("matched_keywords", [])
            for kw in keywords:
                keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

        return dict(sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True))

    def get_statistics(self) -> Dict:
        """
        Get user feedback statistics.

        Returns:
            Statistics dictionary
        """
        liked = self.get_liked_papers()
        disliked = self.get_disliked_papers()

        return {
            "total_liked": len(liked),
            "total_disliked": len(disliked),
            "top_keywords": list(self.get_user_keywords().items())[:10],
            "feedback_ratio": (
                len(liked) / (len(liked) + len(disliked))
                if (len(liked) + len(disliked)) > 0
                else 0
            ),
        }

    def _update_user_profile(self):
        """Update user profile based on feedback history."""
        stats = self.get_statistics()
        keywords = self.get_user_keywords()

        profile = {
            "updated_at": datetime.now().isoformat(),
            "statistics": stats,
            "preferred_keywords": keywords,
        }

        with open(self.profile_file, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)

    def clear_feedback(self, feedback_type: Optional[str] = None):
        """
        Clear feedback data.

        Args:
            feedback_type: "like", "dislike", or None (clear all)
        """
        if feedback_type in [None, "like"] and self.liked_file.exists():
            self.liked_file.unlink()
            logger.info("Cleared liked papers")

        if feedback_type in [None, "dislike"] and self.disliked_file.exists():
            self.disliked_file.unlink()
            logger.info("Cleared disliked papers")
