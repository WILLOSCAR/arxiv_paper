"""API client for LLM providers (OpenRouter, OpenAI compatible)."""

import logging
import os
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


class APIClient:
    """Base API client for OpenAI-compatible APIs."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize API client.

        Args:
            base_url: API base URL
            api_key: API key (optional if api_key_env provided)
            api_key_env: Environment variable name for API key
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Resolve API key
        if api_key:
            self.api_key = api_key
        elif api_key_env:
            self.api_key = os.getenv(api_key_env)
            if not self.api_key:
                logger.warning(f"API key not found in environment: {api_key_env}")
        else:
            self.api_key = None

        self.headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def chat_completion(
        self,
        model: str,
        messages: List[dict],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        **kwargs,
    ) -> dict:
        """
        Call chat completion API.

        Args:
            model: Model ID
            messages: List of message dicts with role and content
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters

        Returns:
            API response dictionary
        """
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        logger.debug(f"Calling {url} with model {model}")

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()

            logger.debug(f"API call successful, usage: {result.get('usage', {})}")
            return result

        except requests.exceptions.Timeout:
            logger.error(f"API request timeout after {self.timeout}s")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"API HTTP error: {e}")
            # Try to get error details from response
            try:
                error_detail = response.json()
                logger.error(f"Error details: {error_detail}")
            except Exception:
                pass
            raise
        except Exception as e:
            logger.error(f"API request failed: {e}")
            raise

    def get_content(self, response: dict) -> str:
        """
        Extract content from API response.

        Args:
            response: API response dictionary

        Returns:
            Content string from first choice
        """
        choices = response.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""


class OpenRouterClient(APIClient):
    """Client for OpenRouter API with free model support."""

    BASE_URL = "https://openrouter.ai/api/v1"
    FRONTEND_API_URL = "https://openrouter.ai/api/frontend/models/find"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_key_env: str = "OPENROUTER_API_KEY",
        timeout: int = 30,
    ):
        """
        Initialize OpenRouter client.

        Args:
            api_key: API key (optional)
            api_key_env: Environment variable for API key
            timeout: Request timeout
        """
        super().__init__(
            base_url=self.BASE_URL,
            api_key=api_key,
            api_key_env=api_key_env,
            timeout=timeout,
        )

        # Add OpenRouter-specific headers
        self.headers["HTTP-Referer"] = "https://github.com/arxiv-paper-bot"
        self.headers["X-Title"] = "arXiv Paper Bot"

    @classmethod
    def get_free_models(cls, limit: int = 10) -> List[dict]:
        """
        Get list of free models from OpenRouter.

        Args:
            limit: Maximum number of models to return

        Returns:
            List of model info dictionaries
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://openrouter.ai/models?q=free",
            "Origin": "https://openrouter.ai",
        }

        try:
            response = requests.get(
                cls.FRONTEND_API_URL,
                params={"fmt": "cards", "q": "free"},
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            models = data.get("data", {}).get("models", [])
            if not isinstance(models, list):
                models = data.get("data", [])

            # Extract free models
            free_models = []
            for m in models:
                endpoint = m.get("endpoint") or {}
                pricing = endpoint.get("pricing") or {}

                is_free = endpoint.get("is_free") or (
                    pricing.get("prompt") == "0" and pricing.get("completion") == "0"
                )

                if not is_free:
                    continue

                model_id = (
                    endpoint.get("model_variant_slug")
                    or endpoint.get("model_variant_permaslug")
                    or endpoint.get("preferred_model_provider_slug")
                    or m.get("slug")
                    or m.get("id")
                )

                free_models.append({
                    "id": model_id,
                    "name": m.get("name"),
                    "context_length": endpoint.get("context_length") or m.get("context_length"),
                })

                if len(free_models) >= limit:
                    break

            logger.info(f"Found {len(free_models)} free models")
            return free_models

        except Exception as e:
            logger.error(f"Failed to fetch free models: {e}")
            return []

    @classmethod
    def get_recommended_free_model(cls) -> str:
        """
        Get recommended free model ID.

        Returns:
            Model ID string
        """
        # Default recommended free models (fallback)
        recommended = [
            "google/gemini-2.0-flash-exp:free",
            "google/gemma-2-9b-it:free",
            "meta-llama/llama-3.1-8b-instruct:free",
        ]

        # Try to get fresh list
        free_models = cls.get_free_models(limit=5)
        if free_models:
            return free_models[0]["id"]

        return recommended[0]


def create_client(
    provider: str = "openrouter",
    **kwargs,
) -> APIClient:
    """
    Factory function to create API client.

    Args:
        provider: Provider name ("openrouter", "openai", etc.)
        **kwargs: Additional arguments for client

    Returns:
        Configured API client
    """
    if provider == "openrouter":
        return OpenRouterClient(**kwargs)
    elif provider == "openai":
        return APIClient(
            base_url="https://api.openai.com/v1",
            api_key_env=kwargs.get("api_key_env", "OPENAI_API_KEY"),
            **{k: v for k, v in kwargs.items() if k != "api_key_env"},
        )
    else:
        # Generic OpenAI-compatible API
        base_url = kwargs.pop("base_url", "https://api.openai.com/v1")
        return APIClient(base_url=base_url, **kwargs)
