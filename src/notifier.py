"""Notification helpers for pushing paper digests to external channels."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

import requests

from .models import Paper
from .secrets import resolve_secret

logger = logging.getLogger(__name__)


FEISHU_CARD_SAFE_BYTES = 25_000


class NotificationError(RuntimeError):
    """Raised when notification delivery fails."""


@dataclass
class NotificationConfig:
    """High-level notification configuration."""

    enabled: bool = False
    provider: str = ""
    top_k: int = 5
    feishu_webhook: Optional[str] = None
    feishu_webhook_file: Optional[str] = None
    feishu_secret: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    wechat_app_id: Optional[str] = None
    wechat_app_secret: Optional[str] = None
    wechat_open_id: Optional[str] = None
    # Enhanced options
    include_abstract: bool = False  # Include abstract text
    use_rich_format: bool = True  # Use rich format (card/markdown)
    card_style: str = "magazine"
    abstract_preview_chars: int = 220
    show_authors: bool = True
    show_keywords: bool = True
    show_reason: bool = True
    show_score_badge: bool = True


def build_notifier(config: NotificationConfig):
    """Create notifier instance based on provider config."""

    provider = (config.provider or "").lower()

    if not config.enabled or not provider:
        logger.info("Notification disabled or provider missing, skipping push")
        return None

    if provider == "feishu":
        try:
            webhook = resolve_secret(
                value=config.feishu_webhook,
                file_path=config.feishu_webhook_file,
                required=True,
                name="Feishu webhook_url",
            )
        except Exception as exc:
            raise NotificationError("Feishu requires webhook_url or webhook_file") from exc
        return FeishuNotifier(
            webhook,
            config.feishu_secret,
            config.top_k,
            use_card=config.use_rich_format,
            include_abstract=config.include_abstract,
            card_style=config.card_style,
            abstract_preview_chars=config.abstract_preview_chars,
            show_authors=config.show_authors,
            show_keywords=config.show_keywords,
            show_reason=config.show_reason,
            show_score_badge=config.show_score_badge,
        )

    if provider == "telegram":
        if not config.telegram_bot_token or not config.telegram_chat_id:
            raise NotificationError("Telegram requires bot_token and chat_id")
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
            raise NotificationError(f"WeChat missing required settings: {', '.join(missing)}")
        return WeChatNotifier(
            app_id=config.wechat_app_id,
            app_secret=config.wechat_app_secret,
            open_id=config.wechat_open_id,
            top_k=config.top_k,
            use_news=config.use_rich_format,
            include_abstract=config.include_abstract,
        )

    raise NotificationError(f"Unknown notification provider: {config.provider}")


def _format_paper_digest(papers: Iterable[Paper], limit: int) -> str:
    """Format paper list into a multiline plain-text digest."""

    lines = []
    for idx, paper in enumerate(papers, start=1):
        if idx > limit:
            break
        keywords = ", ".join(paper.matched_keywords) or "none"
        line = (
            f"{idx}. {paper.title}\n"
            f"Score: {paper.score:.1f} | Keywords: {keywords}\n"
            f"Link: {paper.entry_url}"
        )
        lines.append(line)

    return "\n\n".join(lines) if lines else "No papers matched today."


def _format_daily_topics_digest(grouped_output: dict, per_topic: int = 3) -> str:
    """Fallback plain-text summary for daily topic output."""

    day = grouped_output.get("day") or datetime.now().strftime("%Y-%m-%d")
    timezone_name = grouped_output.get("timezone") or "Asia/Shanghai"
    threshold = grouped_output.get("threshold")
    topics = grouped_output.get("topics") or []

    lines = [f"📚 arXiv Topic Daily ({day}, {timezone_name})"]
    if threshold is not None:
        lines.append(f"Threshold: {float(threshold):.2f}")

    for topic in topics:
        topic_name = str(topic.get("topic") or "Unknown Topic")
        lines.append(f"\n【{topic_name}】")
        papers = topic.get("papers") or []
        if not papers:
            lines.append("- No selected papers today")
            continue

        for idx, paper in enumerate(papers[:per_topic], start=1):
            title = str(paper.get("title") or "Untitled")
            rel = float(paper.get("relevance") or 0.0)
            lines.append(f"- {idx}. {title} (rel={rel:.2f})")
            entry = str(paper.get("entry_url") or "")
            if entry:
                lines.append(f"  {entry}")

    return "\n".join(lines)


def _truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text to max length."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _escape_telegram_markdown(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters."""
    # MarkdownV2 characters that require escaping.
    special_chars = r"_*[]()~`>#+-=|{}.!"
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text


def _get_papers_stats(papers: List[Paper]) -> dict:
    """Compute digest statistics for a paper list."""
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
    """Shared notifier base class."""

    provider_name: str = "base"

    def __init__(self, top_k: int = 5, include_abstract: bool = False):
        self.top_k = top_k
        self.include_abstract = include_abstract

    def send(self, papers: Iterable[Paper]) -> None:
        papers_list = list(papers)[: self.top_k]
        message = _format_paper_digest(papers_list, self.top_k)
        self._send_message(message, papers_list)
        logger.info("%s push completed", self.provider_name)

    def _send_message(self, message: str, papers: List[Paper] = None) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class FeishuNotifier(BaseNotifier):
    """Feishu group bot notifier with card support."""

    provider_name = "Feishu"

    def __init__(
        self,
        webhook: str,
        secret: Optional[str],
        top_k: int = 5,
        use_card: bool = True,
        include_abstract: bool = False,
        card_style: str = "magazine",
        abstract_preview_chars: int = 180,
        show_authors: bool = True,
        show_keywords: bool = True,
        show_reason: bool = True,
        show_score_badge: bool = True,
    ):
        super().__init__(top_k, include_abstract)
        self.webhook = webhook
        self.secret = secret
        self.use_card = use_card
        self.card_style = (card_style or "magazine").strip().lower()
        self.abstract_preview_chars = max(80, int(abstract_preview_chars or 180))
        self.show_authors = show_authors
        self.show_keywords = show_keywords
        self.show_reason = show_reason
        self.show_score_badge = show_score_badge

    def _build_sign(self) -> tuple[str, str]:
        timestamp = str(int(time.time()))
        if not self.secret:
            return timestamp, ""

        key = self.secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{self.secret}".encode("utf-8")
        hmac_code = hmac.new(key, string_to_sign, digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return timestamp, sign

    def _score_badge(self, score: float) -> tuple[str, str]:
        if score >= 5:
            return "🔥", "High match"
        if score >= 3:
            return "⭐", "Medium match"
        return "📄", "Basic match"

    def _format_reason(self, reason: str) -> str:
        reason_text = (reason or "").strip()
        if not reason_text:
            return ""

        lowered = reason_text.lower()
        if lowered.startswith("fallback (llm config error"):
            return "Rule fallback scoring (LLM key/config missing)"
        if lowered.startswith("fallback (llm batch error"):
            return "Rule fallback scoring (LLM batch error)"
        if lowered.startswith("fallback (rule-only"):
            return "Rule-only output (LLM not called)"
        if lowered.startswith("fallback"):
            return "Rule fallback scoring"
        return reason_text

    def _format_recall_hits(self, hits: List[str], *, max_items: int = 4) -> str:
        clean_hits = [str(h).strip() for h in hits if str(h).strip()]
        if not clean_hits:
            return ""
        if len(clean_hits) <= max_items:
            return ", ".join(clean_hits)
        remain = len(clean_hits) - max_items
        return f"{', '.join(clean_hits[:max_items])} +{remain} more"

    def _build_header(self, *, title: str, subtitle: str, template: str = "blue") -> dict:
        return {
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": title},
                "subtitle": {"tag": "plain_text", "content": subtitle},
            },
            "elements": [],
        }

    def _build_stats_block(self, *, total: int, stats: dict) -> dict:
        return {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"📊 **Top {total} papers today** · avg score `{stats['avg_score']:.1f}` "
                    f"· range `{stats['min_score']:.1f} ~ {stats['max_score']:.1f}`"
                ),
            },
        }

    def _build_action_row(
        self,
        *,
        entry_url: str,
        pdf_url: str,
        detail_url: str = "",
    ) -> dict:
        actions = []

        if entry_url:
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "Open arXiv"},
                    "type": "default",
                    "url": entry_url,
                }
            )

        if pdf_url:
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "Open PDF"},
                    "type": "default",
                    "url": pdf_url,
                }
            )

        if detail_url:
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "Details"},
                    "type": "default",
                    "url": detail_url,
                }
            )

        return {"tag": "action", "actions": actions} if actions else {"tag": "hr"}

    def _build_paper_content(self, paper: Paper, *, idx: int, preview_chars: int) -> str:
        score = float(paper.score or 0.0)
        emoji, score_label = self._score_badge(score)

        title_md = f"[{paper.title}]({paper.entry_url})" if paper.entry_url else paper.title
        lines = [f"{emoji} **{idx}. {title_md}**"]

        meta_chunks = [f"ID: `{paper.arxiv_id}`"] if paper.arxiv_id else []
        if self.show_score_badge:
            meta_chunks.append(f"`{score:.1f}` {score_label}")
        if paper.primary_category:
            meta_chunks.append(f"`{paper.primary_category}`")
        if self.show_keywords and paper.matched_keywords:
            meta_chunks.append(f"keywords: {', '.join(paper.matched_keywords[:4])}")
        if meta_chunks:
            lines.append(" · ".join(meta_chunks))

        if self.show_authors and paper.authors:
            authors = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors += f" (+{len(paper.authors) - 3} more)"
            lines.append(f"Authors: {authors}")

        if paper.published:
            pub = paper.published.strftime("%Y-%m-%d") if hasattr(paper.published, "strftime") else str(paper.published)[:10]
            lines.append(f"Published: {pub}")

        extra_meta = []
        if paper.doi:
            extra_meta.append(f"DOI: {paper.doi}")
        if paper.journal_ref:
            extra_meta.append(f"Journal: {_truncate_text(paper.journal_ref, 80)}")
        if extra_meta:
            lines.append(" · ".join(extra_meta))

        if self.include_abstract and paper.abstract:
            lines.append(f"Abstract: {_truncate_text(paper.abstract, preview_chars)}")

        if self.show_reason and paper.summary:
            if isinstance(paper.summary, dict):
                reason = paper.summary.get("one_sentence_highlight") or paper.summary.get("core_method") or ""
                if reason:
                    lines.append(f"Highlight: {_truncate_text(str(reason), preview_chars)}")
            elif isinstance(paper.summary, str):
                lines.append(f"Highlight: {_truncate_text(paper.summary, preview_chars)}")

        return "\n".join(lines)

    def _build_card_payload(self, papers: List[Paper], *, preview_chars: int) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        stats = _get_papers_stats(papers)

        card = self._build_header(
            title=f"📚 arXiv Paper Daily ({today})",
            subtitle="Magazine Card · quick scan + deep links",
            template="blue",
        )
        elements = card["elements"]
        elements.append(self._build_stats_block(total=len(papers), stats=stats))
        elements.append({"tag": "hr"})

        for idx, paper in enumerate(papers, start=1):
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": self._build_paper_content(paper, idx=idx, preview_chars=preview_chars),
                    },
                }
            )
            elements.append(
                self._build_action_row(
                    entry_url=paper.entry_url,
                    pdf_url=paper.pdf_url,
                )
            )
            if idx < len(papers):
                elements.append({"tag": "hr"})

        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"🤖 arXiv Paper Bot | {today} | keyword recall + agent scoring",
                    }
                ],
            }
        )
        return card

    def _build_daily_topics_card_payload(
        self,
        grouped_output: dict,
        *,
        per_topic: int,
        include_empty_topics: bool,
        abstract_chars: int,
        reason_chars: int,
        include_reason: bool,
        include_abstract: bool,
    ) -> dict:
        day = grouped_output.get("day") or datetime.now().strftime("%Y-%m-%d")
        timezone_name = grouped_output.get("timezone") or "Asia/Shanghai"
        threshold = grouped_output.get("threshold")
        topics = grouped_output.get("topics") or []

        total_kept = sum(int(topic.get("count") or 0) for topic in topics)
        card_part = grouped_output.get("card_part")
        card_total = grouped_output.get("card_total")
        part_suffix = f" | Card {card_part}/{card_total}" if card_part and card_total else ""

        card = self._build_header(
            title=f"arXiv Topic Daily ({day}){part_suffix}",
            subtitle=f"{timezone_name} | 7 topics | up to {per_topic} papers/topic",
            template="wathet",
        )
        elements = card["elements"]

        threshold_text = f"{float(threshold):.2f}" if threshold is not None else "N/A"
        llm_enabled = grouped_output.get("llm_enabled")
        if llm_enabled is False:
            llm_mode = "Rule fallback"
        elif llm_enabled is True:
            llm_mode = "LLM adjudication"
        else:
            llm_mode = "Unknown"

        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"📊 **Selected {total_kept} papers** | threshold `{threshold_text}` | mode `{llm_mode}`"
                    ),
                },
            }
        )
        if llm_enabled is False:
            elements.append(
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "LLM is unavailable. The card uses rule fallback scoring.",
                        }
                    ],
                }
            )
        elements.append({"tag": "hr"})

        for topic in topics:
            topic_id = topic.get("topic_id", "-")
            topic_name = str(topic.get("topic") or "Unknown Topic")
            topic_count = int(topic.get("count") or 0)
            papers = topic.get("papers") or []

            if topic_count == 0 and not include_empty_topics:
                continue

            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📂 Topic {topic_id}: {topic_name} ({topic_count})**",
                    },
                }
            )

            if not papers:
                elements.append(
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": "- No selected papers today."},
                    }
                )
                elements.append({"tag": "hr"})
                continue

            topic_slice = papers[:per_topic]
            for idx, paper in enumerate(topic_slice, start=1):
                relevance = float(paper.get("relevance") or 0.0)
                confidence = float(paper.get("confidence") or 0.0)
                title = str(paper.get("title") or "Untitled")
                subtopic = str(paper.get("subtopic") or "")
                reason = str(paper.get("reason") or "")
                one_sentence_summary = str(paper.get("one_sentence_summary") or "")
                paper_id = str(paper.get("paper_id") or paper.get("arxiv_id") or "")
                primary_category = str(paper.get("primary_category") or "")
                categories = [str(c) for c in (paper.get("categories") or []) if c]
                authors = [str(a) for a in (paper.get("authors") or []) if a]
                published = str(paper.get("published") or "")
                updated = str(paper.get("updated") or "")
                abstract = str(paper.get("abstract") or "")
                doi = str(paper.get("doi") or "")
                journal_ref = str(paper.get("journal_ref") or "")
                comment = str(paper.get("comment") or "")
                topic_of_paper = str(paper.get("topic") or topic_name)
                entry_url = str(paper.get("entry_url") or "")
                pdf_url = str(paper.get("pdf_url") or "")
                recall_hits = [str(h) for h in (paper.get("recall_hits") or []) if h]
                recall_hit_count = int(paper.get("recall_hit_count") or len(recall_hits))

                title_md = f"[{title}]({entry_url})" if entry_url else title
                lines = [f"**{idx}. {title_md}**"]

                meta_line = [
                    f"`🆔 {paper_id or 'N/A'}`",
                    f"`🎯 Rel {relevance:.2f}`",
                    f"`🔒 Conf {confidence:.2f}`",
                    f"`🏷️ {primary_category or 'N/A'}`",
                ]
                lines.append(" | ".join(meta_line))
                lines.append("📌 **Routing**")
                lines.append(f"- **Topic:** `{topic_id}` {topic_of_paper}")
                lines.append(f"- **Subtopic:** {subtopic or 'Unspecified'}")

                lines.append("🔗 **Source** · Use the title link above")

                lines.append("")
                lines.append("🧠 **LLM Judgment**")

                if one_sentence_summary:
                    lines.append(f"- **1-sentence summary:** {one_sentence_summary}")

                if include_reason and self.show_reason:
                    formatted_reason = self._format_reason(reason)
                    if formatted_reason:
                        lines.append(f"- **Rationale:** {_truncate_text(formatted_reason, reason_chars)}")

                lines.append("")
                lines.append("📚 **Paper Info**")

                if self.show_authors:
                    author_text = ", ".join(authors[:4]) if authors else "N/A"
                    if authors and len(authors) > 4:
                        author_text += f" (+{len(authors) - 4} more)"
                    lines.append(f"- **Authors:** {author_text}")

                category_text = ", ".join(categories) if categories else "N/A"
                pub_text = published[:10] if published else "N/A"
                upd_text = updated[:10] if updated else "N/A"
                lines.append(f"- **Categories:** {category_text}")
                lines.append(f"- **Published / Updated:** {pub_text} / {upd_text}")

                journal_text = _truncate_text(journal_ref, 120) if journal_ref else "N/A"
                comment_text = _truncate_text(comment, 140) if comment else "N/A"
                lines.append(f"- **DOI / Journal / Comment:** {doi or 'N/A'} | {journal_text} | {comment_text}")

                if self.show_keywords:
                    hit_text = ", ".join(recall_hits) if recall_hits else "none"
                    lines.append(f"- **Recall hits ({recall_hit_count}):** {hit_text}")
                else:
                    lines.append(f"- **Recall hit count:** {recall_hit_count}")

                if include_abstract:
                    lines.append("")
                    if abstract:
                        if abstract_chars > 0:
                            lines.append(f"📝 **Abstract (first {abstract_chars} chars)**")
                            lines.append(_truncate_text(abstract, abstract_chars))
                        else:
                            lines.append("📝 **Abstract (full)**")
                            lines.append(abstract)
                    else:
                        lines.append("📝 **Abstract:** N/A")

                elements.append(
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": "\n".join(lines)},
                    }
                )
                if idx < len(topic_slice):
                    elements.append({"tag": "hr"})

            elements.append({"tag": "hr"})

        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "Tip: Paper title is the only link entry (to avoid duplicate link blocks).",
                    }
                ],
            }
        )
        return card

    def _card_size_bytes(self, card: dict) -> int:
        return len(json.dumps(card, ensure_ascii=False).encode("utf-8"))

    def _build_topk_card_with_fallback(self, papers: List[Paper]) -> Optional[dict]:
        for preview_chars in [self.abstract_preview_chars, 140, 100]:
            card = self._build_card_payload(papers, preview_chars=preview_chars)
            if self._card_size_bytes(card) <= FEISHU_CARD_SAFE_BYTES:
                return card
        return None

    def _build_daily_card_with_fallback(
        self,
        grouped_output: dict,
        *,
        per_topic: int,
        include_empty_topics: bool,
        abstract_preview_chars: int,
    ) -> Optional[dict]:
        include_abstract_default = bool(self.include_abstract)
        if abstract_preview_chars <= 0:
            # Prioritize full abstracts; reduce paper count before truncating abstract text.
            attempts = [
                (per_topic, 0, 140, True, include_abstract_default),
                (max(1, min(per_topic, 2)), 0, 120, True, include_abstract_default),
                (1, 0, 100, True, include_abstract_default),
                (1, 0, 80, False, include_abstract_default),
                (1, 0, 80, False, False),
            ]
        else:
            attempts = [
                (per_topic, abstract_preview_chars, 140, True, include_abstract_default),
                (per_topic, min(160, abstract_preview_chars), 120, True, include_abstract_default),
                (per_topic, min(110, abstract_preview_chars), 100, True, include_abstract_default),
                (max(1, min(per_topic, 2)), min(90, abstract_preview_chars), 90, False, include_abstract_default),
                (max(1, min(per_topic, 2)), 0, 80, False, False),
            ]
        for size, abstract_chars, reason_chars, include_reason, include_abstract in attempts:
            card = self._build_daily_topics_card_payload(
                grouped_output,
                per_topic=size,
                include_empty_topics=include_empty_topics,
                abstract_chars=abstract_chars,
                reason_chars=reason_chars,
                include_reason=include_reason,
                include_abstract=include_abstract,
            )
            if self._card_size_bytes(card) <= FEISHU_CARD_SAFE_BYTES:
                return card
        return None

    def _post_payload(self, payload: dict) -> None:
        response = requests.post(self.webhook, json=payload, timeout=10)
        _raise_for_status(response)

        data = response.json()
        if data.get("code") != 0:
            raise NotificationError(f"Feishu send failed: {data}")

    def _split_grouped_output_for_cards(self, grouped_output: dict, *, num_cards: int = 2) -> List[dict]:
        topics = list(grouped_output.get("topics") or [])
        if not topics or num_cards <= 1:
            return [grouped_output]

        total_topics = len(topics)
        first_size = (total_topics + 1) // 2
        chunks = [topics[:first_size], topics[first_size:]]

        outputs: List[dict] = []
        non_empty_chunks = [chunk for chunk in chunks if chunk]
        total_cards = len(non_empty_chunks)
        for idx, chunk in enumerate(non_empty_chunks, start=1):
            piece = dict(grouped_output)
            piece["topics"] = chunk
            piece["card_part"] = idx
            piece["card_total"] = total_cards
            outputs.append(piece)
        return outputs or [grouped_output]

    def send_daily_topics(
        self,
        grouped_output: dict,
        *,
        per_topic: int = 3,
        include_empty_topics: bool = True,
        abstract_preview_chars: int = 0,
    ) -> None:
        """Send daily 7-topic card."""
        timestamp, sign = self._build_sign()
        if not self.use_card:
            payload = {
                "timestamp": timestamp,
                "sign": sign,
                "msg_type": "text",
                "content": {"text": _format_daily_topics_digest(grouped_output, per_topic=per_topic)},
            }
            self._post_payload(payload)
            logger.info("%s daily topic push completed", self.provider_name)
            return

        requested_abstract_chars = 0 if abstract_preview_chars is None else int(abstract_preview_chars)
        normalized_abstract_chars = 0 if requested_abstract_chars <= 0 else max(80, requested_abstract_chars)

        grouped_parts = self._split_grouped_output_for_cards(grouped_output, num_cards=2)
        for part in grouped_parts:
            card = self._build_daily_card_with_fallback(
                part,
                per_topic=max(1, int(per_topic)),
                include_empty_topics=include_empty_topics,
                abstract_preview_chars=normalized_abstract_chars,
            )

            if card is None:
                payload = {
                    "timestamp": timestamp,
                    "sign": sign,
                    "msg_type": "text",
                    "content": {"text": _format_daily_topics_digest(part, per_topic=2)},
                }
            else:
                payload = {
                    "timestamp": timestamp,
                    "sign": sign,
                    "msg_type": "interactive",
                    "card": card,
                }

            self._post_payload(payload)

        logger.info("%s daily topic push completed", self.provider_name)

    def _send_message(self, message: str, papers: List[Paper] = None) -> None:
        timestamp, sign = self._build_sign()

        if self.use_card and papers:
            card = self._build_topk_card_with_fallback(papers)
            if card is not None:
                payload = {
                    "timestamp": timestamp,
                    "sign": sign,
                    "msg_type": "interactive",
                    "card": card,
                }
            else:
                payload = {
                    "timestamp": timestamp,
                    "sign": sign,
                    "msg_type": "text",
                    "content": {"text": message},
                }
        else:
            payload = {
                "timestamp": timestamp,
                "sign": sign,
                "msg_type": "text",
                "content": {"text": message},
            }

        self._post_payload(payload)


class TelegramNotifier(BaseNotifier):
    """Telegram notifier with MarkdownV2 support."""

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
        """Build Telegram MarkdownV2 message."""
        today = datetime.now().strftime("%Y\\-%-m\\-%d")
        stats = _get_papers_stats(papers)

        lines = []
        lines.append(f"📚 *arXiv Paper Daily* \\({today}\\)")
        lines.append("")
        lines.append(
            f"📊 Top *{len(papers)}* papers \\| "
            f"Avg score: {stats['avg_score']:.1f} \\| "
            f"Range: {stats['min_score']:.1f}\\-{stats['max_score']:.1f}"
        )
        lines.append("─" * 20)

        for idx, paper in enumerate(papers, start=1):
            keywords = ", ".join(paper.matched_keywords[:3]) if paper.matched_keywords else "none"
            score_emoji = "🔥" if paper.score >= 5 else "⭐" if paper.score >= 3 else "📄"

            # Escape special characters in title.
            title_escaped = _escape_telegram_markdown(paper.title)

            lines.append(f"{score_emoji} *{idx}\\. {title_escaped}*")
            lines.append(f"Score: `{paper.score:.1f}` \\| Keywords: {_escape_telegram_markdown(keywords)}")

            if self.include_abstract and paper.abstract:
                abstract = _truncate_text(paper.abstract, 120)
                lines.append(f"_{_escape_telegram_markdown(abstract)}_")

            # Link
            lines.append(f"[📎 Open paper]({paper.entry_url})")
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

        # Validate Telegram API response.
        data = response.json()
        if not data.get("ok"):
            raise NotificationError(f"Telegram send failed: {data}")


class WeChatNotifier(BaseNotifier):
    """WeChat service message notifier with news-card support."""

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
            raise NotificationError(f"Failed to fetch access_token: {data}")
        return token

    def _build_news_payload(self, papers: List[Paper]) -> dict:
        """Build news payload (WeChat limit: 8 items)."""
        articles = []

        for paper in papers[:8]:  # WeChat allows at most 8 items.
            # Build article description.
            keywords = ", ".join(paper.matched_keywords[:3]) if paper.matched_keywords else ""
            description = f"Score: {paper.score:.1f}"
            if keywords:
                description += f" | Keywords: {keywords}"
            if self.include_abstract and paper.abstract:
                description += f"\n{_truncate_text(paper.abstract, 100)}"

            articles.append(
                {
                    "title": paper.title,
                    "description": description,
                    "url": paper.entry_url,
                    "picurl": "",  # Optional cover image URL.
                }
            )

        return {"touser": self.open_id, "msgtype": "news", "news": {"articles": articles}}

    def _send_message(self, message: str, papers: List[Paper] = None) -> None:
        access_token = self._fetch_access_token()
        url = (
            "https://api.weixin.qq.com/cgi-bin/message/custom/send"
            f"?access_token={access_token}"
        )

        if self.use_news and papers:
            # Use news-card payload.
            payload = self._build_news_payload(papers)
        else:
            # Use plain-text payload.
            payload = {
                "touser": self.open_id,
                "msgtype": "text",
                "text": {"content": message},
            }

        response = requests.post(url, json=payload, timeout=10)
        _raise_for_status(response)
        data = response.json()
        if data.get("errcode") != 0:
            raise NotificationError(f"WeChat send failed: {data}")


def _raise_for_status(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - requests wrapper
        raise NotificationError(f"HTTP request failed: {exc}") from exc
