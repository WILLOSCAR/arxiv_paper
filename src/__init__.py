"""arXiv Paper Bot - Core modules for paper fetching, filtering, and storage."""

__version__ = "0.3.0"

from .fetcher import ArxivFetcher
from .filter import PaperFilter, DynamicFilter
from .models import Paper, FetchConfig, FilterConfig
from .storage import PaperStorage
from .summarizer import PaperSummarizer, SummarizerConfig, create_summarizer
from .notifier import NotificationConfig, build_notifier
from .validators import StageValidator, ValidationResult, validate_pipeline_stage
from .api_client import APIClient, OpenRouterClient, create_client

# Personalization modules
from .feedback import FeedbackCollector
from .personalization import PersonalizedRanker, IntentAgent

# Integration layer (LangGraph orchestration)
from .integration import Orchestrator, OrchestratorConfig, AgentFilter

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
    "create_summarizer",
    "NotificationConfig",
    "build_notifier",
    # Validators
    "StageValidator",
    "ValidationResult",
    "validate_pipeline_stage",
    # API Client
    "APIClient",
    "OpenRouterClient",
    "create_client",
    # Personalization
    "FeedbackCollector",
    "PersonalizedRanker",
    "IntentAgent",
    # Integration
    "Orchestrator",
    "OrchestratorConfig",
    "AgentFilter",
]
