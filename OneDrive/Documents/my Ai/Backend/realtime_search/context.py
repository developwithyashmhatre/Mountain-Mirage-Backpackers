from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SearchSessionContext:
    """Short-lived follow-up context (e.g., 'tomorrow' after a weather query)."""

    last_query: str | None = None
    last_normalized_query: str | None = None
    last_topics: list[str] = field(default_factory=list)
    updated_at: datetime | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def merge_followup(self, query: str) -> str:
        """Expand pronouns / follow-ups using the last query when obvious."""
        q = (query or "").strip()
        low = q.lower()
        if not self.last_normalized_query:
            return q
        follow_starts = (
            "what about ",
            "how about ",
            "and ",
            "tomorrow",
            "next ",
            "also ",
            "same for ",
        )
        if any(low.startswith(s) for s in follow_starts) or low in {"tomorrow", "today", "tonight"}:
            return f"{self.last_normalized_query} — {q}"
        return q

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_query": self.last_query,
            "last_normalized_query": self.last_normalized_query,
            "last_topics": list(self.last_topics),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def update_from_run(self, original: str, normalized: str, topics: list[str]) -> None:
        self.last_query = original
        self.last_normalized_query = normalized
        self.last_topics = list(topics)
        self.touch()


_SESSION = SearchSessionContext()


def get_search_session() -> SearchSessionContext:
    return _SESSION
