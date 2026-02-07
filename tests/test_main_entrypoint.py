"""Tests for deprecated main.py compatibility wrapper."""

from datetime import date

import main as legacy_main


class _FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 2, 7)


def test_main_forwards_basic_args(monkeypatch):
    captured = {}

    def _fake_run_daily(args):
        captured["args"] = list(args)
        return 0

    monkeypatch.setattr(legacy_main, "run_daily_main", _fake_run_daily)

    code = legacy_main.main(["--config", "config/config.yaml", "--day", "2026-02-06", "--no-llm"])

    assert code == 0
    assert captured["args"] == [
        "--config",
        "config/config.yaml",
        "--day",
        "2026-02-06",
        "--no-llm",
    ]


def test_main_maps_legacy_days_and_test_mode(monkeypatch):
    captured = {}

    def _fake_run_daily(args):
        captured["args"] = list(args)
        return 0

    monkeypatch.setattr(legacy_main, "run_daily_main", _fake_run_daily)
    monkeypatch.setattr(legacy_main, "date", _FixedDate)

    code = legacy_main.main(["--days", "3", "--test"])

    assert code == 0
    assert captured["args"] == [
        "--config",
        "config/config.yaml",
        "--day",
        "2026-02-05",
        "--max-results",
        "50",
        "--no-notify",
    ]
