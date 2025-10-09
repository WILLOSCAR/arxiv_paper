#!/usr/bin/env python3
"""
Keyword-Only Search Example - Search by keywords across all categories.

Use this when you want papers on a specific topic regardless of category.
"""

from src import ArxivFetcher, FetchConfig

def main():
    print("=== Keyword-Only Search Example ===\n")

    # Configure for keyword-only search
    config = FetchConfig(
        categories=[],  # Empty - not used in keyword_only mode
        max_results=30,
        fetch_mode="keyword_only",  # Search by keywords only
        search_keywords=[
            "vision-language model",
            "multimodal learning",
            "CLIP",
        ],
    )

    print(f"Searching across all categories for keywords:")
    for kw in config.search_keywords:
        print(f"  - {kw}")
    print()

    # Fetch papers
    fetcher = ArxivFetcher(config)
    papers = fetcher.fetch_latest_papers(days=7)

    print(f"\n✓ Found {len(papers)} papers\n")

    # Group by category
    from collections import defaultdict
    by_category = defaultdict(list)
    for paper in papers:
        by_category[paper.primary_category].append(paper)

    print("Papers by category:")
    for category, papers_list in sorted(by_category.items()):
        print(f"\n{category}: {len(papers_list)} papers")
        for paper in papers_list[:3]:  # Show first 3
            print(f"  - {paper.title}")


if __name__ == "__main__":
    main()
