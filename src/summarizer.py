"""AI summarization module with pluggable provider support."""

import logging
import os
from typing import Dict, List, Optional

import openai

from .models import Paper

logger = logging.getLogger(__name__)


class SummarizerConfig:
    """Configuration for AI summarization."""

    def __init__(
        self,
        enabled: bool = False,
        provider: str = "gemini",
        base_url: str = "",
        model: str = "",
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        fields: List[str] = None,
    ):
        self.enabled = enabled
        self.provider = provider
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.fields = fields or ["one_sentence_highlight", "core_method"]

    def get_api_key(self) -> str:
        """Get API key from config or environment variable."""
        if self.api_key:
            return self.api_key

        if self.api_key_env:
            key = os.getenv(self.api_key_env)
            if key:
                return key
            raise ValueError(f"API key not found in environment: {self.api_key_env}")

        raise ValueError("No API key configured")


class PaperSummarizer:
    """Generates AI-powered summaries for papers."""

    def __init__(self, config: SummarizerConfig):
        """
        Initialize summarizer with configuration.

        Args:
            config: SummarizerConfig object
        """
        self.config = config

        if config.enabled:
            # Initialize OpenAI-compatible client
            api_key = config.get_api_key()
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url=config.base_url,
            )
            logger.info(f"Initialized summarizer with provider: {config.provider}")
        else:
            self.client = None
            logger.info("Summarization disabled")

    def summarize_papers(self, papers: List[Paper]) -> List[Paper]:
        """
        Generate summaries for a list of papers.

        Args:
            papers: List of Paper objects

        Returns:
            List of Paper objects with summaries added
        """
        if not self.config.enabled:
            logger.info("Summarization disabled, skipping")
            return papers

        for i, paper in enumerate(papers):
            logger.info(f"Summarizing paper {i+1}/{len(papers)}: {paper.title}")

            try:
                summary = self._generate_summary(paper)
                paper.summary = summary
            except Exception as e:
                logger.error(f"Error summarizing paper {paper.arxiv_id}: {e}")
                paper.summary = {"error": str(e)}

        return papers

    def _generate_summary(self, paper: Paper) -> Dict[str, str]:
        """
        Generate summary for a single paper.

        Args:
            paper: Paper object

        Returns:
            Dictionary with summary fields
        """
        prompt = self._build_prompt(paper)

        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a research assistant helping to summarize academic papers.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.3,
            )

            content = response.choices[0].message.content
            summary = self._parse_summary(content)

            logger.debug(f"Generated summary for {paper.arxiv_id}")
            return summary

        except Exception as e:
            logger.error(f"Error calling LLM API: {e}")
            raise

    def _build_prompt(self, paper: Paper) -> str:
        """
        Build the prompt for summarization.

        Args:
            paper: Paper object

        Returns:
            Prompt string
        """
        fields_desc = ", ".join(self.config.fields)

        prompt = f"""Please summarize the following research paper.

Title: {paper.title}

Abstract: {paper.abstract}

Provide the following information:
{self._format_field_instructions()}

Format your response as:
FIELD_NAME: content
"""
        return prompt

    def _format_field_instructions(self) -> str:
        """Format instructions for each summary field."""
        instructions = {
            "one_sentence_highlight": "- ONE_SENTENCE_HIGHLIGHT: A single sentence capturing the main contribution",
            "core_method": "- CORE_METHOD: The key technical approach or methodology (1-2 sentences)",
            "key_contributions": "- KEY_CONTRIBUTIONS: Main contributions as bullet points",
        }

        lines = []
        for field in self.config.fields:
            if field in instructions:
                lines.append(instructions[field])

        return "\n".join(lines)

    def _parse_summary(self, content: str) -> Dict[str, str]:
        """
        Parse the LLM response into a structured summary.

        Args:
            content: Raw LLM response

        Returns:
            Dictionary with parsed fields
        """
        summary = {}

        # Simple line-based parsing
        for line in content.split("\n"):
            line = line.strip()
            if ":" in line:
                # Split on first colon
                parts = line.split(":", 1)
                if len(parts) == 2:
                    key = parts[0].strip().lower().replace(" ", "_")
                    value = parts[1].strip()
                    summary[key] = value

        return summary


class GLMSummarizer(PaperSummarizer):
    """Summarizer using GLM (Zhipu AI) models."""

    def __init__(self, config: SummarizerConfig):
        super().__init__(config)


class GeminiSummarizer(PaperSummarizer):
    """Summarizer using Google Gemini models with search capabilities."""

    def __init__(self, config: SummarizerConfig):
        super().__init__(config)


def create_summarizer(config: SummarizerConfig) -> PaperSummarizer:
    """
    Factory to create a summarizer instance based on provider.

    The current implementation uses OpenAI-compatible APIs for all providers.
    Provider-specific subclasses are thin wrappers kept for future extension.
    """
    provider = (config.provider or "").strip().lower()
    if provider == "glm":
        return GLMSummarizer(config)
    if provider == "gemini":
        return GeminiSummarizer(config)
    return PaperSummarizer(config)
