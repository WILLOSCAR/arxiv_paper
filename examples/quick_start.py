#!/usr/bin/env python3
"""
Quick Start Example - Fetch and filter papers by category.

This example demonstrates the basic usage of arXiv Paper Bot.
"""

from src import ArxivFetcher, FetchConfig, PaperFilter, FilterConfig, PaperStorage

def main():
    print("=== arXiv Paper Bot - Quick Start Example ===\n")

    # Step 1: Configure fetcher
    print("[1] Configuring paper fetcher...")
    fetch_config = FetchConfig(
        categories=["cs.AI"],  # Computer Science - AI
        max_results=10,  # Limit results for demo
        fetch_mode="category_only",
    )

    fetcher = ArxivFetcher(fetch_config)

    # Step 2: Fetch papers
    print("[2] Fetching latest papers from cs.AI...\n")
    papers = fetcher.fetch_latest_papers(days=7)  # Last 7 days
    print(f"✓ Fetched {len(papers)} papers\n")

    # Step 3: Filter papers by keywords
    print("[3] Filtering papers by keywords...")
    filter_config = FilterConfig(
        enabled=True,
        keywords={
            "high_priority": ["llm", "large language model"],
            "medium_priority": ["transformer", "attention"],
            "low_priority": ["neural network"],
        },
        min_score=1.0,
        top_k=5,
    )

    paper_filter = PaperFilter(filter_config)
    filtered_papers = paper_filter.filter_and_rank(papers)
    print(f"✓ Filtered to {len(filtered_papers)} relevant papers\n")

    # Step 4: Display results
    print("[4] Top Papers:\n")
    for i, paper in enumerate(filtered_papers[:5], 1):
        print(f"{i}. {paper.title}")
        print(f"   Score: {paper.score:.1f}")
        print(f"   Keywords: {', '.join(paper.matched_keywords)}")
        print(f"   URL: {paper.entry_url}")
        print()

    # Step 5: Save results
    print("[5] Saving results...")
    storage = PaperStorage(
        json_path="data/demo_papers.json",
        csv_path="data/demo_papers.csv",
    )
    storage.save(filtered_papers, format="both")
    print("✓ Saved to data/demo_papers.json and data/demo_papers.csv\n")

    print("=== Demo Complete! ===")


if __name__ == "__main__":
    main()
