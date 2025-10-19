"""Data models for arXiv papers."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Paper:
    """Represents a single arXiv paper with all relevant metadata."""

    # Core identifiers
    arxiv_id: str
    title: str
    abstract: str

    # Authors
    authors: List[str]

    # Categories and tags
    primary_category: str
    categories: List[str]

    # URLs
    pdf_url: str
    entry_url: str

    # Dates
    published: datetime
    updated: datetime

    # Optional arXiv metadata
    comment: Optional[str] = None
    journal_ref: Optional[str] = None
    doi: Optional[str] = None

    # Filtering and ranking
    score: float = 0.0
    matched_keywords: List[str] = field(default_factory=list)

    # Optional AI-generated summary
    summary: Optional[dict] = None

    # Personalization fields (预留)
    user_feedback: Optional[str] = None  # "like" / "dislike" / null
    feedback_time: Optional[datetime] = None
    read_duration: Optional[int] = None  # 阅读时长（秒）
    similarity_score: Optional[float] = None  # 与历史论文相似度
    personalized_score: Optional[float] = None  # 综合个性化分数

    # Metadata
    fetched_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert paper to dictionary for JSON serialization."""
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "primary_category": self.primary_category,
            "categories": self.categories,
            "pdf_url": self.pdf_url,
            "entry_url": self.entry_url,
            "published": self.published.isoformat(),
            "updated": self.updated.isoformat(),
            "comment": self.comment,
            "journal_ref": self.journal_ref,
            "doi": self.doi,
            "score": self.score,
            "matched_keywords": self.matched_keywords,
            "summary": self.summary,
            "fetched_at": self.fetched_at.isoformat(),
        }

    def to_csv_row(self) -> dict:
        """Convert paper to a flat dictionary for CSV export."""
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": "; ".join(self.authors),
            "primary_category": self.primary_category,
            "categories": ", ".join(self.categories),
            "pdf_url": self.pdf_url,
            "entry_url": self.entry_url,
            "published": self.published.isoformat(),
            "updated": self.updated.isoformat(),
            "comment": self.comment or "",
            "journal_ref": self.journal_ref or "",
            "doi": self.doi or "",
            "score": self.score,
            "matched_keywords": ", ".join(self.matched_keywords),
            "fetched_at": self.fetched_at.isoformat(),
        }

    @staticmethod
    def from_arxiv_result(result) -> "Paper":
        """
        Create a Paper instance from an arxiv.Result object.

        Args:
            result: An arxiv.Result object from the arxiv Python library

        Returns:
            Paper: A Paper instance with all fields populated
        """
        return Paper(
            arxiv_id=result.entry_id.split("/")[-1],  # Extract ID from URL
            title=result.title.strip(),
            abstract=result.summary.strip(),
            authors=[author.name for author in result.authors],
            primary_category=result.primary_category,
            categories=result.categories,
            pdf_url=result.pdf_url,
            entry_url=result.entry_id,
            published=result.published,
            updated=result.updated,
            comment=getattr(result, "comment", None),
            journal_ref=getattr(result, "journal_ref", None),
            doi=getattr(result, "doi", None),
        )


@dataclass
class FetchConfig:
    """Configuration for fetching papers from arXiv."""

    categories: List[str]
    max_results: int
    sort_by: str = "submittedDate"
    sort_order: str = "descending"

    # Fetch mode determines how papers are retrieved
    # - "category_only": Fetch by categories only (default)
    # - "keyword_only": Fetch by keywords only (requires keywords to be set)
    # - "combined": Fetch by categories AND keywords (most efficient ⭐)
    # - "category_then_filter": Fetch by categories, then filter locally
    fetch_mode: str = "category_only"

    # Keywords for arXiv API search (used in keyword_only and combined modes)
    search_keywords: List[str] = field(default_factory=list)

    # Whether to fetch full category results in addition to keyword queries
    fetch_full_categories: bool = False


@dataclass
class FilterConfig:
    """Configuration for filtering and ranking papers."""

    enabled: bool
    mode: str = "static"
    keywords: dict = field(default_factory=dict)
    min_score: float = 0.0
    top_k: int = 20
