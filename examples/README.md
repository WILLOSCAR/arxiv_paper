# Examples (Legacy / Optional)

`examples/` contains low-level usage demos (fetch/filter/storage).

For new usage, start with the primary daily entrypoint:

```bash
python -m src.pipeline.run_daily --config config/config.yaml --day YYYY-MM-DD
```

## Available scripts

- `quick_start.py`: basic fetch + filter + save
- `combined_search.py`: category + keyword search
- `keyword_search.py`: keyword-only search
- `fetch_today.py`: simple daily fetch preview

Run any example:

```bash
python examples/<script_name>.py
```

## Positioning

These scripts are kept for reference and experimentation.
They are not the main production workflow of this repository.
