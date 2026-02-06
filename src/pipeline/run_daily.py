"""CLI to run the calendar-day daily pipeline graph and write grouped output."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import yaml

from .daily_graph import build_daily_graph
from .topics import DEFAULT_INTEREST_RUBRIC_TEXT


logger = logging.getLogger(__name__)


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

    return out


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run calendar-day arXiv daily topic pipeline")
    parser.add_argument("--config", default="config/config.yaml", help="Path to YAML config")
    parser.add_argument("--day", default="", help="Local calendar day YYYY-MM-DD (default: today in timezone)")
    parser.add_argument("--timezone", default="", help="IANA timezone (default: Asia/Shanghai or config)")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM adjudication/scoring")
    parser.add_argument("--no-intermediates", action="store_true", help="Do not write intermediate JSONL files")
    parser.add_argument("--out", default="", help="Output JSON path (default: data/index/<day>/daily_topics.json)")
    parser.add_argument("--max-results", type=int, default=0, help="Max results per category (default: 2000)")
    args = parser.parse_args(argv)

    cfg = _load_yaml(args.config)
    daily_cfg = cfg.get("daily") or {}

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

    llm_enabled = (not args.no_llm) and bool(daily_cfg.get("llm_enabled", True))
    llm_config = _derive_llm_config(cfg)

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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
