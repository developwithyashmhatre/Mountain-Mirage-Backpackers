"""Enterprise-style live web search layer (Playwright + dedicated memory + cache)."""

from Backend.realtime_search.pipeline import realtime_search_engine

__all__ = ["realtime_search_engine"]
