"""Notification helpers for pushing 论文摘要到外部渠道."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional

import requests

from .models import Paper

logger = logging.getLogger(__name__)


class NotificationError(RuntimeError):
    """Raised when通知发送失败."""


@dataclass
class NotificationConfig:
    """High-level notification配置."""

    enabled: bool = False
    provider: str = ""
    top_k: int = 5
    feishu_webhook: Optional[str] = None
    feishu_secret: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    wechat_app_id: Optional[str] = None
    wechat_app_secret: Optional[str] = None
    wechat_open_id: Optional[str] = None
    # 增强选项
    include_abstract: bool = False  # 是否包含摘要
    use_rich_format: bool = True    # 是否使用富文本/卡片格式


def build_notifier(config: NotificationConfig):
    """Create notifier instance based on provider配置."""

    provider = (config.provider or "").lower()

    if not config.enabled or not provider:
        logger.info("Notification disabled or provider missing,跳过推送")
        return None

    if provider == "feishu":
        if not config.feishu_webhook:
            raise NotificationError("Feishu 推送需要配置 webhook_url")
        return FeishuNotifier(
            config.feishu_webhook,
            config.feishu_secret,
            config.top_k,
            use_card=config.use_rich_format,
            include_abstract=config.include_abstract,
        )

    if provider == "telegram":
        if not config.telegram_bot_token or not config.telegram_chat_id:
            raise NotificationError("Telegram 推送需要配置 bot_token 和 chat_id")
        return TelegramNotifier(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
            top_k=config.top_k,
            use_markdown=config.use_rich_format,
            include_abstract=config.include_abstract,
        )

    if provider == "wechat":
        missing = [
            name
            for name, value in {
                "app_id": config.wechat_app_id,
                "app_secret": config.wechat_app_secret,
                "open_id": config.wechat_open_id,
            }.items()
            if not value
        ]
        if missing:
            raise NotificationError(
                f"WeChat 推送缺少配置: {', '.join(missing)}"
            )
        return WeChatNotifier(
            app_id=config.wechat_app_id,
            app_secret=config.wechat_app_secret,
            open_id=config.wechat_open_id,
            top_k=config.top_k,
            use_news=config.use_rich_format,
            include_abstract=config.include_abstract,
        )

    raise NotificationError(f"未知通知渠道: {config.provider}")


def _format_paper_digest(papers: Iterable[Paper], limit: int) -> str:
    """将论文列表压缩为多行文本."""

    lines = []
    for idx, paper in enumerate(papers, start=1):
        if idx > limit:
            break
        keywords = ", ".join(paper.matched_keywords) or "无关键词"
        line = (
            f"{idx}. {paper.title}\n"
            f"分数: {paper.score:.1f} 关键词: {keywords}\n"
            f"链接: {paper.entry_url}"
        )
        lines.append(line)

    return "\n\n".join(lines) if lines else "今日暂无符合条件的论文。"


def _truncate_text(text: str, max_length: int = 200) -> str:
    """截断文本到指定长度."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def _escape_telegram_markdown(text: str) -> str:
    """转义 Telegram MarkdownV2 特殊字符."""
    # MarkdownV2 需要转义的字符: _ * [ ] ( ) ~ ` > # + - = | { } . !
    special_chars = r'_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def _get_papers_stats(papers: List[Paper]) -> dict:
    """获取论文统计信息."""
    if not papers:
        return {"count": 0, "avg_score": 0, "min_score": 0, "max_score": 0}

    scores = [p.score for p in papers if p.score is not None]
    return {
        "count": len(papers),
        "avg_score": sum(scores) / len(scores) if scores else 0,
        "min_score": min(scores) if scores else 0,
        "max_score": max(scores) if scores else 0,
    }


class BaseNotifier:
    """统一的通知基类,负责生成正文."""

    provider_name: str = "base"

    def __init__(self, top_k: int = 5, include_abstract: bool = False):
        self.top_k = top_k
        self.include_abstract = include_abstract

    def send(self, papers: Iterable[Paper]) -> None:
        papers_list = list(papers)[:self.top_k]
        message = _format_paper_digest(papers_list, self.top_k)
        self._send_message(message, papers_list)
        logger.info("%s 推送完成", self.provider_name)

    def _send_message(self, message: str, papers: List[Paper] = None) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class FeishuNotifier(BaseNotifier):
    """飞书群机器人推送 - 支持消息卡片."""

    provider_name = "Feishu"

    def __init__(
        self,
        webhook: str,
        secret: Optional[str],
        top_k: int = 5,
        use_card: bool = True,
        include_abstract: bool = False,
    ):
        super().__init__(top_k, include_abstract)
        self.webhook = webhook
        self.secret = secret
        self.use_card = use_card

    def _build_sign(self) -> tuple[str, str]:
        timestamp = str(int(time.time()))
        if not self.secret:
            return timestamp, ""

        key = self.secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{self.secret}".encode("utf-8")
        hmac_code = hmac.new(key, string_to_sign, digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return timestamp, sign

    def _build_card_payload(self, papers: List[Paper]) -> dict:
        """构建飞书消息卡片 payload - 完整信息版."""
        today = datetime.now().strftime("%Y-%m-%d")
        stats = _get_papers_stats(papers)

        # 构建论文元素列表
        elements = []

        # 统计信息
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"📊 **今日推荐 {len(papers)} 篇** | 平均分: {stats['avg_score']:.1f} | 分数范围: {stats['min_score']:.1f}-{stats['max_score']:.1f}"
            }
        })

        elements.append({"tag": "hr"})

        # 论文列表
        for idx, paper in enumerate(papers, start=1):
            # 分数 emoji
            if paper.score >= 5:
                score_emoji = "🔥"
                score_label = "高度匹配"
            elif paper.score >= 3:
                score_emoji = "⭐"
                score_label = "中度匹配"
            else:
                score_emoji = "📄"
                score_label = "一般匹配"

            # 标题
            content = f"{score_emoji} **{idx}. {paper.title}**\n\n"

            # 分数详情
            content += f"**匹配分数:** `{paper.score:.1f}` ({score_label})\n"

            # 关键词
            if paper.matched_keywords:
                keywords = ", ".join(paper.matched_keywords[:5])
                content += f"**命中关键词:** {keywords}\n"

            # 作者
            if paper.authors:
                authors = ", ".join(paper.authors[:3])
                if len(paper.authors) > 3:
                    authors += f" 等 {len(paper.authors)} 人"
                content += f"**作者:** {authors}\n"

            # 分类
            if paper.primary_category:
                categories = paper.primary_category
                if paper.categories and len(paper.categories) > 1:
                    other_cats = [c for c in paper.categories[:3] if c != paper.primary_category]
                    if other_cats:
                        categories += f" ({', '.join(other_cats)})"
                content += f"**分类:** {categories}\n"

            # 发布日期
            if paper.published:
                pub_date = paper.published.strftime("%Y-%m-%d") if hasattr(paper.published, 'strftime') else str(paper.published)[:10]
                content += f"**发布日期:** {pub_date}\n"

            content += "\n"

            # 摘要 (可选)
            if self.include_abstract and paper.abstract:
                abstract = _truncate_text(paper.abstract, 300)
                content += f"**摘要:**\n{abstract}\n\n"

            # AI 生成的摘要/亮点 (如果有)
            if hasattr(paper, 'summary') and paper.summary:
                if isinstance(paper.summary, dict):
                    if paper.summary.get('one_sentence_highlight'):
                        content += f"**💡 一句话亮点:** {paper.summary['one_sentence_highlight']}\n"
                    if paper.summary.get('core_method'):
                        content += f"**🔧 核心方法:** {paper.summary['core_method']}\n"
                elif isinstance(paper.summary, str):
                    content += f"**💡 AI 摘要:** {paper.summary}\n"
                content += "\n"

            # 链接
            content += f"[📄 arXiv 页面]({paper.entry_url})"
            if paper.pdf_url:
                content += f"  |  [📥 PDF 下载]({paper.pdf_url})"

            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": content
                }
            })

            if idx < len(papers):
                elements.append({"tag": "hr"})

        # 底部说明
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"🤖 arXiv Paper Bot | {today} | 关键词过滤 + AI 评分"
                }
            ]
        })

        card = {
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": f"📚 arXiv 论文日报 ({today})"
                }
            },
            "elements": elements
        }

        return card

    def _send_message(self, message: str, papers: List[Paper] = None) -> None:
        timestamp, sign = self._build_sign()

        if self.use_card and papers:
            # 使用消息卡片格式
            card = self._build_card_payload(papers)
            payload = {
                "timestamp": timestamp,
                "sign": sign,
                "msg_type": "interactive",
                "card": card,
            }
        else:
            # 使用纯文本格式
            payload = {
                "timestamp": timestamp,
                "sign": sign,
                "msg_type": "text",
                "content": {"text": message},
            }

        response = requests.post(self.webhook, json=payload, timeout=10)
        _raise_for_status(response)

        # 检查飞书返回的错误码
        data = response.json()
        if data.get("code") != 0:
            raise NotificationError(f"飞书发送失败: {data}")


class TelegramNotifier(BaseNotifier):
    """Telegram Bot 推送 - 支持 MarkdownV2 格式."""

    provider_name = "Telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        top_k: int = 5,
        use_markdown: bool = True,
        include_abstract: bool = False,
    ):
        super().__init__(top_k, include_abstract)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.use_markdown = use_markdown

    def _build_markdown_message(self, papers: List[Paper]) -> str:
        """构建 Telegram MarkdownV2 格式消息."""
        today = datetime.now().strftime("%Y\\-%-m\\-%d")
        stats = _get_papers_stats(papers)

        lines = []
        lines.append(f"📚 *arXiv 论文日报* \\({today}\\)")
        lines.append("")
        lines.append(
            f"📊 今日推荐 *{len(papers)}* 篇 \\| "
            f"平均分: {stats['avg_score']:.1f} \\| "
            f"范围: {stats['min_score']:.1f}\\-{stats['max_score']:.1f}"
        )
        lines.append("─" * 20)

        for idx, paper in enumerate(papers, start=1):
            keywords = ", ".join(paper.matched_keywords[:3]) if paper.matched_keywords else "无关键词"
            score_emoji = "🔥" if paper.score >= 5 else "⭐" if paper.score >= 3 else "📄"

            # 转义标题中的特殊字符
            title_escaped = _escape_telegram_markdown(paper.title)

            lines.append(f"{score_emoji} *{idx}\\. {title_escaped}*")
            lines.append(f"分数: `{paper.score:.1f}` \\| 关键词: {_escape_telegram_markdown(keywords)}")

            if self.include_abstract and paper.abstract:
                abstract = _truncate_text(paper.abstract, 120)
                lines.append(f"_{_escape_telegram_markdown(abstract)}_")

            # 链接
            lines.append(f"[📎 查看论文]({paper.entry_url})")
            lines.append("")

        lines.append("🤖 _arXiv Paper Bot_")

        return "\n".join(lines)

    def _send_message(self, message: str, papers: List[Paper] = None) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        if self.use_markdown and papers:
            markdown_message = self._build_markdown_message(papers)
            payload = {
                "chat_id": self.chat_id,
                "text": markdown_message,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            }
        else:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "disable_web_page_preview": True,
            }

        response = requests.post(url, json=payload, timeout=10)
        _raise_for_status(response)

        # 检查 Telegram 返回的错误
        data = response.json()
        if not data.get("ok"):
            raise NotificationError(f"Telegram 发送失败: {data}")


class WeChatNotifier(BaseNotifier):
    """微信公众号客服消息推送 - 支持图文消息."""

    provider_name = "WeChat"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        open_id: str,
        top_k: int = 5,
        use_news: bool = True,
        include_abstract: bool = False,
    ):
        super().__init__(top_k, include_abstract)
        self.app_id = app_id
        self.app_secret = app_secret
        self.open_id = open_id
        self.use_news = use_news

    def _fetch_access_token(self) -> str:
        token_url = (
            "https://api.weixin.qq.com/cgi-bin/token"
            "?grant_type=client_credential"
            f"&appid={self.app_id}"
            f"&secret={self.app_secret}"
        )

        response = requests.get(token_url, timeout=10)
        _raise_for_status(response)
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise NotificationError(f"获取 access_token 失败: {data}")
        return token

    def _build_news_payload(self, papers: List[Paper]) -> dict:
        """构建图文消息 payload (最多8条)."""
        articles = []

        for paper in papers[:8]:  # 微信限制最多8条
            # 构建描述
            keywords = ", ".join(paper.matched_keywords[:3]) if paper.matched_keywords else ""
            description = f"分数: {paper.score:.1f}"
            if keywords:
                description += f" | 关键词: {keywords}"
            if self.include_abstract and paper.abstract:
                description += f"\n{_truncate_text(paper.abstract, 100)}"

            articles.append({
                "title": paper.title,
                "description": description,
                "url": paper.entry_url,
                "picurl": "",  # 可选：论文封面图 URL
            })

        return {
            "touser": self.open_id,
            "msgtype": "news",
            "news": {
                "articles": articles
            }
        }

    def _send_message(self, message: str, papers: List[Paper] = None) -> None:
        access_token = self._fetch_access_token()
        url = (
            "https://api.weixin.qq.com/cgi-bin/message/custom/send"
            f"?access_token={access_token}"
        )

        if self.use_news and papers:
            # 使用图文消息格式
            payload = self._build_news_payload(papers)
        else:
            # 使用纯文本格式
            payload = {
                "touser": self.open_id,
                "msgtype": "text",
                "text": {"content": message},
            }

        response = requests.post(url, json=payload, timeout=10)
        _raise_for_status(response)
        data = response.json()
        if data.get("errcode") != 0:
            raise NotificationError(f"微信发送失败: {data}")


def _raise_for_status(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - requests封装
        raise NotificationError(f"HTTP 请求失败: {exc}") from exc
