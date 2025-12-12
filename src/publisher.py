"""微信公众号图文发布模块 - 将论文发布为公众号文章."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests

from .models import Paper

logger = logging.getLogger(__name__)


class PublishError(RuntimeError):
    """发布错误."""


@dataclass
class PublisherConfig:
    """公众号发布配置."""

    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""

    # 发布选项
    auto_publish: bool = False  # 是否自动发布（否则只保存到草稿箱）
    include_abstract: bool = True  # 是否包含摘要
    include_authors: bool = True  # 是否包含作者

    # 文章模板
    article_author: str = "arXiv Paper Bot"  # 文章作者名
    default_cover: str = ""  # 默认封面图 media_id


class WeChatPublisher:
    """微信公众号发布器."""

    BASE_URL = "https://api.weixin.qq.com/cgi-bin"

    def __init__(self, config: PublisherConfig):
        self.config = config
        self._access_token: Optional[str] = None
        self._token_expires: float = 0

    def _get_access_token(self) -> str:
        """获取 access_token（带缓存）."""
        import time

        if self._access_token and time.time() < self._token_expires:
            return self._access_token

        url = (
            f"{self.BASE_URL}/token"
            f"?grant_type=client_credential"
            f"&appid={self.config.app_id}"
            f"&secret={self.config.app_secret}"
        )

        resp = requests.get(url, timeout=10)
        data = resp.json()

        if "access_token" not in data:
            raise PublishError(f"获取 access_token 失败: {data}")

        self._access_token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 7200) - 300
        return self._access_token

    def upload_image(self, image_path: str) -> str:
        """
        上传图片素材，返回 media_id.

        Args:
            image_path: 图片文件路径

        Returns:
            media_id
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}/material/add_material?access_token={token}&type=image"

        with open(image_path, "rb") as f:
            files = {"media": f}
            resp = requests.post(url, files=files, timeout=30)

        data = resp.json()
        if "media_id" not in data:
            raise PublishError(f"上传图片失败: {data}")

        logger.info(f"图片上传成功: {data['media_id']}")
        return data["media_id"]

    def upload_content_image(self, image_path: str) -> str:
        """
        上传图文内容中的图片，返回 URL.

        用于文章正文中的图片。

        Args:
            image_path: 图片文件路径

        Returns:
            图片 URL
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}/media/uploadimg?access_token={token}"

        with open(image_path, "rb") as f:
            files = {"media": f}
            resp = requests.post(url, files=files, timeout=30)

        data = resp.json()
        if "url" not in data:
            raise PublishError(f"上传内容图片失败: {data}")

        return data["url"]

    def _build_paper_html(self, paper: Paper) -> str:
        """构建单篇论文的 HTML 内容."""
        html_parts = []

        # 分数和关键词
        keywords = ", ".join(paper.matched_keywords[:5]) if paper.matched_keywords else ""
        score_display = f"⭐ 匹配分数: {paper.score:.1f}" if paper.score else ""

        if score_display or keywords:
            html_parts.append(f'<p style="color: #666; font-size: 14px;">')
            if score_display:
                html_parts.append(f"{score_display}")
            if keywords:
                html_parts.append(f" | 关键词: {keywords}")
            html_parts.append("</p>")

        # 作者
        if self.config.include_authors and paper.authors:
            authors = ", ".join(paper.authors[:5])
            if len(paper.authors) > 5:
                authors += " et al."
            html_parts.append(f'<p style="color: #888; font-size: 13px;">👤 {authors}</p>')

        # 摘要
        if self.config.include_abstract and paper.abstract:
            abstract = paper.abstract[:500]
            if len(paper.abstract) > 500:
                abstract += "..."
            html_parts.append(f'<section style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 10px 0;">')
            html_parts.append(f'<p style="font-size: 14px; line-height: 1.8; color: #333;">{abstract}</p>')
            html_parts.append("</section>")

        # arXiv 链接
        html_parts.append(f'<p style="margin-top: 15px;">')
        html_parts.append(f'📄 <a href="{paper.entry_url}">arXiv: {paper.arxiv_id}</a>')
        if paper.pdf_url:
            html_parts.append(f' | <a href="{paper.pdf_url}">PDF 下载</a>')
        html_parts.append("</p>")

        return "\n".join(html_parts)

    def _build_digest_html(self, papers: List[Paper]) -> str:
        """构建论文日报的完整 HTML 内容."""
        today = datetime.now().strftime("%Y-%m-%d")
        html_parts = []

        # 标题区
        html_parts.append(f'<h2 style="text-align: center; color: #333;">📚 arXiv 论文日报</h2>')
        html_parts.append(f'<p style="text-align: center; color: #666;">{today} | 共 {len(papers)} 篇精选论文</p>')
        html_parts.append("<hr/>")

        # 论文列表
        for idx, paper in enumerate(papers, 1):
            html_parts.append(f'<h3>{idx}. {paper.title}</h3>')
            html_parts.append(self._build_paper_html(paper))
            if idx < len(papers):
                html_parts.append("<hr/>")

        # 底部
        html_parts.append('<p style="text-align: center; color: #999; font-size: 12px; margin-top: 30px;">')
        html_parts.append("🤖 由 arXiv Paper Bot 自动生成")
        html_parts.append("</p>")

        return "\n".join(html_parts)

    def create_draft(
        self,
        papers: List[Paper],
        title: Optional[str] = None,
        thumb_media_id: Optional[str] = None,
    ) -> str:
        """
        创建图文草稿.

        Args:
            papers: 论文列表
            title: 文章标题（默认自动生成）
            thumb_media_id: 封面图 media_id

        Returns:
            草稿 media_id
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}/draft/add?access_token={token}"

        today = datetime.now().strftime("%Y-%m-%d")
        if not title:
            title = f"📚 arXiv 论文日报 ({today})"

        content = self._build_digest_html(papers)

        # 摘要
        if papers:
            digest = f"今日精选 {len(papers)} 篇论文：{papers[0].title[:30]}..."
        else:
            digest = "今日暂无精选论文"

        article = {
            "title": title,
            "author": self.config.article_author,
            "digest": digest,
            "content": content,
            "content_source_url": "https://arxiv.org/",
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }

        # 封面图（必填）
        if thumb_media_id:
            article["thumb_media_id"] = thumb_media_id
        elif self.config.default_cover:
            article["thumb_media_id"] = thumb_media_id
        else:
            raise PublishError("缺少封面图 thumb_media_id，请先上传封面图片")

        payload = {"articles": [article]}

        # 发送请求（处理中文编码）
        headers = {"Content-Type": "application/json"}
        resp = requests.post(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            timeout=30,
        )

        data = resp.json()
        if "media_id" not in data:
            raise PublishError(f"创建草稿失败: {data}")

        logger.info(f"草稿创建成功: {data['media_id']}")
        return data["media_id"]

    def publish_draft(self, media_id: str) -> str:
        """
        发布草稿.

        Args:
            media_id: 草稿 media_id

        Returns:
            publish_id
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}/freepublish/submit?access_token={token}"

        payload = {"media_id": media_id}
        resp = requests.post(url, json=payload, timeout=30)

        data = resp.json()
        if data.get("errcode") != 0:
            raise PublishError(f"发布失败: {data}")

        publish_id = data.get("publish_id", "")
        logger.info(f"发布任务提交成功: {publish_id}")
        return publish_id

    def get_publish_status(self, publish_id: str) -> dict:
        """
        查询发布状态.

        Args:
            publish_id: 发布任务 ID

        Returns:
            发布状态信息
        """
        token = self._get_access_token()
        url = f"{self.BASE_URL}/freepublish/get?access_token={token}"

        payload = {"publish_id": publish_id}
        resp = requests.post(url, json=payload, timeout=10)

        return resp.json()

    def publish_papers(
        self,
        papers: List[Paper],
        title: Optional[str] = None,
        thumb_media_id: Optional[str] = None,
    ) -> dict:
        """
        发布论文到公众号.

        Args:
            papers: 论文列表
            title: 文章标题
            thumb_media_id: 封面图 media_id

        Returns:
            {"media_id": ..., "publish_id": ...}
        """
        # 创建草稿
        media_id = self.create_draft(papers, title, thumb_media_id)
        result = {"media_id": media_id, "publish_id": None, "status": "draft"}

        # 自动发布
        if self.config.auto_publish:
            publish_id = self.publish_draft(media_id)
            result["publish_id"] = publish_id
            result["status"] = "publishing"

        return result


def build_publisher(config: dict) -> Optional[WeChatPublisher]:
    """从配置创建发布器."""
    pub_config = config.get("publisher", {})

    if not pub_config.get("enabled"):
        return None

    wechat = pub_config.get("wechat", {})

    return WeChatPublisher(
        PublisherConfig(
            enabled=True,
            app_id=wechat.get("app_id", ""),
            app_secret=wechat.get("app_secret", ""),
            auto_publish=pub_config.get("auto_publish", False),
            include_abstract=pub_config.get("include_abstract", True),
            include_authors=pub_config.get("include_authors", True),
            article_author=pub_config.get("author", "arXiv Paper Bot"),
            default_cover=wechat.get("default_cover", ""),
        )
    )
