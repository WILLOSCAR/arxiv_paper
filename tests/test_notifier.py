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
    _format_daily_topics_digest,
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
        self.assertIn("No papers matched today.", message)

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


class TestDailyTopicCard(TestCase):
    @patch("src.notifier.requests.post")
    def test_daily_topic_card_send(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"code": 0}
        mock_post.return_value = mock_response

        config = NotificationConfig(
            enabled=True,
            provider="feishu",
            feishu_webhook="https://example.com/webhook",
            use_rich_format=True,
        )
        notifier = build_notifier(config)
        grouped_output = {
            "day": "2026-02-06",
            "timezone": "Asia/Shanghai",
            "threshold": 0.55,
            "llm_enabled": False,
            "topics": [
                {
                    "topic_id": 1,
                    "topic": "LLM/MLLM",
                    "count": 1,
                    "papers": [
                        {
                            "paper_id": "2602.12345",
                            "title": "A Topic Paper",
                            "abstract": "Abstract snippet",
                            "authors": ["Alice", "Bob"],
                            "primary_category": "cs.AI",
                            "categories": ["cs.AI", "cs.CL"],
                            "published": "2026-02-06T01:00:00+08:00",
                            "updated": "2026-02-06T09:00:00+08:00",
                            "doi": "10.1000/test",
                            "journal_ref": "arXiv preprint",
                            "comment": "Code: github.com/example/repo",
                            "recall_hits": ["llm", "alignment"],
                            "recall_hit_count": 2,
                            "relevance": 0.88,
                            "confidence": 0.73,
                            "subtopic": "LLM Fundamentals & Alignment",
                            "reason": "Matches user rubric strongly",
                            "one_sentence_summary": "This paper proposes a practical method for aligned LLM behavior.",
                            "entry_url": "https://arxiv.org/abs/2602.12345",
                            "pdf_url": "https://arxiv.org/pdf/2602.12345",
                        }
                    ],
                }
            ],
        }

        notifier.send_daily_topics(grouped_output, per_topic=3, include_empty_topics=True)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["msg_type"], "interactive")
        self.assertIn("card", payload)
        card_text = "\n".join(
            e.get("text", {}).get("content", "")
            for e in payload["card"].get("elements", [])
            if isinstance(e, dict)
        )
        self.assertIn("2602.12345", card_text)
        self.assertIn("**Authors:** Alice, Bob", card_text)
        self.assertIn("10.1000/test | arXiv preprint | Code: github.com/example/repo", card_text)
        self.assertIn("**Recall hits (2):** llm, alignment", card_text)
        self.assertIn("mode `Rule fallback`", card_text)
        self.assertIn("**1-sentence summary:** This paper proposes a practical method for aligned LLM behavior.", card_text)



    @patch("src.notifier.requests.post")
    def test_daily_topic_card_sends_two_cards_for_topic_chunks(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"code": 0}
        mock_post.return_value = mock_response

        config = NotificationConfig(
            enabled=True,
            provider="feishu",
            feishu_webhook="https://example.com/webhook",
            use_rich_format=True,
        )
        notifier = build_notifier(config)

        grouped_output = {
            "day": "2026-02-06",
            "timezone": "Asia/Shanghai",
            "threshold": 0.55,
            "llm_enabled": True,
            "topics": [
                {"topic_id": 1, "topic": "T1", "count": 0, "papers": []},
                {"topic_id": 2, "topic": "T2", "count": 0, "papers": []},
                {"topic_id": 3, "topic": "T3", "count": 0, "papers": []},
                {"topic_id": 4, "topic": "T4", "count": 0, "papers": []},
                {"topic_id": 5, "topic": "T5", "count": 0, "papers": []},
                {"topic_id": 6, "topic": "T6", "count": 0, "papers": []},
                {"topic_id": 7, "topic": "T7", "count": 0, "papers": []},
            ],
        }

        notifier.send_daily_topics(grouped_output, per_topic=3, include_empty_topics=True)

        assert mock_post.call_count == 2

    @patch("src.notifier.requests.post")
    def test_daily_topic_card_fallback_to_text_when_card_too_large(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"code": 0}
        mock_post.return_value = mock_response

        config = NotificationConfig(
            enabled=True,
            provider="feishu",
            feishu_webhook="https://example.com/webhook",
            use_rich_format=True,
        )
        notifier = build_notifier(config)

        grouped_output = {
            "day": "2026-02-06",
            "timezone": "Asia/Shanghai",
            "topics": [
                {
                    "topic_id": 1,
                    "topic": "LLM/MLLM",
                    "count": 1,
                    "papers": [
                        {
                            "title": "X" * 500,
                            "relevance": 0.88,
                            "confidence": 0.73,
                            "subtopic": "S" * 400,
                            "reason": "R" * 4000,
                            "entry_url": "https://arxiv.org/abs/2602.12345",
                            "pdf_url": "https://arxiv.org/pdf/2602.12345",
                        }
                    ],
                }
            ],
        }

        with patch("src.notifier.FEISHU_CARD_SAFE_BYTES", 100):
            notifier.send_daily_topics(grouped_output, per_topic=3, include_empty_topics=True)

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["msg_type"], "text")


class TestDailyTopicDigest(TestCase):
    def test_daily_topic_digest_basic(self):
        grouped_output = {
            "day": "2026-02-06",
            "timezone": "Asia/Shanghai",
            "threshold": 0.55,
            "topics": [
                {
                    "topic": "LLM/MLLM",
                    "papers": [{"title": "A", "relevance": 0.8, "entry_url": "https://arxiv.org/abs/1"}],
                }
            ],
        }
        txt = _format_daily_topics_digest(grouped_output, per_topic=1)
        self.assertIn("LLM/MLLM", txt)
        self.assertIn("https://arxiv.org/abs/1", txt)


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
