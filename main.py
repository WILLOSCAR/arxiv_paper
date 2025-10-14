#!/usr/bin/env python3
"""
arXiv Paper Bot - Main entry point

Automated paper fetching, filtering, and summarization from arXiv.
"""

import argparse
import logging
from pathlib import Path

import yaml

from src import (
    ArxivFetcher,
    FetchConfig,
    FilterConfig,
    PaperFilter,
    PaperStorage,
    PaperSummarizer,
    SummarizerConfig,
    NotificationConfig,
    build_notifier,
)


def setup_logging(config: dict) -> None:
    """Configure logging based on config."""
    log_config = config.get("logging", {})

    # Create log directory if needed
    log_file = log_config.get("log_file", "logs/arxiv_bot.log")
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure logging
    level = getattr(logging, log_config.get("level", "INFO"))
    handlers = []

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    handlers.append(file_handler)

    # Console handler
    if log_config.get("console_output", True):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        handlers.append(console_handler)

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    """Main execution function."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="arXiv Paper Bot")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to look back (default: 1)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode (fetch fewer papers)",
    )
    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Setup logging
    setup_logging(config)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("arXiv Paper Bot Starting")
    logger.info("=" * 60)

    try:
        # Step 1: Fetch papers from arXiv
        logger.info("\n[1/5] Fetching papers from arXiv...")

        arxiv_config = config["arxiv"]
        fetch_config = FetchConfig(
            categories=arxiv_config["categories"],
            max_results=arxiv_config.get("max_results", 50),
            sort_by=arxiv_config.get("sort_by", "submittedDate"),
            sort_order=arxiv_config.get("sort_order", "descending"),
            fetch_mode=arxiv_config.get("fetch_mode", "category_only"),
            search_keywords=arxiv_config.get("search_keywords", []),
        )

        fetcher = ArxivFetcher(fetch_config)
        papers = fetcher.fetch_latest_papers(days=args.days)

        logger.info(f"✓ Fetched {len(papers)} papers")

        if not papers:
            logger.warning("No papers fetched. Exiting.")
            return

        # Step 2: Filter and rank papers
        logger.info("\n[2/5] Filtering and ranking papers...")

        filter_config_dict = config["filter"]
        filter_config = FilterConfig(
            enabled=filter_config_dict.get("enabled", True),
            mode=filter_config_dict.get("mode", "static"),
            keywords=filter_config_dict.get("keywords", {}),
            min_score=filter_config_dict.get("min_score", 0.0),
            top_k=filter_config_dict.get("top_k", 20),
        )

        paper_filter = PaperFilter(filter_config)
        filtered_papers = paper_filter.filter_and_rank(papers)

        logger.info(f"✓ Filtered to {len(filtered_papers)} papers")

        # Show statistics
        stats = paper_filter.get_statistics(filtered_papers)
        logger.info(f"  Average score: {stats['avg_score']:.2f}")
        logger.info(f"  Score range: {stats['min_score']:.1f} - {stats['max_score']:.1f}")

        if stats.get("top_keywords"):
            logger.info("  Top keywords:")
            for kw, count in stats["top_keywords"][:5]:
                logger.info(f"    - {kw}: {count} papers")

        # Step 3: Generate summaries (optional)
        logger.info("\n[3/5] Generating summaries...")

        summarizer_config_dict = config.get("summarization", {})
        api_config = summarizer_config_dict.get("api", {})

        summarizer_config = SummarizerConfig(
            enabled=summarizer_config_dict.get("enabled", False),
            provider=summarizer_config_dict.get("provider", "gemini"),
            base_url=api_config.get("base_url", ""),
            model=api_config.get("model", ""),
            api_key_env=api_config.get("api_key_env"),
            fields=summarizer_config_dict.get("fields", []),
        )

        summarizer = PaperSummarizer(summarizer_config)

        if summarizer_config.enabled:
            filtered_papers = summarizer.summarize_papers(filtered_papers)
            logger.info(f"✓ Generated summaries for {len(filtered_papers)} papers")
        else:
            logger.info("✓ Summarization disabled (skipped)")

        # Step 4: Save results
        logger.info("\n[4/5] Saving results...")

        storage_config = config["storage"]
        storage = PaperStorage(
            json_path=storage_config.get("json_path", "data/papers.json"),
            csv_path=storage_config.get("csv_path", "data/papers.csv"),
            append_mode=storage_config.get("append_mode", True),
        )

        storage.save(
            filtered_papers,
            format=storage_config.get("format", "both"),
        )

        logger.info(f"✓ Saved {len(filtered_papers)} papers")

        # Step 5: Push notifications (optional)
        notification_dict = config.get("notification", {})
        notification_config = NotificationConfig(
            enabled=notification_dict.get("enabled", False),
            provider=notification_dict.get("provider", ""),
            top_k=notification_dict.get("top_k", 5),
            feishu_webhook=notification_dict.get("feishu", {}).get("webhook_url"),
            feishu_secret=notification_dict.get("feishu", {}).get("secret"),
            telegram_bot_token=notification_dict.get("telegram", {}).get("bot_token"),
            telegram_chat_id=notification_dict.get("telegram", {}).get("chat_id"),
            wechat_app_id=notification_dict.get("wechat", {}).get("app_id"),
            wechat_app_secret=notification_dict.get("wechat", {}).get("app_secret"),
            wechat_open_id=notification_dict.get("wechat", {}).get("open_id"),
        )

        try:
            notifier = build_notifier(notification_config)
            if notifier:
                logger.info("\n[5/5] Sending notifications via %s...", notifier.provider_name)
                notifier.send(filtered_papers)
        except Exception as notify_error:
            logger.error("通知发送失败: %s", notify_error, exc_info=True)

        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("Execution Summary:")
        logger.info(f"  Total fetched: {len(papers)}")
        logger.info(f"  After filtering: {len(filtered_papers)}")
        logger.info(f"  Output format: {storage_config.get('format', 'both')}")
        logger.info("=" * 60)

        # Print top papers
        if filtered_papers:
            logger.info("\nTop 5 Papers:")
            for i, paper in enumerate(filtered_papers[:5], 1):
                logger.info(f"\n{i}. {paper.title}")
                logger.info(f"   Score: {paper.score:.1f}")
                logger.info(f"   Keywords: {', '.join(paper.matched_keywords)}")
                logger.info(f"   URL: {paper.entry_url}")

    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
