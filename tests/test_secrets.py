"""Tests for secret resolution helpers and file-backed config fields."""

import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.secrets import mask_secret, resolve_secret
from src.models import Paper
from src.notifier import NotificationConfig, build_notifier


class TestSecrets(TestCase):
    def test_resolve_secret_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=True) as f:
            f.write("super-secret-value\n")
            f.flush()

            resolved = resolve_secret(file_path=f.name, required=True, name="test")
            self.assertEqual(resolved, "super-secret-value")

    def test_mask_secret(self):
        self.assertEqual(mask_secret("abcd", keep_end=4), "****")
        self.assertTrue(mask_secret("abcdef", keep_end=2).endswith("ef"))


class TestNotifierSecrets(TestCase):
    @patch("src.notifier.requests.post")
    def test_feishu_webhook_file_is_used(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"code": 0}
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=True) as f:
            f.write("https://example.com/webhook-from-file\n")
            f.flush()

            config = NotificationConfig(
                enabled=True,
                provider="feishu",
                feishu_webhook_file=f.name,
                use_rich_format=False,
            )
            notifier = build_notifier(config)

            paper = Paper(
                arxiv_id="1234.56789",
                title="Test Paper",
                abstract="Test abstract",
                authors=["Alice"],
                primary_category="cs.AI",
                categories=["cs.AI"],
                pdf_url="https://arxiv.org/pdf/1234.56789",
                entry_url="https://arxiv.org/abs/1234.56789",
                published=None,
                updated=None,
            )
            notifier.send([paper])

            # Ensure HTTP was called with the webhook loaded from file.
            called_url = mock_post.call_args[0][0]
            self.assertEqual(called_url, "https://example.com/webhook-from-file")


class TestAgentConfigSecrets(TestCase):
    def test_agent_config_api_key_file(self):
        from src.agents.config import AgentConfig

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=True) as f:
            f.write("openrouter-key-from-file\n")
            f.flush()

            cfg = AgentConfig.from_dict(
                {
                    "enabled": True,
                    "provider": "openrouter",
                    "api": {
                        "api_key_file": f.name,
                        "api_key_env": "NON_EXISTENT_ENV",
                    },
                }
            )
            self.assertEqual(cfg.get_api_key(), "openrouter-key-from-file")

