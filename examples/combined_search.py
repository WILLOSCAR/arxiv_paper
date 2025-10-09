#!/usr/bin/env python3
"""
Combined Search Example - Search by category AND keywords.

This is the most efficient way to fetch papers.
"""

from src import ArxivFetcher, FetchConfig, PaperStorage

def main():
    print("=== Combined Search Example ===\n")

    # Configure for combined search
    config = FetchConfig(
        categories=["cs.CV", "cs.AI"],
        max_results=20,
        fetch_mode="combined",  # ⭐ Combined mode
        search_keywords=["transformer", "diffusion", "multimodal"],
    )

    print(f"Searching for papers in {config.categories}")
    print(f"with keywords: {config.search_keywords}\n")

    # Fetch papers
    fetcher = ArxivFetcher(config)
    papers = fetcher.fetch_latest_papers(days=7)

    print(f"\n✓ Found {len(papers)} papers\n")

    # Display results
    print("Papers found:")
    for i, paper in enumerate(papers[:10], 1):
        print(f"\n{i}. {paper.title}")
        print(f"   Category: {paper.primary_category}")
        print(f"   URL: {paper.entry_url}")

    # Save results
    if papers:
        storage = PaperStorage(
            json_path="data/combined_search.json",
            csv_path="data/combined_search.csv",
        )
        storage.save(papers, format="both")
        print(f"\n✓ Saved {len(papers)} papers to data/")


if __name__ == "__main__":
    main()
