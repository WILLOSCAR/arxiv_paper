"""Notification helpers for pushing 论文摘要到外部渠道."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Iterable, Optional

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


def build_notifier(config: NotificationConfig):
    """Create notifier instance based on provider配置."""

    provider = (config.provider or "").lower()

    if not config.enabled or not provider:
        logger.info("Notification disabled or provider missing,跳过推送")
        return None

    if provider == "feishu":
        if not config.feishu_webhook:
            raise NotificationError("Feishu 推送需要配置 webhook_url")
        return FeishuNotifier(config.feishu_webhook, config.feishu_secret, config.top_k)

    if provider == "telegram":
        if not config.telegram_bot_token or not config.telegram_chat_id:
            raise NotificationError("Telegram 推送需要配置 bot_token 和 chat_id")
        return TelegramNotifier(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
            top_k=config.top_k,
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


class BaseNotifier:
    """统一的通知基类,负责生成正文."""

    provider_name: str = "base"

    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    def send(self, papers: Iterable[Paper]) -> None:
        message = _format_paper_digest(papers, self.top_k)
        self._send_message(message)
        logger.info("%s 推送完成", self.provider_name)

    def _send_message(self, message: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class FeishuNotifier(BaseNotifier):
    """飞书群机器人推送."""

    provider_name = "Feishu"

    def __init__(self, webhook: str, secret: Optional[str], top_k: int = 5):
        super().__init__(top_k)
        self.webhook = webhook
        self.secret = secret

    def _build_sign(self) -> tuple[str, str]:
        timestamp = str(int(time.time()))
        if not self.secret:
            return timestamp, ""

        key = self.secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{self.secret}".encode("utf-8")
        hmac_code = hmac.new(key, string_to_sign, digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return timestamp, sign

    def _send_message(self, message: str) -> None:
        timestamp, sign = self._build_sign()
        payload = {
            "timestamp": timestamp,
            "sign": sign,
            "msg_type": "text",
            "content": {"text": message},
        }

        response = requests.post(self.webhook, json=payload, timeout=10)
        _raise_for_status(response)


class TelegramNotifier(BaseNotifier):
    """Telegram Bot 推送."""

    provider_name = "Telegram"

    def __init__(self, bot_token: str, chat_id: str, top_k: int = 5):
        super().__init__(top_k)
        self.bot_token = bot_token
        self.chat_id = chat_id

    def _send_message(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        response = requests.post(url, json=payload, timeout=10)
        _raise_for_status(response)


class WeChatNotifier(BaseNotifier):
    """微信公众号客服消息推送."""

    provider_name = "WeChat"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        open_id: str,
        top_k: int = 5,
    ):
        super().__init__(top_k)
        self.app_id = app_id
        self.app_secret = app_secret
        self.open_id = open_id

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

    def _send_message(self, message: str) -> None:
        access_token = self._fetch_access_token()
        url = (
            "https://api.weixin.qq.com/cgi-bin/message/custom/send"
            f"?access_token={access_token}"
        )
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
