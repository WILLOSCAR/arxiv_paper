"""Tests for daily notification wiring in run_daily CLI."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.notifier import FeishuNotifier
from src.pipeline.run_daily import (
    _build_daily_notification_config,
    _load_default_env_files,
    _load_env_file,
    _maybe_send_daily_notification,
    _derive_llm_config,
    main,
)


def test_build_daily_notification_config_fallback_to_global_feishu():
    cfg = {
        "notification": {
            "provider": "feishu",
            "card_style": "magazine",
            "show_authors": True,
            "show_keywords": True,
            "show_reason": True,
            "show_score_badge": True,
            "feishu": {
                "webhook_url": "https://global.example/webhook",
                "webhook_file": "",
                "secret": "abc",
            },
        }
    }
    daily_cfg = {
        "notification": {
            "enabled": True,
            "per_topic": 3,
            # daily feishu left empty on purpose to test fallback
            "feishu": {},
        }
    }

    out = _build_daily_notification_config(cfg, daily_cfg)
    assert out.enabled is True
    assert out.provider == "feishu"
    assert out.feishu_webhook == "https://global.example/webhook"
    assert out.feishu_secret == "abc"
    assert out.top_k == 3


@patch("src.pipeline.run_daily.build_notifier")
def test_maybe_send_daily_notification_calls_feishu_topic_sender(mock_build):
    feishu = FeishuNotifier(
        webhook="https://example.com/webhook",
        secret=None,
        use_card=True,
    )
    feishu.send_daily_topics = MagicMock()
    mock_build.return_value = feishu

    cfg = {"notification": {"provider": "feishu", "feishu": {"webhook_url": "https://example.com/webhook"}}}
    daily_cfg = {"notification": {"enabled": True, "provider": "feishu", "per_topic": 3}}
    output = {"day": "2026-02-06", "topics": []}

    _maybe_send_daily_notification(
        cfg=cfg,
        daily_cfg=daily_cfg,
        output=output,
        force_notify=False,
        disable_notify=False,
        per_topic_override=0,
    )

    feishu.send_daily_topics.assert_called_once()


@patch("src.pipeline.run_daily.build_notifier")
def test_maybe_send_daily_notification_skips_when_disabled(mock_build):
    _maybe_send_daily_notification(
        cfg={},
        daily_cfg={"notification": {"enabled": False}},
        output={"topics": []},
        force_notify=False,
        disable_notify=False,
        per_topic_override=0,
    )
    mock_build.assert_not_called()


def test_load_env_file_sets_variables(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENROUTER_API_KEY=test-key\nEMPTY=\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    loaded = _load_env_file(env_path)

    assert loaded is True
    assert os.getenv("OPENROUTER_API_KEY") == "test-key"


def test_load_default_env_files_reads_project_env(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    config_path = cfg_dir / "config.yaml"
    config_path.write_text("daily: {}\n", encoding="utf-8")

    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    (env_dir / ".env").write_text("OPENROUTER_API_KEY=from-default-env\n", encoding="utf-8")

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    _load_default_env_files(str(config_path))

    assert os.getenv("OPENROUTER_API_KEY") == "from-default-env"


def test_derive_llm_config_includes_batch_retries_and_parallel_workers():
    cfg = {
        "daily": {"llm_batch_retries": 2, "llm_parallel_workers": 4},
        "personalization": {
            "agent": {
                "provider": "openrouter",
                "api": {"api_key_env": "OPENROUTER_API_KEY"},
                "models": {},
            }
        },
    }

    out = _derive_llm_config(cfg)

    assert out["batch_retries"] == 2
    assert out["parallel_workers"] == 4


def test_build_daily_notification_config_keeps_zero_abstract_chars():
    cfg = {"notification": {"provider": "feishu", "abstract_preview_chars": 220, "feishu": {}}}
    daily_cfg = {"notification": {"enabled": True, "abstract_preview_chars": 0, "feishu": {}}}

    out = _build_daily_notification_config(cfg, daily_cfg)

    assert out.abstract_preview_chars == 0


def test_run_daily_requires_llm_key_by_default(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
daily:
  llm_enabled: true
  require_llm: true
personalization:
  agent:
    provider: openrouter
    api:
      api_key_env: NON_EXISTENT_ENV
""",
        encoding="utf-8",
    )

    monkeypatch.delenv("NON_EXISTENT_ENV", raising=False)

    with pytest.raises(SystemExit, match="LLM is required"):
        main(["--config", str(cfg_file), "--day", "2026-02-06"])
