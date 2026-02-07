"""CLI to run the calendar-day daily pipeline graph and write grouped output."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import yaml

from ..notifier import FeishuNotifier, NotificationConfig, NotificationError, build_notifier
from ..secrets import SecretError, resolve_secret
from .daily_graph import build_daily_graph
from .topics import DEFAULT_INTEREST_RUBRIC_TEXT


logger = logging.getLogger(__name__)


def _load_env_file(path: Path) -> bool:
    """Load KEY=VALUE pairs from a dotenv-style file into os.environ."""
    if not path.exists() or not path.is_file():
        return False

    loaded = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
        loaded = True
    return loaded


def _load_default_env_files(config_path: str) -> None:
    """Best-effort loading of local env files used in this project."""
    candidates = [Path("env/.env"), Path("../env/.env")]

    cfg_path = Path(config_path)
    if cfg_path.exists():
        cfg_dir = cfg_path.resolve().parent
        candidates.append(cfg_dir.parent / "env/.env")
        candidates.append(cfg_dir.parent.parent / "env/.env")

    seen = set()
    for candidate in candidates:
        resolved = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        if _load_env_file(candidate):
            logger.info("Loaded env file: %s", candidate)


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _derive_llm_config(cfg: dict) -> dict:
    """Build llm_config for daily graph from either `daily.llm` or existing agent config."""
    daily = cfg.get("daily") or {}
    if isinstance(daily.get("llm"), dict):
        return dict(daily["llm"])

    agent = (cfg.get("personalization") or {}).get("agent") or {}
    api = agent.get("api") or {}
    models = agent.get("models") or {}

    out: Dict[str, Any] = {
        "provider": agent.get("provider"),
        "base_url": api.get("base_url"),
        "model": agent.get("model"),
        "reasoning_model": models.get("reasoning"),
        "simple_model": models.get("simple"),
        "temperature": agent.get("temperature", 0.2),
        "timeout": api.get("timeout"),
        "api_key": api.get("api_key"),
        "api_key_env": api.get("api_key_env"),
        "api_key_file": api.get("api_key_file"),
    }

    # Daily-only tuning knobs (optional).
    if daily.get("llm_batch_size") is not None:
        out["batch_size"] = daily.get("llm_batch_size")
    if daily.get("llm_scope") is not None:
        out["scope"] = daily.get("llm_scope")
    if daily.get("llm_vote_enabled") is not None:
        out["vote_enabled"] = daily.get("llm_vote_enabled")
    if daily.get("llm_vote_model") is not None:
        out["vote_model"] = daily.get("llm_vote_model")
    if daily.get("llm_batch_retries") is not None:
        out["batch_retries"] = daily.get("llm_batch_retries")
    if daily.get("llm_parallel_workers") is not None:
        out["parallel_workers"] = daily.get("llm_parallel_workers")

    return out


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_daily_notification_config(cfg: dict, daily_cfg: dict) -> NotificationConfig:
    """Build NotificationConfig for daily topic push with global fallback."""
    daily_notify = daily_cfg.get("notification") or {}
    global_notify = cfg.get("notification") or {}

    daily_feishu = daily_notify.get("feishu") or {}
    global_feishu = global_notify.get("feishu") or {}

    abstract_preview_chars_value = daily_notify.get("abstract_preview_chars")
    if abstract_preview_chars_value is None:
        abstract_preview_chars_value = global_notify.get("abstract_preview_chars")
    if abstract_preview_chars_value is None:
        abstract_preview_chars_value = 0

    return NotificationConfig(
        enabled=bool(daily_notify.get("enabled", False)),
        provider=str(daily_notify.get("provider") or global_notify.get("provider") or "feishu"),
        top_k=int(daily_notify.get("per_topic") or 3),
        feishu_webhook=daily_feishu.get("webhook_url") or global_feishu.get("webhook_url"),
        feishu_webhook_file=daily_feishu.get("webhook_file") or global_feishu.get("webhook_file"),
        feishu_secret=daily_feishu.get("secret") or global_feishu.get("secret"),
        use_rich_format=True,
        include_abstract=bool(daily_notify.get("include_abstract", global_notify.get("include_abstract", False))),
        card_style=str(daily_notify.get("card_style") or global_notify.get("card_style") or "magazine"),
        abstract_preview_chars=int(abstract_preview_chars_value),
        show_authors=bool(daily_notify.get("show_authors", global_notify.get("show_authors", True))),
        show_keywords=bool(daily_notify.get("show_keywords", global_notify.get("show_keywords", True))),
        show_reason=bool(daily_notify.get("show_reason", global_notify.get("show_reason", True))),
        show_score_badge=bool(
            daily_notify.get("show_score_badge", global_notify.get("show_score_badge", True))
        ),
    )


def _maybe_send_daily_notification(
    *,
    cfg: dict,
    daily_cfg: dict,
    output: dict,
    force_notify: bool,
    disable_notify: bool,
    per_topic_override: int,
) -> None:
    notify_cfg = _build_daily_notification_config(cfg, daily_cfg)
    if force_notify:
        notify_cfg.enabled = True
    if disable_notify:
        notify_cfg.enabled = False

    if not notify_cfg.enabled:
        return

    per_topic = max(1, int(per_topic_override or notify_cfg.top_k or 3))
    daily_notify = daily_cfg.get("notification") or {}
    include_empty_topics = bool(daily_notify.get("include_empty_topics", True))
    raw_abstract_preview_chars = daily_notify.get("abstract_preview_chars")
    abstract_preview_chars = 0 if raw_abstract_preview_chars is None else int(raw_abstract_preview_chars)

    try:
        notifier = build_notifier(notify_cfg)
    except NotificationError as exc:
        logger.warning("Daily notification disabled due to config error: %s", exc)
        return

    if not notifier:
        return

    if isinstance(notifier, FeishuNotifier):
        try:
            notifier.send_daily_topics(
                output,
                per_topic=per_topic,
                include_empty_topics=include_empty_topics,
                abstract_preview_chars=abstract_preview_chars,
            )
        except Exception as exc:
            logger.warning("Daily notification failed: %s", exc)
        return

    logger.warning(
        "Daily notification currently supports Feishu topic card only; provider=%s skipped",
        notify_cfg.provider,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run calendar-day arXiv daily topic pipeline")
    parser.add_argument("--config", default="config/config.yaml", help="Path to YAML config")
    parser.add_argument("--day", default="", help="Local calendar day YYYY-MM-DD (default: today in timezone)")
    parser.add_argument("--timezone", default="", help="IANA timezone (default: Asia/Shanghai or config)")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM adjudication/scoring (blocked when daily.require_llm=true)",
    )
    parser.add_argument("--no-intermediates", action="store_true", help="Do not write intermediate JSONL files")
    parser.add_argument("--out", default="", help="Output JSON path (default: data/index/<day>/daily_topics.json)")
    parser.add_argument("--max-results", type=int, default=0, help="Max results per category (default: 2000)")
    parser.add_argument("--notify-feishu", action="store_true", help="Send daily 7-topic card via Feishu")
    parser.add_argument("--no-notify", action="store_true", help="Disable daily notification for this run")
    parser.add_argument("--per-topic", type=int, default=0, help="Override papers shown per topic in daily card")
    args = parser.parse_args(argv)

    _load_default_env_files(args.config)
    cfg = _load_yaml(args.config)
    daily_cfg = cfg.get("daily") or {}

    require_llm = bool(daily_cfg.get("require_llm", True))

    timezone = args.timezone or daily_cfg.get("timezone") or (cfg.get("schedule") or {}).get("timezone") or "Asia/Shanghai"
    categories = daily_cfg.get("categories") or [
        "cs.AI",
        "cs.CV",
        "cs.IR",
        "cs.HC",
        "cs.CL",
        "cs.LG",
    ]
    max_results = int(args.max_results or daily_cfg.get("max_results") or 2000)

    rubric_text = daily_cfg.get("rubric_text") or DEFAULT_INTEREST_RUBRIC_TEXT
    relevance_threshold = daily_cfg.get("relevance_threshold")

    if require_llm and args.no_llm:
        raise SystemExit("`--no-llm` is disabled because daily.require_llm=true")

    if require_llm and not bool(daily_cfg.get("llm_enabled", True)):
        raise SystemExit("`daily.llm_enabled` must be true when `daily.require_llm=true`")

    llm_enabled = (not args.no_llm) and bool(daily_cfg.get("llm_enabled", True))
    llm_config = _derive_llm_config(cfg)
    llm_config["allow_rule_fallback"] = bool(daily_cfg.get("allow_rule_fallback", False))

    if require_llm:
        try:
            resolve_secret(
                value=llm_config.get("api_key"),
                env=llm_config.get("api_key_env") or "OPENAI_API_KEY",
                file_path=llm_config.get("api_key_file"),
                required=True,
                name="LLM API key",
            )
        except SecretError as exc:
            raise SystemExit(f"LLM is required but API key is not configured: {exc}")

    # Logging (keep it simple; do not print secrets).
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    graph = build_daily_graph()

    init_state: dict = {
        "day": args.day or "",
        "timezone": timezone,
        "arxiv_categories": categories,
        "arxiv_max_results": max_results,
        "rubric_text": rubric_text,
        "relevance_threshold": relevance_threshold,
        "llm_enabled": llm_enabled,
        "llm_config": llm_config,
    }

    thread_id = f"daily-{args.day or 'today'}-{uuid4().hex[:8]}"
    logger.info("Running daily pipeline (day=%s tz=%s)", args.day or "AUTO", timezone)

    result = graph.invoke(init_state, config={"configurable": {"thread_id": thread_id}})
    output = result.get("grouped_output") or {}

    if args.out:
        out_path = Path(args.out)
    else:
        day_str = output.get("day") or (args.day or "unknown-day")
        out_path = Path("data") / "index" / str(day_str) / "daily_topics.json"

    _write_json(out_path, output)
    logger.info("Wrote grouped output: %s", out_path)

    save_intermediates = bool(daily_cfg.get("save_intermediates", True)) and not args.no_intermediates
    if save_intermediates:
        day_dir = out_path.parent
        for key, filename in [
            ("raw_papers", "raw.jsonl"),
            ("fetched_papers", "enriched.jsonl"),
            ("recalled_papers", "recalled.jsonl"),
            ("dropped_papers", "dropped.jsonl"),
            ("routed_papers", "routed.jsonl"),
            ("scored_papers", "scored.jsonl"),
        ]:
            rows = result.get(key) or []
            if isinstance(rows, list) and rows:
                _write_jsonl(day_dir / filename, rows)

    _maybe_send_daily_notification(
        cfg=cfg,
        daily_cfg=daily_cfg,
        output=output,
        force_notify=bool(args.notify_feishu),
        disable_notify=bool(args.no_notify),
        per_topic_override=int(args.per_topic or 0),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
