from __future__ import annotations

import os
from typing import Optional

from dotenv import dotenv_values


_DOTENV = dotenv_values(".env")


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read config from OS env first, then .env (for local dev)."""
    return os.environ.get(name, _DOTENV.get(name, default))


def env_int(name: str, default: int) -> int:
    raw = env(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default

