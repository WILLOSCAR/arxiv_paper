"""Repository hygiene checks."""

from pathlib import Path


def test_no_hardcoded_api_keys_in_source_tree():
    root = Path(__file__).resolve().parents[1]
    banned_prefixes = ("sk" + "-",)
    scan_suffixes = {".py", ".md", ".yaml", ".yml", ".json"}
    ignored_parts = {".git", "__pycache__", ".pytest_cache"}

    offenders = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in scan_suffixes:
            continue
        if any(part in ignored_parts for part in path.parts):
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(prefix in text for prefix in banned_prefixes):
            offenders.append(path.relative_to(root).as_posix())

    assert not offenders, f"Hardcoded key-like content found in: {offenders}"
