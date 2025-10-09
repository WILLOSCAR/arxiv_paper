"""Tests for paper filtering and ranking."""

import unittest
from datetime import datetime

from src.filter import PaperFilter
from src.models import Paper, FilterConfig


class TestPaperFilter(unittest.TestCase):
    """Test PaperFilter class."""

    def setUp(self):
        """Set up test data."""
        # Create test papers
        self.papers = [
            Paper(
                arxiv_id="2501.001",
                title="Transformer Networks for Image Recognition",
                abstract="We propose a novel transformer architecture for computer vision tasks.",
                authors=["Alice"],
                primary_category="cs.CV",
                categories=["cs.CV"],
                pdf_url="https://arxiv.org/pdf/2501.001",
                entry_url="https://arxiv.org/abs/2501.001",
                published=datetime(2025, 1, 1),
                updated=datetime(2025, 1, 1),
            ),
            Paper(
                arxiv_id="2501.002",
                title="Diffusion Models for Image Generation",
                abstract="This paper studies diffusion models and their applications.",
                authors=["Bob"],
                primary_category="cs.CV",
                categories=["cs.CV", "cs.LG"],
                pdf_url="https://arxiv.org/pdf/2501.002",
                entry_url="https://arxiv.org/abs/2501.002",
                published=datetime(2025, 1, 2),
                updated=datetime(2025, 1, 2),
            ),
            Paper(
                arxiv_id="2501.003",
                title="Deep Learning for Object Detection",
                abstract="We present a deep learning approach to object detection in images.",
                authors=["Charlie"],
                primary_category="cs.CV",
                categories=["cs.CV"],
                pdf_url="https://arxiv.org/pdf/2501.003",
                entry_url="https://arxiv.org/abs/2501.003",
                published=datetime(2025, 1, 3),
                updated=datetime(2025, 1, 3),
            ),
            Paper(
                arxiv_id="2501.004",
                title="Unrelated Paper on Database Systems",
                abstract="This discusses database optimization techniques.",
                authors=["Dave"],
                primary_category="cs.DB",
                categories=["cs.DB"],
                pdf_url="https://arxiv.org/pdf/2501.004",
                entry_url="https://arxiv.org/abs/2501.004",
                published=datetime(2025, 1, 4),
                updated=datetime(2025, 1, 4),
            ),
        ]

        # Create filter config
        self.config = FilterConfig(
            enabled=True,
            keywords={
                "high_priority": ["transformer", "diffusion"],
                "medium_priority": ["detection"],
                "low_priority": ["deep learning"],
            },
            min_score=1.0,
            top_k=10,
        )

    def test_keyword_matching(self):
        """Test keyword matching in titles and abstracts."""
        filter = PaperFilter(self.config)
        filtered = filter.filter_and_rank(self.papers)

        # Paper 1: transformer (high=3.0)
        # Paper 2: diffusion (high=3.0)
        # Paper 3: detection + deep learning (medium=2.0 + low=1.0 = 3.0)
        # Paper 4: no keywords (score=0, filtered out)

        self.assertEqual(len(filtered), 3)

        # Check scores
        paper_scores = {p.arxiv_id: p.score for p in filtered}
        self.assertEqual(paper_scores["2501.001"], 3.0)  # transformer
        self.assertEqual(paper_scores["2501.002"], 3.0)  # diffusion
        self.assertEqual(paper_scores["2501.003"], 3.0)  # detection + deep learning

    def test_filtering_disabled(self):
        """Test that disabling filter returns all papers."""
        config = FilterConfig(enabled=False, keywords={})
        filter = PaperFilter(config)
        filtered = filter.filter_and_rank(self.papers)

        self.assertEqual(len(filtered), 4)  # All papers returned

    def test_min_score_threshold(self):
        """Test minimum score threshold filtering."""
        # Set higher threshold
        config = FilterConfig(
            enabled=True,
            keywords={
                "high_priority": ["transformer"],
                "low_priority": ["deep learning"],
            },
            min_score=2.0,  # Only high-priority matches
            top_k=10,
        )

        filter = PaperFilter(config)
        filtered = filter.filter_and_rank(self.papers)

        # Only paper 1 has score >= 2.0
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].arxiv_id, "2501.001")

    def test_top_k_limit(self):
        """Test top_k limiting."""
        config = FilterConfig(
            enabled=True,
            keywords={
                "low_priority": ["deep learning", "transformer", "diffusion", "detection"],
            },
            min_score=0.5,
            top_k=2,  # Keep only top 2
        )

        filter = PaperFilter(config)
        filtered = filter.filter_and_rank(self.papers)

        self.assertEqual(len(filtered), 2)

    def test_matched_keywords_tracking(self):
        """Test that matched keywords are tracked."""
        filter = PaperFilter(self.config)
        filtered = filter.filter_and_rank(self.papers)

        # Find the transformer paper
        transformer_paper = [p for p in filtered if p.arxiv_id == "2501.001"][0]
        self.assertIn("transformer", transformer_paper.matched_keywords)

        # Find the diffusion paper
        diffusion_paper = [p for p in filtered if p.arxiv_id == "2501.002"][0]
        self.assertIn("diffusion", diffusion_paper.matched_keywords)

    def test_statistics(self):
        """Test statistics generation."""
        filter = PaperFilter(self.config)
        filtered = filter.filter_and_rank(self.papers)
        stats = filter.get_statistics(filtered)

        self.assertEqual(stats["total_papers"], 3)
        self.assertGreater(stats["avg_score"], 0)
        self.assertGreater(stats["max_score"], 0)
        self.assertIn("top_keywords", stats)


if __name__ == "__main__":
    unittest.main()
