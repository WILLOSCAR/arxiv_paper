"""arXiv Paper Bot - Core modules for paper fetching, filtering, and storage."""

__version__ = "0.1.0"

from .fetcher import ArxivFetcher
from .filter import PaperFilter, DynamicFilter
from .models import Paper, FetchConfig, FilterConfig
from .storage import PaperStorage
from .summarizer import PaperSummarizer, SummarizerConfig
from .notifier import NotificationConfig, build_notifier

# Personalization modules (reserved slots for future implementation)
from .feedback import FeedbackCollector
from .personalization import PersonalizedRanker, IntentAgent

__all__ = [
    "ArxivFetcher",
    "PaperFilter",
    "DynamicFilter",
    "Paper",
    "FetchConfig",
    "FilterConfig",
    "PaperStorage",
    "PaperSummarizer",
    "SummarizerConfig",
    "NotificationConfig",
    "build_notifier",
    # Personalization
    "FeedbackCollector",
    "PersonalizedRanker",
    "IntentAgent",
]
