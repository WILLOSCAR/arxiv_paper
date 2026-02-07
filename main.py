#!/usr/bin/env python3
"""Legacy compatibility entrypoint.

`main.py` is kept for backward compatibility and now delegates to
`python -m src.pipeline.run_daily`.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from typing import Sequence

from src.pipeline.run_daily import main as run_daily_main

logger = logging.getLogger(__name__)


def _parse_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description=(
            "Deprecated entrypoint. Prefer: python -m src.pipeline.run_daily "
            "--config config/config.yaml --day YYYY-MM-DD"
        )
    )
    parser.add_argument("--config", default="config/config.yaml", help="Path to YAML config")
    parser.add_argument("--day", default="", help="Calendar day YYYY-MM-DD")
    parser.add_argument("--timezone", default="", help="IANA timezone")

    # Legacy flags kept for compatibility.
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Legacy lookback days. If provided, only one derived day is run.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Legacy test mode. Maps to smaller fetch scope + no notifications.",
    )

    return parser.parse_known_args(argv)


def _derive_day(day_arg: str, days_arg: int) -> str:
    if day_arg:
        return day_arg
    if days_arg <= 1:
        return ""

    # Legacy `--days N` used a rolling window; daily pipeline is calendar-day based.
    # Choose one deterministic day to keep backward compatibility predictable.
    derived = date.today() - timedelta(days=days_arg - 1)
    logger.warning("`--days %s` maps to single day `%s` in compatibility mode", days_arg, derived.isoformat())
    return derived.isoformat()


def _build_forward_args(args: argparse.Namespace, passthrough: list[str]) -> list[str]:
    forward = ["--config", args.config]

    day = _derive_day(args.day, args.days)
    if day:
        forward.extend(["--day", day])
    if args.timezone:
        forward.extend(["--timezone", args.timezone])

    if args.test:
        forward.extend(["--max-results", "50", "--no-notify"])

    # Preserve newer run_daily flags not explicitly modeled here.
    forward.extend(passthrough)
    return forward


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    args, passthrough = _parse_args(argv)
    logger.warning("`main.py` is deprecated. Use `python -m src.pipeline.run_daily` instead.")

    forward_args = _build_forward_args(args, passthrough)
    return int(run_daily_main(forward_args))


if __name__ == "__main__":
    raise SystemExit(main())
