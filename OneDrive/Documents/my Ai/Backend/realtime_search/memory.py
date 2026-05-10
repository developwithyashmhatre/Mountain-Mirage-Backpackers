from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


@dataclass
class SearchMemoryEntry:
    id: str
    timestamp_iso: str
    query: str
    normalized_query: str
    provider: str
    topics: list[str]
    hits: list[dict[str, str]]
    summary: str
    stale_after_iso: str
    user_agent_note: str = "browser_data_minimized_no_cookies_exported"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_stale_after(topics: list[str], live_ttl: int, default_ttl: int) -> datetime:
    live_markers = {"weather", "crypto", "stocks", "sports", "news", "traffic", "flights"}
    if topics and any(t in live_markers for t in topics):
        return _utc_now() + timedelta(seconds=live_ttl)
    return _utc_now() + timedelta(seconds=default_ttl)


def classify_topics(query: str) -> list[str]:
    q = query.lower()
    topics: list[str] = []
    if any(w in q for w in ("weather", "forecast", "rain", "temperature", "humidity", "wind")):
        topics.append("weather")
    if any(w in q for w in ("bitcoin", "btc", "ethereum", "eth", "crypto", "solana")):
        topics.append("crypto")
    if any(w in q for w in ("stock", "nasdaq", "dow", "s&p", "nifty", "sensex")):
        topics.append("stocks")
    if any(w in q for w in ("score", "ipl", "match", "nba", "nfl", "cricket", "football")):
        topics.append("sports")
    if any(w in q for w in ("news", "breaking", "headline")):
        topics.append("news")
    if any(w in q for w in ("flight", "traffic", "map", "directions")):
        topics.append("traffic" if "traffic" in q else "maps")
    if not topics:
        topics.append("general")
    return sorted(set(topics))


class SearchMemoryStore:
    def __init__(self, path: Path, live_ttl: int, default_ttl: int) -> None:
        self._path = path
        self._live_ttl = live_ttl
        self._default_ttl = default_ttl
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"version": 1, "entries": []})

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "entries": []}

    def _write(self, doc: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    def append(
        self,
        *,
        query: str,
        normalized_query: str,
        provider: str,
        hits: list[SearchHit],
        summary: str,
        topics: list[str],
    ) -> SearchMemoryEntry:
        stale = _default_stale_after(topics, self._live_ttl, self._default_ttl)
        entry = SearchMemoryEntry(
            id=str(uuid.uuid4()),
            timestamp_iso=_utc_now().isoformat(),
            query=query,
            normalized_query=normalized_query,
            provider=provider,
            topics=topics,
            hits=[asdict(h) for h in hits],
            summary=summary,
            stale_after_iso=stale.isoformat(),
        )
        doc = self._read()
        entries: list[dict[str, Any]] = doc.get("entries", [])
        entries.append(asdict(entry))
        # cap file size — keep last 200 dedicated search events only
        doc["entries"] = entries[-200:]
        self._write(doc)
        return entry

    def mark_stale_older_than(self, days: int = 30) -> None:
        """Housekeeping: flag very old entries (soft; we keep stale_after on each record)."""
        cutoff = _utc_now() - timedelta(days=days)
        doc = self._read()
        for e in doc.get("entries", []):
            try:
                ts = datetime.fromisoformat(e["timestamp_iso"])
            except Exception:
                continue
            if ts < cutoff:
                e["archived"] = True
        self._write(doc)
