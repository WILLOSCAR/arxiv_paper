"""Tests for notification module."""

from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.models import Paper
from src.notifier import (
    NotificationConfig,
    NotificationError,
    build_notifier,
    _format_paper_digest,
)


_DUMMY_DATETIME = datetime(2024, 1, 1)


def _sample_paper(title: str = "Paper Title", score: float = 3.5) -> Paper:
    return Paper(
        arxiv_id="1234.56789",
        title=title,
        abstract="This is an abstract about transformers and diffusion.",
        authors=["Alice", "Bob"],
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/1234.56789",
        entry_url="https://arxiv.org/abs/1234.56789",
        published=_DUMMY_DATETIME,
        updated=_DUMMY_DATETIME,
        score=score,
        matched_keywords=["transformer"],
    )


class TestNotificationHelpers(TestCase):
    def test_format_digest_empty(self):
        message = _format_paper_digest([], 5)
        self.assertIn("暂无", message)

    def test_format_digest_limit(self):
        papers = [_sample_paper(title=f"Paper {i}") for i in range(10)]
        message = _format_paper_digest(papers, 3)
        self.assertIn("1. Paper 0", message)
        self.assertIn("3. Paper 2", message)
        self.assertNotIn("Paper 3", message)


class TestBuildNotifier(TestCase):
    def test_disabled_returns_none(self):
        config = NotificationConfig(enabled=False)
        notifier = build_notifier(config)
        self.assertIsNone(notifier)

    def test_missing_provider_returns_none(self):
        config = NotificationConfig(enabled=True, provider="")
        notifier = build_notifier(config)
        self.assertIsNone(notifier)

    def test_feishu_requires_webhook(self):
        config = NotificationConfig(enabled=True, provider="feishu")
        with self.assertRaises(NotificationError):
            build_notifier(config)


class TestFeishuNotifier(TestCase):
    @patch("src.notifier.requests.post")
    def test_feishu_send_invokes_http(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"code": 0}  # 飞书成功响应
        mock_post.return_value = mock_response

        config = NotificationConfig(
            enabled=True,
            provider="feishu",
            feishu_webhook="https://example.com/webhook",
            use_rich_format=True,  # 测试消息卡片格式
        )
        notifier = build_notifier(config)
        notifier.send([_sample_paper()])

        self.assertTrue(mock_post.called)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["msg_type"], "interactive")  # 消息卡片格式

    @patch("src.notifier.requests.post")
    def test_feishu_send_plain_text(self, mock_post):
        """测试飞书纯文本格式."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"code": 0}
        mock_post.return_value = mock_response

        config = NotificationConfig(
            enabled=True,
            provider="feishu",
            feishu_webhook="https://example.com/webhook",
            use_rich_format=False,  # 纯文本格式
        )
        notifier = build_notifier(config)
        notifier.send([_sample_paper()])

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["msg_type"], "text")


class TestTelegramNotifier(TestCase):
    @patch("src.notifier.requests.post")
    def test_telegram_send_invokes_http(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True}  # Telegram 成功响应
        mock_post.return_value = mock_response

        config = NotificationConfig(
            enabled=True,
            provider="telegram",
            telegram_bot_token="bot-token",
            telegram_chat_id="chat-id",
            use_rich_format=True,  # 测试 Markdown 格式
        )
        notifier = build_notifier(config)
        notifier.send([_sample_paper()])

        mock_post.assert_called_once()
        self.assertIn("sendMessage", mock_post.call_args[0][0])
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["parse_mode"], "MarkdownV2")

    @patch("src.notifier.requests.post")
    def test_telegram_send_plain_text(self, mock_post):
        """测试 Telegram 纯文本格式."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        config = NotificationConfig(
            enabled=True,
            provider="telegram",
            telegram_bot_token="bot-token",
            telegram_chat_id="chat-id",
            use_rich_format=False,  # 纯文本格式
        )
        notifier = build_notifier(config)
        notifier.send([_sample_paper()])

        payload = mock_post.call_args.kwargs["json"]
        self.assertNotIn("parse_mode", payload)


class TestWeChatNotifier(TestCase):
    @patch("src.notifier.requests.post")
    @patch("src.notifier.requests.get")
    def test_wechat_send_invokes_http(self, mock_get, mock_post):
        mock_get_response = MagicMock()
        mock_get_response.raise_for_status.return_value = None
        mock_get_response.json.return_value = {"access_token": "token"}
        mock_get.return_value = mock_get_response

        mock_post_response = MagicMock()
        mock_post_response.raise_for_status.return_value = None
        mock_post_response.json.return_value = {"errcode": 0}
        mock_post.return_value = mock_post_response

        config = NotificationConfig(
            enabled=True,
            provider="wechat",
            wechat_app_id="app",
            wechat_app_secret="secret",
            wechat_open_id="openid",
            use_rich_format=True,  # 测试图文消息格式
        )
        notifier = build_notifier(config)
        notifier.send([_sample_paper()])

        mock_get.assert_called_once()
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["msgtype"], "news")  # 图文消息格式
        self.assertIn("articles", payload["news"])

    @patch("src.notifier.requests.post")
    @patch("src.notifier.requests.get")
    def test_wechat_send_plain_text(self, mock_get, mock_post):
        """测试微信纯文本格式."""
        mock_get_response = MagicMock()
        mock_get_response.raise_for_status.return_value = None
        mock_get_response.json.return_value = {"access_token": "token"}
        mock_get.return_value = mock_get_response

        mock_post_response = MagicMock()
        mock_post_response.raise_for_status.return_value = None
        mock_post_response.json.return_value = {"errcode": 0}
        mock_post.return_value = mock_post_response

        config = NotificationConfig(
            enabled=True,
            provider="wechat",
            wechat_app_id="app",
            wechat_app_secret="secret",
            wechat_open_id="openid",
            use_rich_format=False,  # 纯文本格式
        )
        notifier = build_notifier(config)
        notifier.send([_sample_paper()])

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["msgtype"], "text")
