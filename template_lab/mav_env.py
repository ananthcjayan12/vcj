"""Load repository-local environment defaults for MAV processes."""
from __future__ import annotations

import os
from pathlib import Path


def load_repo_env(repo_root: Path | None = None) -> Path | None:
    """Load unset variables from the repository .env file.

    Explicitly exported environment variables always win. This intentionally
    supports the small KEY=value subset used by the local pipeline without a
    third-party dotenv dependency.
    """
    root = repo_root or Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    if not env_path.exists():
        return None
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value
    return env_path
