#!/usr/bin/env python3
"""微信公众号发布工具 - 将论文发布为公众号图文文章.

使用方法:
    # 1. 上传封面图片
    python scripts/publish.py upload-cover path/to/cover.jpg

    # 2. 发布论文到草稿箱
    python scripts/publish.py publish --cover MEDIA_ID

    # 3. 发布并自动推送
    python scripts/publish.py publish --cover MEDIA_ID --auto

    # 4. 从 JSON 文件发布
    python scripts/publish.py publish --cover MEDIA_ID --input data/papers.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Paper
from src.publisher import WeChatPublisher, PublisherConfig, PublishError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """加载配置文件."""
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_publisher(config: dict) -> WeChatPublisher:
    """创建发布器实例."""
    pub_config = config.get("publisher", {})
    wechat = pub_config.get("wechat", {})

    if not wechat.get("app_id") or not wechat.get("app_secret"):
        print("❌ 错误: 请在 config/config.yaml 中配置 publisher.wechat.app_id 和 app_secret")
        sys.exit(1)

    return WeChatPublisher(
        PublisherConfig(
            enabled=True,
            app_id=wechat["app_id"],
            app_secret=wechat["app_secret"],
            auto_publish=pub_config.get("auto_publish", False),
            include_abstract=pub_config.get("include_abstract", True),
            include_authors=pub_config.get("include_authors", True),
            article_author=pub_config.get("author", "arXiv Paper Bot"),
            default_cover=wechat.get("default_cover", ""),
        )
    )


def load_papers(input_path: str) -> list:
    """从 JSON 文件加载论文."""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    papers = []
    for item in data:
        paper = Paper(
            arxiv_id=item.get("arxiv_id", ""),
            title=item.get("title", ""),
            abstract=item.get("abstract", ""),
            authors=item.get("authors", []),
            primary_category=item.get("primary_category", ""),
            categories=item.get("categories", []),
            pdf_url=item.get("pdf_url", ""),
            entry_url=item.get("entry_url", ""),
            published=None,
            updated=None,
            score=item.get("score", 0),
            matched_keywords=item.get("matched_keywords", []),
        )
        papers.append(paper)

    return papers


def cmd_upload_cover(args, config):
    """上传封面图片."""
    publisher = create_publisher(config)

    print(f"📤 上传封面图片: {args.image_path}")

    try:
        media_id = publisher.upload_image(args.image_path)
        print(f"\n✅ 上传成功!")
        print(f"   media_id: {media_id}")
        print(f"\n💡 将此 media_id 添加到 config/config.yaml:")
        print(f"   publisher:")
        print(f"     wechat:")
        print(f'       default_cover: "{media_id}"')
    except PublishError as e:
        print(f"❌ 上传失败: {e}")
        sys.exit(1)


def cmd_publish(args, config):
    """发布论文."""
    publisher = create_publisher(config)

    # 加载论文
    if args.input:
        print(f"📖 从文件加载论文: {args.input}")
        papers = load_papers(args.input)
    else:
        # 默认从 data/papers.json 加载
        default_path = Path(__file__).parent.parent / "data" / "papers.json"
        if not default_path.exists():
            print("❌ 错误: 未找到 data/papers.json，请先运行 python main.py 获取论文")
            sys.exit(1)
        print(f"📖 从默认路径加载论文: {default_path}")
        papers = load_papers(str(default_path))

    if not papers:
        print("❌ 错误: 没有可发布的论文")
        sys.exit(1)

    # 限制数量
    papers = papers[: args.top_k]
    print(f"📚 准备发布 {len(papers)} 篇论文")

    # 获取封面图
    thumb_media_id = args.cover or config.get("publisher", {}).get("wechat", {}).get("default_cover")
    if not thumb_media_id:
        print("❌ 错误: 缺少封面图 media_id")
        print("   请使用 --cover 参数指定，或在配置中设置 default_cover")
        print("   上传封面图: python scripts/publish.py upload-cover path/to/cover.jpg")
        sys.exit(1)

    # 发布
    try:
        if args.auto:
            publisher.config.auto_publish = True
            print("🚀 自动发布模式已启用")

        result = publisher.publish_papers(papers, thumb_media_id=thumb_media_id)

        print(f"\n✅ 操作成功!")
        print(f"   草稿 media_id: {result['media_id']}")

        if result.get("publish_id"):
            print(f"   发布任务 ID: {result['publish_id']}")
            print(f"   状态: {result['status']}")
            print("\n💡 发布需要一些时间，请在公众号后台查看发布状态")
        else:
            print(f"   状态: 已保存到草稿箱")
            print("\n💡 请前往公众号后台 -> 草稿箱 查看并手动发布")

    except PublishError as e:
        print(f"❌ 发布失败: {e}")
        sys.exit(1)


def cmd_status(args, config):
    """查询发布状态."""
    publisher = create_publisher(config)

    try:
        status = publisher.get_publish_status(args.publish_id)
        print(f"📊 发布状态:")
        print(json.dumps(status, indent=2, ensure_ascii=False))
    except PublishError as e:
        print(f"❌ 查询失败: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="微信公众号发布工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # upload-cover 命令
    upload_parser = subparsers.add_parser("upload-cover", help="上传封面图片")
    upload_parser.add_argument("image_path", help="图片文件路径")

    # publish 命令
    publish_parser = subparsers.add_parser("publish", help="发布论文到公众号")
    publish_parser.add_argument("--cover", help="封面图 media_id")
    publish_parser.add_argument("--input", "-i", help="论文 JSON 文件路径")
    publish_parser.add_argument("--top-k", type=int, default=10, help="发布论文数量 (默认: 10)")
    publish_parser.add_argument("--auto", action="store_true", help="自动发布 (不只是保存草稿)")

    # status 命令
    status_parser = subparsers.add_parser("status", help="查询发布状态")
    status_parser.add_argument("publish_id", help="发布任务 ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    config = load_config()

    if args.command == "upload-cover":
        cmd_upload_cover(args, config)
    elif args.command == "publish":
        cmd_publish(args, config)
    elif args.command == "status":
        cmd_status(args, config)


if __name__ == "__main__":
    main()
