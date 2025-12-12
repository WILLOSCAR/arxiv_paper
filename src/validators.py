"""Stage validators for pipeline validation."""

import csv
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

from .models import Paper, FilterConfig

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""

    success: bool
    message: str
    details: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    stage: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def __bool__(self) -> bool:
        return self.success

    def to_dict(self) -> dict:
        """Convert to dictionary for CSV export."""
        return {
            "timestamp": self.timestamp,
            "stage": self.stage,
            "success": self.success,
            "message": self.message,
            "details": str(self.details),
            "warnings": "; ".join(self.warnings),
        }


class ValidationLogger:
    """Logger for validation results to CSV."""

    def __init__(self, log_path: str = "data/validation_log.csv"):
        """
        Initialize validation logger.

        Args:
            log_path: Path to CSV log file
        """
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_header()

    def _ensure_header(self):
        """Ensure CSV header exists."""
        if not self.log_path.exists():
            with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["timestamp", "stage", "success", "message", "details", "warnings"],
                )
                writer.writeheader()

    def log(self, result: ValidationResult):
        """
        Log a validation result to CSV.

        Args:
            result: ValidationResult to log
        """
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["timestamp", "stage", "success", "message", "details", "warnings"],
            )
            writer.writerow(result.to_dict())

        logger.info(f"Validation logged: {result.stage} - {result.message}")

    def log_all(self, results: List[ValidationResult]):
        """Log multiple validation results."""
        for result in results:
            self.log(result)

    def get_recent_logs(self, limit: int = 100) -> List[dict]:
        """
        Get recent validation logs.

        Args:
            limit: Maximum number of logs to return

        Returns:
            List of log dictionaries
        """
        if not self.log_path.exists():
            return []

        logs = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            logs = list(reader)

        return logs[-limit:]


# Global validation logger instance
_validation_logger: Optional[ValidationLogger] = None


def get_validation_logger(log_path: str = "data/validation_log.csv") -> ValidationLogger:
    """Get or create validation logger instance."""
    global _validation_logger
    if _validation_logger is None:
        _validation_logger = ValidationLogger(log_path)
    return _validation_logger


class StageValidator:
    """Stage validators for pipeline validation."""

    @staticmethod
    def validate_fetch_result(
        papers: List[Paper],
        expected_min: int = 0,
        max_age_days: int = 7,
    ) -> ValidationResult:
        """
        Validate fetch results.

        Args:
            papers: List of fetched papers
            expected_min: Minimum expected paper count
            max_age_days: Maximum age of papers in days

        Returns:
            ValidationResult with success status and details
        """
        warnings = []
        details = {
            "total_count": len(papers),
            "valid_count": 0,
            "invalid_count": 0,
            "missing_fields": [],
        }

        if not papers:
            return ValidationResult(
                success=expected_min == 0,
                message="No papers fetched" if expected_min > 0 else "Empty result (expected)",
                details=details,
            )

        # Check required fields
        required_fields = ["arxiv_id", "title", "abstract"]
        valid_papers = 0
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        for paper in papers:
            is_valid = True
            for field_name in required_fields:
                value = getattr(paper, field_name, None)
                if not value:
                    details["missing_fields"].append(
                        {"arxiv_id": paper.arxiv_id, "field": field_name}
                    )
                    is_valid = False

            # Check date
            if paper.published and paper.published < cutoff_date:
                warnings.append(f"Paper {paper.arxiv_id} is older than {max_age_days} days")

            if is_valid:
                valid_papers += 1

        details["valid_count"] = valid_papers
        details["invalid_count"] = len(papers) - valid_papers

        success = valid_papers >= expected_min
        message = f"Fetched {valid_papers} valid papers out of {len(papers)}"

        if details["missing_fields"]:
            warnings.append(f"{len(details['missing_fields'])} papers have missing fields")

        return ValidationResult(
            success=success,
            message=message,
            details=details,
            warnings=warnings,
        )

    @staticmethod
    def validate_filter_result(
        papers: List[Paper],
        config: FilterConfig,
    ) -> ValidationResult:
        """
        Validate filter results.

        Args:
            papers: List of filtered papers
            config: Filter configuration

        Returns:
            ValidationResult with success status and details
        """
        warnings = []
        details = {
            "total_count": len(papers),
            "scored_count": 0,
            "has_keywords_count": 0,
            "score_range": {"min": None, "max": None},
        }

        if not papers:
            return ValidationResult(
                success=True,
                message="No papers after filtering (expected if no matches)",
                details=details,
            )

        # Check scores and matched keywords
        scores = []
        for paper in papers:
            if paper.score is not None and paper.score >= 0:
                details["scored_count"] += 1
                scores.append(paper.score)

            if paper.matched_keywords:
                details["has_keywords_count"] += 1

        if scores:
            details["score_range"]["min"] = min(scores)
            details["score_range"]["max"] = max(scores)

        # Validate top_k limit
        if config.top_k and len(papers) > config.top_k:
            warnings.append(
                f"Paper count ({len(papers)}) exceeds top_k ({config.top_k})"
            )

        # Check min_score
        below_threshold = [p for p in papers if p.score < config.min_score]
        if below_threshold:
            warnings.append(
                f"{len(below_threshold)} papers below min_score ({config.min_score})"
            )

        # Determine success
        success = (
            details["scored_count"] == len(papers)
            and len(below_threshold) == 0
            and (not config.top_k or len(papers) <= config.top_k)
        )

        message = f"Filtered {len(papers)} papers, scores: {details['score_range']['min']:.1f}-{details['score_range']['max']:.1f}" if scores else "No scored papers"

        return ValidationResult(
            success=success,
            message=message,
            details=details,
            warnings=warnings,
        )

    @staticmethod
    def validate_api_response(
        response: dict,
        required_fields: Optional[List[str]] = None,
    ) -> ValidationResult:
        """
        Validate API response structure.

        Args:
            response: API response dictionary
            required_fields: List of required field names

        Returns:
            ValidationResult with success status and details
        """
        if required_fields is None:
            required_fields = ["choices"]

        warnings = []
        details = {
            "has_required_fields": True,
            "missing_fields": [],
        }

        if not isinstance(response, dict):
            return ValidationResult(
                success=False,
                message=f"Invalid response type: expected dict, got {type(response).__name__}",
                details=details,
            )

        # Check required fields
        for field_name in required_fields:
            if field_name not in response:
                details["missing_fields"].append(field_name)
                details["has_required_fields"] = False

        # Check for error field
        if "error" in response:
            error_info = response["error"]
            return ValidationResult(
                success=False,
                message=f"API error: {error_info}",
                details={"error": error_info},
            )

        success = details["has_required_fields"]
        message = "API response valid" if success else f"Missing fields: {details['missing_fields']}"

        return ValidationResult(
            success=success,
            message=message,
            details=details,
            warnings=warnings,
        )

    @staticmethod
    def validate_papers_for_agent(
        papers: List[Paper],
        min_count: int = 1,
    ) -> ValidationResult:
        """
        Validate papers are ready for agent processing.

        Args:
            papers: List of papers
            min_count: Minimum required papers

        Returns:
            ValidationResult with success status and details
        """
        details = {
            "total_count": len(papers),
            "ready_count": 0,
        }

        if len(papers) < min_count:
            return ValidationResult(
                success=False,
                message=f"Not enough papers: {len(papers)} < {min_count}",
                details=details,
            )

        # Check papers have required content
        ready_count = 0
        for paper in papers:
            if paper.title and paper.abstract:
                ready_count += 1

        details["ready_count"] = ready_count

        success = ready_count >= min_count
        message = f"{ready_count} papers ready for agent processing"

        return ValidationResult(
            success=success,
            message=message,
            details=details,
        )


def validate_pipeline_stage(
    stage: str,
    data: any,
    config: Optional[dict] = None,
) -> ValidationResult:
    """
    Convenience function to validate a pipeline stage.

    Args:
        stage: Stage name ("fetch", "filter", "api", "agent")
        data: Data to validate
        config: Optional configuration

    Returns:
        ValidationResult
    """
    config = config or {}

    if stage == "fetch":
        return StageValidator.validate_fetch_result(
            data,
            expected_min=config.get("expected_min", 0),
            max_age_days=config.get("max_age_days", 7),
        )
    elif stage == "filter":
        filter_config = config.get("filter_config")
        if not filter_config:
            filter_config = FilterConfig(
                enabled=True,
                mode="static",
                keywords={},
                min_score=0.0,
                top_k=None,
            )
        return StageValidator.validate_filter_result(data, filter_config)
    elif stage == "api":
        return StageValidator.validate_api_response(
            data,
            required_fields=config.get("required_fields"),
        )
    elif stage == "agent":
        return StageValidator.validate_papers_for_agent(
            data,
            min_count=config.get("min_count", 1),
        )
    else:
        return ValidationResult(
            success=False,
            message=f"Unknown stage: {stage}",
        )
