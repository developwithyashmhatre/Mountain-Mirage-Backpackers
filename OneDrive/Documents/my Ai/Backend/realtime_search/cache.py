from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_FORCE_REFRESH_TERMS = (
    "current ",
    " right now",
    "right now",
    "latest ",
    "live ",
    "breaking ",
    "now ",
    "today",
    "this minute",
)


def should_bypass_cache(query: str) -> bool:
    q = f" {query.lower()} "
    return any(term in q for term in _FORCE_REFRESH_TERMS)


def _normalize_key(query: str, provider: str) -> str:
    s = re.sub(r"\s+", " ", (query or "").strip().lower())
    raw = f"{provider}|{s}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SearchCache:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"version": 1, "items": {}})

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "items": {}}

    def _write(self, doc: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, query: str, provider: str, ttl_seconds: int) -> str | None:
        if should_bypass_cache(query):
            return None
        key = _normalize_key(query, provider)
        doc = self._read()
        item = doc.get("items", {}).get(key)
        if not item:
            return None
        try:
            saved = datetime.fromisoformat(item["saved_at_iso"])
        except Exception:
            return None
        age = (datetime.now(timezone.utc) - saved).total_seconds()
        if age > float(item.get("ttl_seconds", ttl_seconds)):
            return None
        return str(item.get("summary") or "")

    def set(self, query: str, provider: str, summary: str, ttl_seconds: int) -> None:
        key = _normalize_key(query, provider)
        doc = self._read()
        items: dict[str, Any] = doc.get("items", {})
        items[key] = {
            "key": key,
            "saved_at_iso": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": ttl_seconds,
            "summary": summary,
            "provider": provider,
            "query": query,
        }
        # bound cache map
        if len(items) > 400:
            items = dict(list(items.items())[-400:])
        doc["items"] = items
        self._write(doc)
