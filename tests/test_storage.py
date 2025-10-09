"""Tests for data storage."""

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.models import Paper
from src.storage import PaperStorage


class TestPaperStorage(unittest.TestCase):
    """Test PaperStorage class."""

    def setUp(self):
        """Set up test data and temporary directory."""
        # Create temporary directory for tests
        self.temp_dir = tempfile.mkdtemp()

        # Create test papers
        self.papers = [
            Paper(
                arxiv_id="2501.001",
                title="Test Paper 1",
                abstract="Abstract 1",
                authors=["Alice"],
                primary_category="cs.AI",
                categories=["cs.AI"],
                pdf_url="https://arxiv.org/pdf/2501.001",
                entry_url="https://arxiv.org/abs/2501.001",
                published=datetime(2025, 1, 1),
                updated=datetime(2025, 1, 1),
                score=5.0,
                matched_keywords=["transformer"],
            ),
            Paper(
                arxiv_id="2501.002",
                title="Test Paper 2",
                abstract="Abstract 2",
                authors=["Bob", "Charlie"],
                primary_category="cs.CV",
                categories=["cs.CV", "cs.LG"],
                pdf_url="https://arxiv.org/pdf/2501.002",
                entry_url="https://arxiv.org/abs/2501.002",
                published=datetime(2025, 1, 2),
                updated=datetime(2025, 1, 2),
                score=3.0,
                matched_keywords=["diffusion", "detection"],
            ),
        ]

        # Create storage
        self.json_path = os.path.join(self.temp_dir, "papers.json")
        self.csv_path = os.path.join(self.temp_dir, "papers.csv")

        self.storage = PaperStorage(
            json_path=self.json_path,
            csv_path=self.csv_path,
            append_mode=False,
        )

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_save_json(self):
        """Test saving papers to JSON."""
        self.storage.save_json(self.papers)

        # Verify file exists
        self.assertTrue(os.path.exists(self.json_path))

        # Load and verify content
        with open(self.json_path, "r") as f:
            data = json.load(f)

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["arxiv_id"], "2501.001")
        self.assertEqual(data[1]["arxiv_id"], "2501.002")

    def test_save_csv(self):
        """Test saving papers to CSV."""
        self.storage.save_csv(self.papers)

        # Verify file exists
        self.assertTrue(os.path.exists(self.csv_path))

        # Read CSV file
        import csv

        with open(self.csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["arxiv_id"], "2501.001")
        # Check multi-author formatting
        self.assertEqual(rows[1]["authors"], "Bob; Charlie")

    def test_save_both_formats(self):
        """Test saving to both JSON and CSV."""
        self.storage.save(self.papers, format="both")

        self.assertTrue(os.path.exists(self.json_path))
        self.assertTrue(os.path.exists(self.csv_path))

    def test_append_mode_json(self):
        """Test append mode for JSON."""
        # Create storage with append mode
        storage_append = PaperStorage(
            json_path=self.json_path,
            csv_path=self.csv_path,
            append_mode=True,
        )

        # Save first paper
        storage_append.save_json([self.papers[0]])

        # Save second paper
        storage_append.save_json([self.papers[1]])

        # Load and verify both papers are present
        data = storage_append.load_json()
        self.assertEqual(len(data), 2)

    def test_load_json(self):
        """Test loading papers from JSON."""
        self.storage.save_json(self.papers)
        loaded_data = self.storage.load_json()

        self.assertEqual(len(loaded_data), 2)
        self.assertEqual(loaded_data[0]["title"], "Test Paper 1")

    def test_load_nonexistent_file(self):
        """Test loading from nonexistent file."""
        data = self.storage.load_json()
        self.assertEqual(data, [])

    def test_duplicate_removal(self):
        """Test that duplicates are removed when appending."""
        storage_append = PaperStorage(
            json_path=self.json_path,
            csv_path=self.csv_path,
            append_mode=True,
        )

        # Save same paper twice
        storage_append.save_json([self.papers[0]])
        storage_append.save_json([self.papers[0]])  # Duplicate

        # Load and verify only one copy
        data = storage_append.load_json()
        self.assertEqual(len(data), 1)


if __name__ == "__main__":
    unittest.main()
