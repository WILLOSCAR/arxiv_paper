#!/usr/bin/env python3
"""Quick test script to fetch today's cs.AI / cs.HC papers and print metadata."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src import ArxivFetcher, FetchConfig


def main() -> None:
    fetch_config = FetchConfig(
        categories=["cs.AI", "cs.HC"],
        max_results=50,
        fetch_mode="category_only",
        sort_by="submittedDate",
        sort_order="descending",
    )

    fetcher = ArxivFetcher(fetch_config)
    papers = fetcher.fetch_latest_papers(days=1)

    print(f"Fetched {len(papers)} papers from cs.AI/cs.HC in the last day\n")

    for idx, paper in enumerate(papers[:10], start=1):
        authors = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors += " et al."
        print(f"[{idx}] {paper.title}")
        print(f"    ID: {paper.arxiv_id}")
        print(f"    Published: {paper.published.strftime('%Y-%m-%d')}")
        print(f"    Categories: {', '.join(paper.categories)}")
        print(f"    Authors: {authors}")
        print(f"    URL: {paper.entry_url}\n")


if __name__ == "__main__":
    main()
