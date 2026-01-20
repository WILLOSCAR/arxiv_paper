"""Tests for calendar-day fetching logic (timezone window filtering)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

from src.fetcher import ArxivFetcher
from src.models import FetchConfig


class TestFetcherCalendarDay(TestCase):
    def test_fetch_papers_for_calendar_day_filters_by_window(self):
        cfg = FetchConfig(
            categories=["cs.AI"],
            max_results=100,
            sort_by="submittedDate",
            sort_order="descending",
            fetch_mode="category_only",
        )
        fetcher = ArxivFetcher(cfg)

        # Local day in Asia/Shanghai: 2026-01-20 00:00+08 == 2026-01-19 16:00Z
        target_day = date(2026, 1, 20)
        start_utc = datetime(2026, 1, 19, 16, 0, 0, tzinfo=timezone.utc)
        end_utc = datetime(2026, 1, 20, 16, 0, 0, tzinfo=timezone.utc)

        def author(name: str):
            return SimpleNamespace(name=name)

        # Results are sorted newest-first, so we can test break behavior.
        results = [
            # Too new (after end_utc) -> skipped
            SimpleNamespace(
                entry_id="http://arxiv.org/abs/9999.00003v1",
                title="Too new",
                summary="",
                authors=[author("A")],
                primary_category="cs.AI",
                categories=["cs.AI"],
                pdf_url="https://arxiv.org/pdf/9999.00003v1",
                published=end_utc,
                updated=end_utc,
                comment="",
                journal_ref="",
                doi="",
            ),
            # In window -> kept
            SimpleNamespace(
                entry_id="http://arxiv.org/abs/9999.00002v1",
                title="In window 1",
                summary="",
                authors=[author("A")],
                primary_category="cs.AI",
                categories=["cs.AI"],
                pdf_url="https://arxiv.org/pdf/9999.00002v1",
                published=end_utc.replace(hour=15),
                updated=end_utc.replace(hour=15),
                comment="",
                journal_ref="",
                doi="",
            ),
            # In window -> kept
            SimpleNamespace(
                entry_id="http://arxiv.org/abs/9999.00001v1",
                title="In window 2",
                summary="",
                authors=[author("A")],
                primary_category="cs.AI",
                categories=["cs.AI"],
                pdf_url="https://arxiv.org/pdf/9999.00001v1",
                published=start_utc,
                updated=start_utc,
                comment="",
                journal_ref="",
                doi="",
            ),
            # Too old (before start_utc) -> triggers break
            SimpleNamespace(
                entry_id="http://arxiv.org/abs/9999.00000v1",
                title="Too old",
                summary="",
                authors=[author("A")],
                primary_category="cs.AI",
                categories=["cs.AI"],
                pdf_url="https://arxiv.org/pdf/9999.00000v1",
                published=start_utc.replace(hour=15) if start_utc.hour != 15 else start_utc.replace(hour=14),
                updated=start_utc.replace(hour=15) if start_utc.hour != 15 else start_utc.replace(hour=14),
                comment="",
                journal_ref="",
                doi="",
            ),
        ]

        def fake_results(_search):
            for r in results:
                yield r

        fetcher.client.results = fake_results  # type: ignore[attr-defined]

        papers = fetcher.fetch_papers_for_calendar_day(target_day, timezone_name="Asia/Shanghai")
        ids = [p.arxiv_id for p in papers]
        self.assertEqual(ids, ["9999.00002v1", "9999.00001v1"])

