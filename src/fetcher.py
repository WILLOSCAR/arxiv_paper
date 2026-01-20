"""arXiv paper fetcher module using the official arxiv Python library."""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

import arxiv
from zoneinfo import ZoneInfo

from .models import Paper, FetchConfig

logger = logging.getLogger(__name__)


class ArxivFetcher:
    """Fetches papers from arXiv using the official API."""

    def __init__(self, config: FetchConfig):
        """
        Initialize the fetcher with configuration.

        Args:
            config: FetchConfig object with arXiv query parameters
        """
        self.config = config
        self.client = arxiv.Client()

    def fetch_latest_papers(self, days: int = 1) -> List[Paper]:
        """
        Fetch the latest papers based on configured fetch_mode.

        Args:
            days: Number of days to look back (default: 1 for today's papers)

        Returns:
            List of Paper objects
        """
        mode = self.config.fetch_mode

        primary_papers: List[Paper]

        if mode == "category_only":
            primary_papers = self._fetch_by_categories(days)
        elif mode == "keyword_only":
            primary_papers = self._fetch_by_keywords(days)
        elif mode == "combined":
            primary_papers = self._fetch_combined(days)
        elif mode == "category_then_filter":
            primary_papers = self._fetch_by_categories(days)
        else:
            logger.warning(f"Unknown fetch_mode '{mode}', using category_only")
            primary_papers = self._fetch_by_categories(days)

        if (
            self.config.fetch_full_categories
            and mode != "category_only"
        ):
            logger.info(
                "fetch_full_categories=True, fetching full category dumps for %s",
                ", ".join(self.config.categories),
            )
            category_papers = self._fetch_by_categories(days)
            primary_papers.extend(category_papers)
            primary_papers = self._deduplicate_papers(primary_papers)

        return primary_papers

    def fetch_papers_for_calendar_day(
        self,
        day: date,
        *,
        timezone_name: str = "Asia/Shanghai",
    ) -> List[Paper]:
        """
        Fetch papers that fall within a calendar day window in a given timezone.

        This is useful for "today's papers" workflows where the window is a
        calendar day (00:00-23:59) rather than a rolling N-day cutoff.

        Notes:
        - arXiv API returns timestamps in UTC. We convert the local calendar day
          window to UTC and filter by result.published.
        - This method uses category queries (cat:...) and relies on the search
          being sorted by submittedDate descending so we can stop early once
          results are older than the window start.

        Args:
            day: Local calendar day (date) in timezone_name
            timezone_name: IANA timezone (default: Asia/Shanghai)

        Returns:
            List[Paper] within [day 00:00, next day 00:00) in the given timezone
        """
        try:
            tz = ZoneInfo(timezone_name)
        except Exception as exc:
            raise ValueError(f"Invalid timezone: {timezone_name}") from exc

        start_local = datetime.combine(day, time.min).replace(tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        all_papers: List[Paper] = []

        # Always fetch newest-first so we can break once we're older than window.
        for category in self.config.categories:
            logger.info(
                "Fetching papers for %s in %s (UTC window %s -> %s)",
                category,
                timezone_name,
                start_utc.isoformat(),
                end_utc.isoformat(),
            )

            search = arxiv.Search(
                query=f"cat:{category}",
                max_results=self.config.max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            saw_older = False
            last_published: Optional[datetime] = None

            for result in self.client.results(search):
                last_published = result.published

                # If running for a past day, we might see newer entries first.
                if result.published >= end_utc:
                    continue

                if result.published < start_utc:
                    saw_older = True
                    break

                all_papers.append(Paper.from_arxiv_result(result))

            # If we never saw an older paper, max_results may be too small.
            if not saw_older and last_published and last_published >= start_utc:
                logger.warning(
                    "Potential truncation for %s: max_results=%s may be too low to cover full day",
                    category,
                    self.config.max_results,
                )

        unique = self._deduplicate_papers(all_papers)
        unique.sort(key=lambda p: p.published, reverse=True)
        logger.info("Total unique papers in day window: %s", len(unique))
        return unique

    def _fetch_by_categories(self, days: int) -> List[Paper]:
        """
        Fetch papers by categories only.

        Args:
            days: Number of days to look back

        Returns:
            List of Paper objects
        """
        all_papers = []

        for category in self.config.categories:
            logger.info(f"Fetching papers from category: {category}")

            try:
                papers = self._fetch_category(category, days)
                all_papers.extend(papers)
                logger.info(f"Fetched {len(papers)} papers from {category}")

            except Exception as e:
                logger.error(f"Error fetching papers from {category}: {e}")

        # Remove duplicates based on arxiv_id
        unique_papers = self._deduplicate_papers(all_papers)
        logger.info(f"Total unique papers fetched: {len(unique_papers)}")

        return unique_papers

    def _fetch_by_keywords(self, days: int) -> List[Paper]:
        """
        Fetch papers by keywords only.

        Args:
            days: Number of days to look back

        Returns:
            List of Paper objects
        """
        if not self.config.search_keywords:
            logger.warning("No search_keywords configured for keyword_only mode")
            return []

        logger.info(f"Fetching papers by keywords: {self.config.search_keywords}")

        # Construct query with keywords
        query = " OR ".join([f'"{kw}"' for kw in self.config.search_keywords])

        search = arxiv.Search(
            query=query,
            max_results=self.config.max_results,
            sort_by=self._get_sort_by(),
            sort_order=self._get_sort_order(),
        )

        papers = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        for result in self.client.results(search):
            if result.published < cutoff_date:
                continue

            paper = Paper.from_arxiv_result(result)
            papers.append(paper)

        logger.info(f"Fetched {len(papers)} papers by keywords")
        return papers

    def _fetch_combined(self, days: int) -> List[Paper]:
        """
        Fetch papers by combining categories AND keywords.
        This is the most efficient mode for targeted searches.

        Args:
            days: Number of days to look back

        Returns:
            List of Paper objects
        """
        if not self.config.search_keywords:
            logger.warning("No search_keywords for combined mode, using category_only")
            return self._fetch_by_categories(days)

        all_papers = []

        for category in self.config.categories:
            logger.info(f"Fetching papers: {category} + keywords")

            try:
                papers = self._fetch_category_with_keywords(
                    category, self.config.search_keywords, days
                )
                all_papers.extend(papers)
                logger.info(f"Fetched {len(papers)} papers from {category} with keywords")

            except Exception as e:
                logger.error(f"Error fetching {category} with keywords: {e}")

        unique_papers = self._deduplicate_papers(all_papers)
        logger.info(f"Total unique papers fetched: {len(unique_papers)}")

        return unique_papers

    def _fetch_category_with_keywords(
        self, category: str, keywords: List[str], days: int
    ) -> List[Paper]:
        """
        Fetch papers from a specific category with keyword filtering.

        Args:
            category: arXiv category (e.g., "cs.CV")
            keywords: List of keywords to search for
            days: Number of days to look back

        Returns:
            List of Paper objects
        """
        # Construct combined query: (keyword1 OR keyword2) AND cat:cs.CV
        keyword_query = " OR ".join([f'"{kw}"' for kw in keywords])
        query = f"({keyword_query}) AND cat:{category}"

        search = arxiv.Search(
            query=query,
            max_results=self.config.max_results,
            sort_by=self._get_sort_by(),
            sort_order=self._get_sort_order(),
        )

        papers = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        for result in self.client.results(search):
            if result.published < cutoff_date:
                logger.debug(f"Skipping paper {result.entry_id} (too old)")
                continue

            paper = Paper.from_arxiv_result(result)
            papers.append(paper)

        return papers

    def _fetch_category(self, category: str, days: int) -> List[Paper]:
        """
        Fetch papers from a specific category.

        Args:
            category: arXiv category (e.g., "cs.CV", "cs.AI")
            days: Number of days to look back

        Returns:
            List of Paper objects
        """
        # Construct search query
        search = arxiv.Search(
            query=f"cat:{category}",
            max_results=self.config.max_results,
            sort_by=self._get_sort_by(),
            sort_order=self._get_sort_order(),
        )

        # Fetch results
        papers = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        for result in self.client.results(search):
            # Filter by date
            if result.published < cutoff_date:
                logger.debug(f"Skipping paper {result.entry_id} (too old)")
                continue

            # Convert to Paper object
            paper = Paper.from_arxiv_result(result)
            papers.append(paper)

        return papers

    def _get_sort_by(self) -> arxiv.SortCriterion:
        """Convert config sort_by string to arxiv.SortCriterion."""
        sort_map = {
            "submittedDate": arxiv.SortCriterion.SubmittedDate,
            "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
            "relevance": arxiv.SortCriterion.Relevance,
        }
        return sort_map.get(
            self.config.sort_by, arxiv.SortCriterion.SubmittedDate
        )

    def _get_sort_order(self) -> arxiv.SortOrder:
        """Convert config sort_order string to arxiv.SortOrder."""
        order_map = {
            "descending": arxiv.SortOrder.Descending,
            "ascending": arxiv.SortOrder.Ascending,
        }
        return order_map.get(
            self.config.sort_order, arxiv.SortOrder.Descending
        )

    def _deduplicate_papers(self, papers: List[Paper]) -> List[Paper]:
        """
        Remove duplicate papers based on arxiv_id.

        Args:
            papers: List of Paper objects

        Returns:
            List of unique Paper objects
        """
        seen_ids = set()
        unique_papers = []

        for paper in papers:
            if paper.arxiv_id not in seen_ids:
                seen_ids.add(paper.arxiv_id)
                unique_papers.append(paper)

        return unique_papers

    def search_by_keywords(self, keywords: List[str], max_results: int = 50) -> List[Paper]:
        """
        Search papers by keywords (useful for initial testing).

        Args:
            keywords: List of keywords to search for
            max_results: Maximum number of results to return

        Returns:
            List of Paper objects
        """
        # Construct query with keywords
        query = " OR ".join([f'"{keyword}"' for keyword in keywords])

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
    
        papers = []
        for result in self.client.results(search):
            paper = Paper.from_arxiv_result(result)
            papers.append(paper)

        logger.info(f"Found {len(papers)} papers matching keywords: {keywords}")
        return papers
