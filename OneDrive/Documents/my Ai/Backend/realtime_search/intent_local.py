from __future__ import annotations

import re

_LIVE_PATTERNS = (
    r"\bsearch\s+internet\b",
    r"\bsearch\b.*\b(internet|online|web|google|bing|duckduckgo|brave)\b",
    r"\b(open|go to)\s+google\b",
    r"\bgoogle\s+and\s+search\b",
    r"\bcheck\s+(the\s+)?(current|latest|live)\b",
    r"\bcurrent\s+(weather|price|score|news|status)\b",
    r"\b(latest|breaking)\s+news\b",
    r"\b(weather|forecast)\s+in\b",
    r"\b(bitcoin|btc|ethereum|eth|crypto|stock|nasdaq|dow)\s+(price|now|today)\b",
    r"\b(ipl|nba|nfl|score|scores|match)\b",
    r"\b(what|what's)\s+happening\b",
    r"\bright\s+now\b",
    r"\bflight\s+status\b",
    r"\btraffic\b.*\b(now|current)\b",
    r"\bmaps?\b.*\b(near|directions)\b",
    r"\bsearch\s+(on\s+)?(youtube|reddit|wikipedia)\b",
    r"\bwiki(pedia)?\s+search\b",
)

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _LIVE_PATTERNS]


def should_treat_as_live_web_search(text: str) -> bool:
    """Heuristic boost so obvious live/web lookups still run even if the DMM mislabels them."""
    if not text or not text.strip():
        return False
    s = text.strip()
    if s.lower().startswith("realtime "):
        return True
    return any(p.search(s) for p in _COMPILED)


def upgrade_general_to_realtime(tasks: list[str], raw_query: str) -> list[str]:
    out: list[str] = []
    raw_live = should_treat_as_live_web_search(raw_query)
    for task in tasks:
        if not task.startswith("general"):
            out.append(task)
            continue
        inner = task.removeprefix("general").strip()
        subject = inner or raw_query
        if raw_live or should_treat_as_live_web_search(subject):
            out.append(f"realtime {subject}".strip())
        else:
            out.append(task)
    return out
