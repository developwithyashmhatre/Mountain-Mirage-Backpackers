"""Backward-compatible entrypoint for the live web search layer."""

from Backend.realtime_search.pipeline import realtime_search_engine

__all__ = ["realtime_search_engine"]

if __name__ == "__main__":
    while True:
        prompt = input("Enter your query: ").strip()
        if not prompt:
            continue
        print(realtime_search_engine(prompt))
