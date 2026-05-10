from __future__ import annotations

import re
from datetime import datetime
from json import dump, load
from pathlib import Path
from typing import Any

from groq import Groq
from dotenv import dotenv_values
import os

from Backend.realtime_search.browser import dispose_controller, get_controller
from Backend.realtime_search.cache import SearchCache, should_bypass_cache
from Backend.realtime_search.config import load_config
from Backend.realtime_search.context import get_search_session
from Backend.realtime_search.learning import bump_topic_stats
from Backend.realtime_search.memory import SearchHit, SearchMemoryStore, classify_topics


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _answer_modifier(answer: str) -> str:
    lines = answer.split("\n")
    non_empty = [line for line in lines if line.strip()]
    return "\n".join(non_empty)


def _load_chat_messages(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return load(f)
    except FileNotFoundError:
        return []


def _save_chat_messages(path: str, messages: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        dump(messages, f, indent=4, ensure_ascii=False)


def _pick_provider(query: str, default: str) -> tuple[str, str]:
    low = query.lower().strip()
    mapping = (
        ("youtube ", "youtube"),
        ("yt ", "youtube"),
        ("reddit ", "reddit"),
        ("wikipedia ", "wikipedia"),
        ("wiki ", "wikipedia"),
        ("duckduckgo ", "duckduckgo"),
        ("ddg ", "duckduckgo"),
        ("bing ", "bing"),
        ("brave ", "brave"),
        ("google ", "google"),
    )
    for pref, prov in mapping:
        if low.startswith(pref):
            return prov, query[len(pref) :].strip()
    return default, query


def _build_evidence(hits: list[SearchHit]) -> str:
    parts: list[str] = []
    for i, h in enumerate(hits, start=1):
        snippet = re.sub(r"\s+", " ", h.snippet or "").strip()
        parts.append(f"{i}. {h.title}\n   URL: {h.url}\n   Snippet: {snippet}")
    return "\n".join(parts).strip()


def _format_widget_data(widget_data: dict[str, Any]) -> str:
    if not widget_data:
        return ""
    # Keep this concise; the LLM will turn it into natural language.
    import json

    return "Widget data (structured):\n" + json.dumps(widget_data, indent=2, ensure_ascii=False)


def _summarize(
    *,
    username: str | None,
    assistantname: str | None,
    query: str,
    evidence: str,
    chat_tail: list[dict[str, Any]],
    realtime_info: str,
    groq_key: str | None,
) -> str:
    if not groq_key:
        return "Search completed, but GroqAPIKey is missing in .env — cannot summarize."
    client = Groq(api_key=groq_key)
    u = username or "User"
    a = assistantname or "Assistant"
    system = (
        f"Hello, I am {u}. You are {a}, a careful research assistant.\n"
        "You are answering using ONLY the provided live search excerpts.\n"
        "If excerpts are insufficient, say what is missing and give the best safe partial answer.\n"
        "Do not invent numbers, scores, or prices. Do not output HTML.\n"
        "Cite sources briefly (domain names). Use professional punctuation.\n"
        "Mention that information is live as of the user's local time when appropriate."
    )
    tail = chat_tail[-10:] if chat_tail else []
    tail_txt = "\n".join(
        f"{m.get('role','')}: {m.get('content','')}" for m in tail if m.get("role") in {"user", "assistant"}
    )
    user_blob = (
        f"User question:\n{query}\n\n"
        f"Recent chat context (may help disambiguate follow-ups):\n{tail_txt}\n\n"
        f"{realtime_info}\n\n"
        f"Live search excerpts:\n{evidence}"
    )
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_blob},
        ],
        temperature=0.35,
        max_tokens=900,
        top_p=1,
        stream=True,
        stop=None,
    )
    answer = ""
    for chunk in completion:
        if chunk.choices[0].delta.content:
            answer += chunk.choices[0].delta.content
    return answer.strip().replace("</s>", "")


def realtime_search_engine(prompt: str) -> str:
    """Run a live browser search, summarize with Groq, store in dedicated search memory + cache."""
    cfg = load_config()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)

    env_vars = dotenv_values(_project_root() / ".env")
    username = os.environ.get("USERNAME", env_vars.get("Username"))
    assistantname = os.environ.get("ASSISTANT_NAME", env_vars.get("Assistantname"))
    groq_key = os.environ.get("GROQ_API_KEY", env_vars.get("GroqAPIKey"))

    chat_path = cfg.data_dir / "ChatLog.json"
    messages = _load_chat_messages(str(chat_path))

    session = get_search_session()
    merged = session.merge_followup(prompt)
    provider, stripped = _pick_provider(merged, cfg.default_provider)
    normalized = " ".join(stripped.split()).strip()
    topics = classify_topics(normalized)

    ttl = cfg.cache_ttl_live_seconds if should_bypass_cache(normalized) else cfg.cache_ttl_seconds_default
    if any(t in {"weather", "crypto", "sports", "news"} for t in topics):
        ttl = min(ttl, cfg.cache_ttl_live_seconds)

    cache = SearchCache(cfg.cache_path)
    cached = cache.get(normalized, provider, ttl_seconds=ttl)
    if cached:
        messages.append({"role": "user", "content": prompt})
        messages.append({"role": "assistant", "content": cached})
        _save_chat_messages(str(chat_path), messages)
        session.update_from_run(prompt, normalized, topics)
        return _answer_modifier(cached)

    controller = get_controller(cfg)
    try:
        bundle = controller.search(normalized, provider)
    finally:
        if not cfg.reuse_browser:
            dispose_controller()

    evidence_parts: list[str] = []
    if bundle.widget_data:
        evidence_parts.append(_format_widget_data(bundle.widget_data))
    if bundle.visible_text_excerpt:
        # Provide a bounded excerpt; this is our main “visible page reader” fallback.
        evidence_parts.append("Visible page text excerpt:\n" + bundle.visible_text_excerpt[:8000])
    link_evidence = _build_evidence(bundle.hits)
    if link_evidence:
        evidence_parts.append("Link results:\n" + link_evidence)
    evidence = "\n\n---\n\n".join([p for p in evidence_parts if p.strip()]).strip()
    if not evidence:
        evidence = "No readable content was extracted from the page."

    day = datetime.now().strftime("%A")
    date = datetime.now().strftime("%d %B %Y %H:%M")
    realtime_info = f"Local assistant time snapshot: {day}, {date}."

    answer = _summarize(
        username=username,
        assistantname=assistantname,
        query=normalized,
        evidence=evidence,
        chat_tail=messages,
        realtime_info=realtime_info,
        groq_key=groq_key,
    )

    store = SearchMemoryStore(cfg.search_memory_path, cfg.cache_ttl_live_seconds, cfg.cache_ttl_seconds_default)
    store.append(
        query=prompt,
        normalized_query=normalized,
        provider=bundle.provider,
        hits=bundle.hits,
        summary=answer,
        topics=topics,
    )
    bump_topic_stats(cfg.data_dir / "SearchTopicStats.json", topics)
    cache.set(normalized, bundle.provider, answer, ttl_seconds=ttl)

    messages.append({"role": "user", "content": prompt})
    messages.append({"role": "assistant", "content": answer})
    _save_chat_messages(str(chat_path), messages)

    session.update_from_run(prompt, normalized, topics)
    return _answer_modifier(answer)


if __name__ == "__main__":
    while True:
        q = input("Enter your query: ").strip()
        if not q:
            continue
        print(realtime_search_engine(q))
