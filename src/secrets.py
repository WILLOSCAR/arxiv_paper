"""Secret resolution helpers.

This project supports keeping credentials out of `config/config.yaml` by loading
them from environment variables or from local files outside the repo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class SecretError(ValueError):
    """Raised when a required secret cannot be resolved."""


def read_secret_file(path: str) -> str:
    """Read a secret from a local file without logging its content."""
    p = Path(path).expanduser()
    try:
        value = p.read_text(encoding="utf-8").strip()
    except OSError:
        # Avoid leaking absolute paths via exception messages.
        raise SecretError(f"Failed to read secret file: {p.name}")
    return value


def resolve_secret(
    *,
    value: Optional[str] = None,
    env: Optional[str] = None,
    file_path: Optional[str] = None,
    required: bool = True,
    name: str = "secret",
) -> Optional[str]:
    """Resolve secret from explicit value, env var, or a file (in that order)."""
    if value:
        resolved = str(value).strip()
        if resolved:
            return resolved

    if env:
        resolved = os.getenv(env)
        if resolved:
            resolved = resolved.strip()
            if resolved:
                return resolved

    file_error: Optional[SecretError] = None
    if file_path:
        try:
            resolved = read_secret_file(file_path)
            if resolved:
                return resolved
        except SecretError as exc:
            file_error = exc

    if required:
        if file_error is not None:
            raise SecretError(str(file_error))
        hint = []
        if env:
            hint.append(f"env={env}")
        if file_path:
            # Avoid leaking local absolute paths in logs/errors.
            hint.append(f"file={Path(file_path).name}")
        hint_str = f" ({', '.join(hint)})" if hint else ""
        raise SecretError(f"Missing required {name}{hint_str}")

    return None


def mask_secret(secret: str, keep_end: int = 4) -> str:
    """Return a non-reversible masked form safe to print."""
    if secret is None:
        return ""
    s = str(secret)
    if len(s) <= keep_end:
        return "*" * len(s)
    return "*" * (len(s) - keep_end) + s[-keep_end:]
