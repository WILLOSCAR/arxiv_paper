# Tests

This project uses `pytest` as the primary test runner.

## Run tests

```bash
python -m pytest -q
```

Verbose mode:

```bash
python -m pytest -v
```

Run one file:

```bash
python -m pytest -q tests/test_pipeline_daily_graph.py
```

Run one test case:

```bash
python -m pytest -q tests/test_pipeline_daily_graph.py::test_build_daily_graph_runs
```

## What is covered

- Core models / storage / notifier behavior
- Fetch/filter pipeline pieces
- Daily pipeline graph + routing + notification wiring
- Secrets loading and configuration fallbacks

## Notes

- Tests should be runnable from repo root.
- Keep new tests deterministic (mock network / LLM calls where needed).
- Prefer focused unit tests over broad integration tests unless validating pipeline wiring.
