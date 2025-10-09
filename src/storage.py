"""Data storage module for saving papers to JSON and CSV formats."""

import csv
import json
import logging
from pathlib import Path
from typing import List

from .models import Paper

logger = logging.getLogger(__name__)


class PaperStorage:
    """Handles saving and loading papers to/from various formats."""

    def __init__(
        self,
        json_path: str = "data/papers.json",
        csv_path: str = "data/papers.csv",
        append_mode: bool = True,
    ):
        """
        Initialize storage with output paths.

        Args:
            json_path: Path to JSON output file
            csv_path: Path to CSV output file
            append_mode: If True, append to existing files; if False, overwrite
        """
        self.json_path = Path(json_path)
        self.csv_path = Path(csv_path)
        self.append_mode = append_mode

        # Create parent directories if they don't exist
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

    def save_json(self, papers: List[Paper]) -> None:
        """
        Save papers to JSON file.

        Args:
            papers: List of Paper objects to save
        """
        try:
            data = []

            # Load existing data if in append mode
            if self.append_mode and self.json_path.exists():
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(f"Loaded {len(data)} existing papers from JSON")

            # Add new papers
            new_data = [paper.to_dict() for paper in papers]
            data.extend(new_data)

            # Remove duplicates based on arxiv_id
            seen_ids = set()
            unique_data = []
            for item in data:
                if item["arxiv_id"] not in seen_ids:
                    seen_ids.add(item["arxiv_id"])
                    unique_data.append(item)

            # Save to file
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(unique_data, f, indent=2, ensure_ascii=False)

            logger.info(
                f"Saved {len(unique_data)} papers to {self.json_path} "
                f"(added {len(papers)} new)"
            )

        except Exception as e:
            logger.error(f"Error saving to JSON: {e}")
            raise

    def save_csv(self, papers: List[Paper]) -> None:
        """
        Save papers to CSV file.

        Args:
            papers: List of Paper objects to save
        """
        try:
            # Determine if we need to write headers
            write_header = not (self.append_mode and self.csv_path.exists())

            # Open file in append or write mode
            mode = "a" if self.append_mode else "w"

            with open(self.csv_path, mode, newline="", encoding="utf-8") as f:
                if papers:
                    # Get field names from the first paper
                    fieldnames = papers[0].to_csv_row().keys()

                    writer = csv.DictWriter(f, fieldnames=fieldnames)

                    if write_header:
                        writer.writeheader()

                    for paper in papers:
                        writer.writerow(paper.to_csv_row())

            logger.info(f"Saved {len(papers)} papers to {self.csv_path}")

        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")
            raise

    def save(self, papers: List[Paper], format: str = "both") -> None:
        """
        Save papers to specified format(s).

        Args:
            papers: List of Paper objects to save
            format: "json", "csv", or "both"
        """
        if not papers:
            logger.warning("No papers to save")
            return

        if format in ["json", "both"]:
            self.save_json(papers)

        if format in ["csv", "both"]:
            self.save_csv(papers)

    def load_json(self) -> List[dict]:
        """
        Load papers from JSON file.

        Returns:
            List of paper dictionaries
        """
        try:
            if not self.json_path.exists():
                logger.warning(f"JSON file not found: {self.json_path}")
                return []

            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.info(f"Loaded {len(data)} papers from {self.json_path}")
            return data

        except Exception as e:
            logger.error(f"Error loading from JSON: {e}")
            raise

    def load_csv(self) -> List[dict]:
        """
        Load papers from CSV file.

        Returns:
            List of paper dictionaries
        """
        try:
            if not self.csv_path.exists():
                logger.warning(f"CSV file not found: {self.csv_path}")
                return []

            data = []
            with open(self.csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                data = list(reader)

            logger.info(f"Loaded {len(data)} papers from {self.csv_path}")
            return data

        except Exception as e:
            logger.error(f"Error loading from CSV: {e}")
            raise

    def clear_data(self) -> None:
        """Clear all stored data (delete files)."""
        if self.json_path.exists():
            self.json_path.unlink()
            logger.info(f"Deleted {self.json_path}")

        if self.csv_path.exists():
            self.csv_path.unlink()
            logger.info(f"Deleted {self.csv_path}")
