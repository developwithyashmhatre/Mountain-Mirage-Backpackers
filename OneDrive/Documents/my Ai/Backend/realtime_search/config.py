from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RealtimeSearchConfig:
    data_dir: Path
    search_memory_path: Path
    cache_path: Path
    browser_profile_dir: Path
    headless: bool
    stealth: bool
    reuse_browser: bool
    default_provider: str
    channel: str | None
    navigation_timeout_ms: int
    max_results: int
    cache_ttl_seconds_default: int
    cache_ttl_live_seconds: int


def load_config() -> RealtimeSearchConfig:
    env = dotenv_values(_project_root() / ".env")
    data_dir = _project_root() / "Data"
    headless = str(env.get("REALTIME_SEARCH_HEADLESS", "false")).lower() in {"1", "true", "yes"}
    stealth = str(env.get("REALTIME_SEARCH_STEALTH", "true")).lower() in {"1", "true", "yes"}
    reuse_browser = str(env.get("REALTIME_SEARCH_REUSE_BROWSER", "false")).lower() in {"1", "true", "yes"}
    channel = env.get("REALTIME_SEARCH_CHROME_CHANNEL") or ("chrome" if os.name == "nt" else None)
    provider = (env.get("REALTIME_SEARCH_PROVIDER") or "google").strip().lower()
    return RealtimeSearchConfig(
        data_dir=data_dir,
        search_memory_path=data_dir / "SearchMemory.json",
        cache_path=data_dir / "SearchCache.json",
        browser_profile_dir=data_dir / "RealtimeSearchBrowserProfile",
        headless=headless,
        stealth=stealth,
        reuse_browser=reuse_browser,
        default_provider=provider,
        channel=channel,
        navigation_timeout_ms=int(env.get("REALTIME_SEARCH_NAV_TIMEOUT_MS", "45000")),
        max_results=int(env.get("REALTIME_SEARCH_MAX_RESULTS", "8")),
        cache_ttl_seconds_default=int(env.get("REALTIME_SEARCH_CACHE_TTL", "900")),
        cache_ttl_live_seconds=int(env.get("REALTIME_SEARCH_CACHE_TTL_LIVE", "120")),
    )
