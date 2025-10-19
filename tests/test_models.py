"""Tests for data models."""

import unittest
from datetime import datetime

from src.models import Paper, FetchConfig, FilterConfig


class TestPaper(unittest.TestCase):
    """Test Paper model."""

    def setUp(self):
        """Set up test data."""
        self.paper = Paper(
            arxiv_id="2501.12345",
            title="Test Paper on Transformers",
            abstract="This paper discusses transformer architectures for deep learning.",
            authors=["Alice Smith", "Bob Jones"],
            primary_category="cs.AI",
            categories=["cs.AI", "cs.LG"],
            pdf_url="https://arxiv.org/pdf/2501.12345",
            entry_url="https://arxiv.org/abs/2501.12345",
            published=datetime(2025, 1, 15),
            updated=datetime(2025, 1, 15),
        )

    def test_paper_creation(self):
        """Test paper creation."""
        self.assertEqual(self.paper.arxiv_id, "2501.12345")
        self.assertEqual(self.paper.title, "Test Paper on Transformers")
        self.assertEqual(len(self.paper.authors), 2)
        self.assertEqual(self.paper.score, 0.0)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        data = self.paper.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["arxiv_id"], "2501.12345")
        self.assertEqual(data["title"], "Test Paper on Transformers")
        self.assertIn("published", data)
        self.assertIn("comment", data)
        self.assertIsNone(data["comment"])

    def test_to_csv_row(self):
        """Test conversion to CSV row."""
        row = self.paper.to_csv_row()
        self.assertIsInstance(row, dict)
        self.assertEqual(row["arxiv_id"], "2501.12345")
        # Authors should be semicolon-separated
        self.assertEqual(row["authors"], "Alice Smith; Bob Jones")
        # Categories should be comma-separated
        self.assertEqual(row["categories"], "cs.AI, cs.LG")
        self.assertEqual(row["comment"], "")


class TestFetchConfig(unittest.TestCase):
    """Test FetchConfig model."""

    def test_fetch_config_defaults(self):
        """Test FetchConfig with defaults."""
        config = FetchConfig(
            categories=["cs.AI", "cs.CV"],
            max_results=50,
        )
        self.assertEqual(config.fetch_mode, "category_only")
        self.assertEqual(config.search_keywords, [])
        self.assertEqual(config.sort_by, "submittedDate")
        self.assertFalse(config.fetch_full_categories)

    def test_fetch_config_combined_mode(self):
        """Test FetchConfig with combined mode."""
        config = FetchConfig(
            categories=["cs.AI"],
            max_results=20,
            fetch_mode="combined",
            search_keywords=["transformer", "diffusion"],
        )
        self.assertEqual(config.fetch_mode, "combined")
        self.assertEqual(len(config.search_keywords), 2)


class TestFilterConfig(unittest.TestCase):
    """Test FilterConfig model."""

    def test_filter_config_defaults(self):
        """Test FilterConfig with defaults."""
        config = FilterConfig(
            enabled=True,
            keywords={
                "high_priority": ["transformer"],
                "medium_priority": ["detection"],
            },
        )
        self.assertTrue(config.enabled)
        self.assertEqual(config.mode, "static")
        self.assertEqual(config.min_score, 0.0)
        self.assertEqual(config.top_k, 20)


if __name__ == "__main__":
    unittest.main()
