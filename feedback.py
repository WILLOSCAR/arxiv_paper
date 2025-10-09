#!/usr/bin/env python3
"""
Feedback CLI - 用户反馈管理工具

Usage:
    python feedback.py like <paper_id>       # 标记喜欢
    python feedback.py dislike <paper_id>    # 标记不喜欢
    python feedback.py stats                 # 查看统计
    python feedback.py list [liked|disliked] # 查看列表
    python feedback.py clear [liked|disliked|all]  # 清空数据
"""

import argparse
import json
import sys
from pathlib import Path

from src.feedback import FeedbackCollector


def cmd_like(args):
    """Record a like."""
    collector = FeedbackCollector()

    # Try to find paper details from recent papers
    paper_data = _find_paper_data(args.paper_id)

    collector.record_feedback(args.paper_id, "like", paper_data)
    print(f"✓ Liked paper: {args.paper_id}")

    if paper_data:
        print(f"  Title: {paper_data.get('title', 'N/A')}")


def cmd_dislike(args):
    """Record a dislike."""
    collector = FeedbackCollector()
    paper_data = _find_paper_data(args.paper_id)

    collector.record_feedback(args.paper_id, "dislike", paper_data)
    print(f"✓ Disliked paper: {args.paper_id}")

    if paper_data:
        print(f"  Title: {paper_data.get('title', 'N/A')}")


def cmd_stats(args):
    """Show statistics."""
    collector = FeedbackCollector()
    stats = collector.get_statistics()

    print("\n📊 User Feedback Statistics")
    print("=" * 50)
    print(f"  Total liked:    {stats['total_liked']} papers")
    print(f"  Total disliked: {stats['total_disliked']} papers")
    print(f"  Like ratio:     {stats['feedback_ratio']*100:.1f}%")

    print("\n🔑 Top Keywords in Liked Papers:")
    for keyword, count in stats["top_keywords"]:
        percentage = count / stats["total_liked"] * 100 if stats["total_liked"] > 0 else 0
        print(f"  - {keyword:20s} {count:3d} papers ({percentage:.0f}%)")

    print()


def cmd_list(args):
    """List papers."""
    collector = FeedbackCollector()

    if args.type in ["liked", "all"]:
        liked = collector.get_liked_papers()
        print(f"\n👍 Liked Papers ({len(liked)}):")
        print("=" * 50)
        for i, paper in enumerate(liked, 1):
            print(f"{i}. [{paper['paper_id']}] {paper.get('title', 'N/A')}")
            if args.verbose:
                print(f"   Keywords: {', '.join(paper.get('matched_keywords', []))}")
                print(f"   Time: {paper['timestamp']}")
            print()

    if args.type in ["disliked", "all"]:
        disliked = collector.get_disliked_papers()
        print(f"\n👎 Disliked Papers ({len(disliked)}):")
        print("=" * 50)
        for i, paper in enumerate(disliked, 1):
            print(f"{i}. [{paper['paper_id']}] {paper.get('title', 'N/A')}")
            print()


def cmd_clear(args):
    """Clear feedback data."""
    collector = FeedbackCollector()

    if args.type == "all":
        confirm = input("⚠️  Clear ALL feedback data? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cancelled.")
            return
        collector.clear_feedback()
        print("✓ Cleared all feedback data")

    elif args.type == "liked":
        collector.clear_feedback("like")
        print("✓ Cleared liked papers")

    elif args.type == "disliked":
        collector.clear_feedback("dislike")
        print("✓ Cleared disliked papers")


def _find_paper_data(paper_id: str) -> dict:
    """
    Try to find paper details from recent papers.json.

    Args:
        paper_id: arXiv ID

    Returns:
        Paper data dict or None
    """
    papers_file = Path("data/papers.json")
    if not papers_file.exists():
        return None

    try:
        with open(papers_file, "r", encoding="utf-8") as f:
            papers = json.load(f)

        for paper in papers:
            if paper.get("arxiv_id") == paper_id:
                return {
                    "title": paper.get("title"),
                    "matched_keywords": paper.get("matched_keywords", []),
                    "score": paper.get("score"),
                    "categories": paper.get("categories", []),
                }
    except Exception:
        pass

    return None


def main():
    parser = argparse.ArgumentParser(description="Manage paper feedback")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Like command
    like_parser = subparsers.add_parser("like", help="Mark paper as liked")
    like_parser.add_argument("paper_id", help="arXiv paper ID (e.g., 2501.12345)")
    like_parser.set_defaults(func=cmd_like)

    # Dislike command
    dislike_parser = subparsers.add_parser("dislike", help="Mark paper as disliked")
    dislike_parser.add_argument("paper_id", help="arXiv paper ID")
    dislike_parser.set_defaults(func=cmd_dislike)

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show statistics")
    stats_parser.set_defaults(func=cmd_stats)

    # List command
    list_parser = subparsers.add_parser("list", help="List papers")
    list_parser.add_argument(
        "type",
        nargs="?",
        default="liked",
        choices=["liked", "disliked", "all"],
        help="Type of papers to list",
    )
    list_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    list_parser.set_defaults(func=cmd_list)

    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear feedback data")
    clear_parser.add_argument(
        "type",
        nargs="?",
        default="all",
        choices=["liked", "disliked", "all"],
        help="Type of data to clear",
    )
    clear_parser.set_defaults(func=cmd_clear)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Execute command
    args.func(args)


if __name__ == "__main__":
    main()
