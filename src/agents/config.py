"""Agent configuration class."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..secrets import resolve_secret


@dataclass
class AgentConfig:
    """Configuration for LangGraph Agent Pipeline."""

    # Enable/disable agent
    enabled: bool = False

    # LLM Provider settings
    provider: str = "openrouter"
    model: str = "z-ai/glm-4.5-air:free"  # Default simple model
    temperature: float = 0.3

    # Dual-model support
    # - reasoning_model: For complex tasks (analysis, scoring with deep thinking)
    # - simple_model: For simple tasks (formatting, extraction)
    reasoning_model: str = "tngtech/deepseek-r1t2-chimera:free"
    simple_model: str = "z-ai/glm-4.5-air:free"

    # API settings
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_key_file: Optional[str] = None
    api_key_env: str = "OPENROUTER_API_KEY"
    timeout: int = 60

    # Feature flags
    preference_analysis: bool = True
    dynamic_query_generation: bool = True
    result_validation: bool = True
    recommendation_explain: bool = True

    # Flow control
    max_iterations: int = 2
    confidence_threshold: float = 0.7
    min_feedback_count: int = 3

    # Score weights
    keyword_weight: float = 0.5
    agent_weight: float = 0.5

    # Keywords for Cold-Start mode
    keywords: Dict[str, List[str]] = field(default_factory=dict)

    # Cold-Start settings
    cold_start_enabled: bool = True
    use_config_keywords: bool = True

    # Features list (for backward compatibility)
    features: List[str] = field(default_factory=list)

    def get_api_key(self) -> str:
        """Get API key from config or environment variable."""
        return resolve_secret(
            value=self.api_key,
            env=self.api_key_env,
            file_path=self.api_key_file,
            required=True,
            name="API key",
        )

    def get_model_for_task(self, task_type: str) -> str:
        """
        Get appropriate model based on task type.

        Args:
            task_type: "reasoning" for complex tasks, "simple" for basic tasks

        Returns:
            Model ID string
        """
        if task_type == "reasoning":
            return self.reasoning_model
        return self.simple_model

    @classmethod
    def from_dict(cls, config: dict) -> "AgentConfig":
        """Create AgentConfig from dictionary."""
        api_config = config.get("api", {})
        features_config = config.get("features", {})
        weights_config = config.get("weights", {})
        cold_start_config = config.get("cold_start", {})
        models_config = config.get("models", {})

        # Handle features as dict or list
        if isinstance(features_config, dict):
            features = [k for k, v in features_config.items() if v]
        else:
            features = features_config

        return cls(
            enabled=config.get("enabled", False),
            provider=config.get("provider", "openrouter"),
            model=config.get("model", "z-ai/glm-4.5-air:free"),
            temperature=config.get("temperature", 0.3),
            # Dual-model support
            reasoning_model=models_config.get("reasoning", "tngtech/deepseek-r1t2-chimera:free"),
            simple_model=models_config.get("simple", "z-ai/glm-4.5-air:free"),
            # API settings
            base_url=api_config.get("base_url"),
            api_key=api_config.get("api_key"),
            api_key_file=api_config.get("api_key_file"),
            api_key_env=api_config.get("api_key_env", "OPENROUTER_API_KEY"),
            timeout=api_config.get("timeout", 60),
            preference_analysis=features_config.get("preference_analysis", True)
            if isinstance(features_config, dict)
            else "preference_analysis" in features,
            dynamic_query_generation=features_config.get(
                "dynamic_query_generation", True
            )
            if isinstance(features_config, dict)
            else "dynamic_query_generation" in features,
            result_validation=features_config.get("result_validation", True)
            if isinstance(features_config, dict)
            else "result_validation" in features,
            recommendation_explain=features_config.get("recommendation_explain", True)
            if isinstance(features_config, dict)
            else "recommendation_explain" in features,
            max_iterations=config.get("max_iterations", 2),
            confidence_threshold=config.get("confidence_threshold", 0.7),
            min_feedback_count=config.get("min_feedback_count", 3),
            keyword_weight=weights_config.get("keyword_score", 0.5),
            agent_weight=weights_config.get("agent_score", 0.5),
            keywords=config.get("keywords", {}),
            cold_start_enabled=cold_start_config.get("enabled", True),
            use_config_keywords=cold_start_config.get("use_config_keywords", True),
            features=features,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "reasoning_model": self.reasoning_model,
            "simple_model": self.simple_model,
            "temperature": self.temperature,
            "base_url": self.base_url,
            "api_key_file": self.api_key_file,
            "api_key_env": self.api_key_env,
            "timeout": self.timeout,
            "max_iterations": self.max_iterations,
            "confidence_threshold": self.confidence_threshold,
            "min_feedback_count": self.min_feedback_count,
            "keyword_weight": self.keyword_weight,
            "agent_weight": self.agent_weight,
            "keywords": self.keywords,
            "cold_start_enabled": self.cold_start_enabled,
            "use_config_keywords": self.use_config_keywords,
        }
