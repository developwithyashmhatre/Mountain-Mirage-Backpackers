from __future__ import annotations

import json
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus

from Backend.realtime_search.config import RealtimeSearchConfig
from Backend.realtime_search.memory import SearchHit


@dataclass
class BrowserSearchResult:
    provider: str
    hits: list[SearchHit]
    widget_data: dict[str, Any]
    visible_text_excerpt: str
    debug: dict[str, Any]


class PlaywrightSearchController:
    """Minimal, security-conscious browser controller (no credential capture)."""

    def __init__(self, cfg: RealtimeSearchConfig) -> None:
        self._cfg = cfg
        self._playwright = None
        self._context = None
        self._debug_log_path = self._cfg.data_dir / "RealtimeSearchDebug.log"

    def _debug(self, event: str, **fields: Any) -> None:
        try:
            payload = {"ts": time.time(), "event": event, **fields}
            self._debug_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._debug_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            # Debug logging must never break search
            return

    def _ensure_import(self):
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chrome"
            ) from exc
        return sync_playwright

    def _launch_context(self):
        sync_playwright = self._ensure_import()
        self._playwright = sync_playwright().start()
        profile = self._cfg.browser_profile_dir
        profile.mkdir(parents=True, exist_ok=True)
        launch_args: list[str] = []
        if self._cfg.stealth:
            launch_args.append("--disable-blink-features=AutomationControlled")
        base = {
            "user_data_dir": str(profile),
            "headless": self._cfg.headless,
            "args": launch_args,
            "viewport": {"width": 1365, "height": 900},
            "locale": "en-US",
            "timezone_id": "UTC",
        }
        if self._cfg.channel:
            try:
                self._context = self._playwright.chromium.launch_persistent_context(
                    **base, channel=self._cfg.channel
                )
            except Exception:
                self._context = self._playwright.chromium.launch_persistent_context(**base)
        else:
            self._context = self._playwright.chromium.launch_persistent_context(**base)
        self._context.set_default_navigation_timeout(self._cfg.navigation_timeout_ms)

    def _get_context(self):
        if self._context is None:
            self._launch_context()
        assert self._context is not None
        return self._context

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            finally:
                self._context = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            finally:
                self._playwright = None

    def _maybe_accept_consent(self, page) -> None:
        selectors = (
            'button:has-text("Accept all")',
            'button:has-text("I agree")',
            'button:has-text("Agree")',
            'form[action*="consent"] button',
            'button:has-text("Accept")',
        )
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=2500)
                    page.wait_for_timeout(400)
                    return
            except Exception:
                continue

    def _wait_ready(self, page, *, provider: str) -> None:
        # A layered wait to avoid scraping before JS/rendering is done.
        # Some pages never reach networkidle (long-polling), so we treat it as best-effort.
        try:
            page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        # Give widgets time to render.
        page.wait_for_timeout(1500)

        # Provider-specific readiness gates.
        if provider == "google":
            for sel in ("#search", "#rso", "body"):
                try:
                    page.wait_for_selector(sel, timeout=12000)
                    break
                except Exception:
                    continue
            page.wait_for_timeout(800)
        elif provider == "bing":
            try:
                page.wait_for_selector("#b_results", timeout=15000)
            except Exception:
                pass
        elif provider in {"duckduckgo", "ddg"}:
            try:
                page.wait_for_selector("a.result__a", timeout=15000)
            except Exception:
                pass

    def _visible_text(self, page, *, limit: int = 12000) -> str:
        try:
            text = page.evaluate("() => (document.body && document.body.innerText) ? document.body.innerText : ''")
            text = re.sub(r"\n{3,}", "\n\n", str(text or "")).strip()
            return text[:limit]
        except Exception:
            return ""

    def _extract_google_weather_widget(self, page) -> dict[str, Any] | None:
        # Google weather widget selectors (most common)
        try:
            if page.locator("#wob_tm").count() == 0:
                return None
            def _txt(sel: str) -> str:
                try:
                    return (page.locator(sel).first.inner_text() or "").strip()
                except Exception:
                    return ""
            data = {
                "type": "weather",
                "location": _txt("#wob_loc"),
                "datetime": _txt("#wob_dts"),
                "temperature_c": _txt("#wob_tm"),
                "condition": _txt("#wob_dc"),
                "precipitation": _txt("#wob_pp"),
                "humidity": _txt("#wob_hm"),
                "wind": _txt("#wob_ws"),
            }
            if any(v for k, v in data.items() if k not in {"type"}):
                return data
        except Exception:
            return None
        return None

    def _extract_google_finance_widget(self, page) -> dict[str, Any] | None:
        # This is intentionally heuristic: Google finance widgets vary heavily.
        # We detect common price/quote patterns and return the most visible candidate.
        try:
            candidates = []
            # Common knowledge panel / finance quote containers.
            for sel in (
                "g-card",
                "div[data-attrid='kc:/finance/stock_price']",
                "div[data-attrid='kc:/finance/crypto_price']",
                "div[data-attrid='kc:/finance/stock_quote']",
                "div[data-attrid='kc:/finance/crypto_quote']",
                "#knowledge-finance-wholepage__entity-summary",
            ):
                try:
                    loc = page.locator(sel).first
                    if loc.count() == 0:
                        continue
                    txt = (loc.inner_text() or "").strip()
                    txt = re.sub(r"\s+", " ", txt)
                    if len(txt) < 40:
                        continue
                    candidates.append((sel, txt[:800]))
                except Exception:
                    continue

            # Also try explicit price-like spans (works for many crypto queries).
            for sel in ("span[jsname='vWLAgc']", "span[jsname='V67aGc']", "div[role='heading'] span"):
                try:
                    loc = page.locator(sel).first
                    if loc.count() == 0:
                        continue
                    t = (loc.inner_text() or "").strip()
                    if re.search(r"[\$₹€£]\s?\d", t) or re.search(r"\d[\d,]*\.\d", t):
                        candidates.append((sel, t))
                except Exception:
                    continue

            if not candidates:
                return None

            # Pick the longest candidate as it tends to contain name + price + change.
            sel, snippet = sorted(candidates, key=lambda x: len(x[1]), reverse=True)[0]
            return {"type": "finance", "selector": sel, "text": snippet}
        except Exception:
            return None

    def _extract_google(self, page) -> list[SearchHit]:
        hits: list[SearchHit] = []
        try:
            page.wait_for_selector("#search", timeout=15000)
        except Exception:
            return hits
        h3s = page.locator("#search a h3").all()[: self._cfg.max_results]
        for h3 in h3s:
            try:
                title = (h3.inner_text() or "").strip()
                if not title:
                    continue
                link_el = h3.locator("xpath=ancestor::a[1]").first
                href = (link_el.get_attribute("href") or "").strip()
                if not href.startswith("http"):
                    continue
                snippet = ""
                try:
                    container = h3.locator("xpath=ancestor::div[contains(@class,'g')][1]").first
                    txt = container.inner_text() or ""
                    snippet = re.sub(r"\s+", " ", txt.replace(title, "", 1)).strip()[:600]
                except Exception:
                    snippet = ""
                hits.append(SearchHit(title=title, url=href, snippet=snippet))
            except Exception:
                continue
        return hits

    def _extract_ddg_html(self, page) -> list[SearchHit]:
        hits: list[SearchHit] = []
        try:
            page.wait_for_selector("a.result__a", timeout=15000)
        except Exception:
            return hits
        links = page.locator("a.result__a").all()[: self._cfg.max_results]
        for a in links:
            try:
                title = (a.inner_text() or "").strip()
                href = (a.get_attribute("href") or "").strip()
                if not title or not href.startswith("http"):
                    continue
                snippet = ""
                try:
                    row = a.locator("xpath=ancestor::div[contains(@class,'result')][1]").first
                    snippet = re.sub(r"\s+", " ", row.inner_text() or "").strip()
                    snippet = snippet.replace(title, "", 1).strip()[:600]
                except Exception:
                    snippet = ""
                hits.append(SearchHit(title=title, url=href, snippet=snippet))
            except Exception:
                continue
        return hits

    def _extract_youtube(self, page) -> list[SearchHit]:
        hits: list[SearchHit] = []
        try:
            page.wait_for_selector("ytd-video-renderer a#video-title", timeout=20000)
        except Exception:
            return hits
        for a in page.locator("ytd-video-renderer a#video-title").all()[: self._cfg.max_results]:
            try:
                title = (a.inner_text() or "").strip()
                href = (a.get_attribute("href") or "").strip()
                if not title:
                    continue
                if href.startswith("/"):
                    href = f"https://www.youtube.com{href}"
                if not href.startswith("http"):
                    continue
                hits.append(SearchHit(title=title, url=href, snippet="YouTube result"))
            except Exception:
                continue
        return hits

    def _extract_wikipedia(self, page) -> list[SearchHit]:
        hits: list[SearchHit] = []
        try:
            if page.locator("#firstHeading").count() > 0:
                title = (page.locator("#firstHeading").inner_text() or "").strip()
                url = page.url
                snippet = ""
                try:
                    snippet = (page.locator("#mw-content-text > p").first.inner_text() or "").strip()[:700]
                except Exception:
                    snippet = ""
                if title:
                    hits.append(SearchHit(title=title, url=url, snippet=snippet))
                return hits
            page.wait_for_selector(".mw-search-result-heading a", timeout=15000)
        except Exception:
            return hits
        for a in page.locator(".mw-search-result-heading a").all()[: self._cfg.max_results]:
            try:
                title = (a.inner_text() or "").strip()
                href = (a.get_attribute("href") or "").strip()
                if not title or not href.startswith("http"):
                    continue
                hits.append(SearchHit(title=title, url=href, snippet="Wikipedia search result"))
            except Exception:
                continue
        return hits

    def _extract_bing(self, page) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for sel in ("#b_results li.b_algo", "#b_results .b_algo"):
            try:
                page.wait_for_selector(sel, timeout=12000)
                items = page.locator(sel).all()[: self._cfg.max_results]
                for li in items:
                    try:
                        link = li.locator("h2 a").first
                        title = (link.inner_text() or "").strip()
                        href = (link.get_attribute("href") or "").strip()
                        if not title or not href.startswith("http"):
                            continue
                        snippet = re.sub(r"\s+", " ", (li.locator("p").first.inner_text() or "").strip())[
                            :600
                        ]
                        hits.append(SearchHit(title=title, url=href, snippet=snippet))
                    except Exception:
                        continue
                if hits:
                    break
            except Exception:
                continue
        return hits

    def _run_on_page(self, url: str, extract: Callable[..., list[SearchHit]], *, provider: str) -> tuple[list[SearchHit], dict[str, Any], str, dict[str, Any]]:
        ctx = self._get_context()
        page = ctx.new_page()
        debug: dict[str, Any] = {"url": url, "provider": provider}
        try:
            self._debug("goto.start", url=url, provider=provider)
            page.goto(url, wait_until="domcontentloaded")
            self._maybe_accept_consent(page)
            self._wait_ready(page, provider=provider)

            widget: dict[str, Any] = {}
            if provider == "google":
                w = self._extract_google_weather_widget(page)
                if w:
                    widget["weather"] = w
                f = self._extract_google_finance_widget(page)
                if f:
                    widget["finance"] = f
                debug["has_weather_widget"] = bool(w)
                debug["has_finance_widget"] = bool(f)

            visible = self._visible_text(page)
            debug["visible_text_len"] = len(visible)

            hits = extract(page)
            debug["hits_count"] = len(hits)
            self._debug("extract.done", **debug)
            return hits, widget, visible, debug
        finally:
            try:
                page.close()
            except Exception:
                pass

    def search(self, query: str, provider: str) -> BrowserSearchResult:
        q = quote_plus(query)
        provider = (provider or self._cfg.default_provider).lower()
        if provider == "google":
            url = f"https://www.google.com/search?q={q}&hl=en"
            hits, widget, visible, debug = self._run_on_page(url, self._extract_google, provider="google")
            if len(hits) < 2 and not widget and len(visible) < 200:
                return self.search(query, "duckduckgo")
            return BrowserSearchResult(provider="google", hits=hits, widget_data=widget, visible_text_excerpt=visible, debug=debug)
        if provider in {"duckduckgo", "ddg"}:
            url = f"https://html.duckduckgo.com/html/?q={q}"
            hits, widget, visible, debug = self._run_on_page(url, self._extract_ddg_html, provider="duckduckgo")
            return BrowserSearchResult(provider="duckduckgo", hits=hits, widget_data=widget, visible_text_excerpt=visible, debug=debug)
        if provider == "bing":
            url = f"https://www.bing.com/search?q={q}&setlang=en-us"
            hits, widget, visible, debug = self._run_on_page(url, self._extract_bing, provider="bing")
            if len(hits) < 2 and not widget and len(visible) < 200:
                return self.search(query, "duckduckgo")
            return BrowserSearchResult(provider="bing", hits=hits, widget_data=widget, visible_text_excerpt=visible, debug=debug)
        if provider in {"brave", "brave_search"}:
            url = f"https://search.brave.com/search?q={q}"
            hits, widget, visible, debug = self._run_on_page(url, self._extract_google, provider="brave")
            if len(hits) < 2 and not widget and len(visible) < 200:
                return self.search(query, "duckduckgo")
            return BrowserSearchResult(provider="brave", hits=hits, widget_data=widget, visible_text_excerpt=visible, debug=debug)
        if provider in {"youtube", "yt"}:
            url = f"https://www.youtube.com/results?search_query={q}"
            hits, widget, visible, debug = self._run_on_page(url, self._extract_youtube, provider="youtube")
            if not hits:
                site_q = quote_plus(f"site:youtube.com {query}")
                hits, widget, visible, debug = self._run_on_page(
                    f"https://www.google.com/search?q={site_q}&hl=en", self._extract_google, provider="google"
                )
            return BrowserSearchResult(provider="youtube", hits=hits, widget_data=widget, visible_text_excerpt=visible, debug=debug)
        if provider in {"reddit"}:
            site_q = quote_plus(f"site:reddit.com {query}")
            url = f"https://www.google.com/search?q={site_q}&hl=en"
            hits, widget, visible, debug = self._run_on_page(url, self._extract_google, provider="google")
            return BrowserSearchResult(provider="reddit", hits=hits, widget_data=widget, visible_text_excerpt=visible, debug=debug)
        if provider in {"wikipedia", "wiki"}:
            url = f"https://en.wikipedia.org/w/index.php?search={q}&fulltext=1"
            hits, widget, visible, debug = self._run_on_page(url, self._extract_wikipedia, provider="wikipedia")
            if not hits:
                wiki_q = quote_plus(f"site:wikipedia.org {query}")
                hits, widget, visible, debug = self._run_on_page(
                    f"https://www.google.com/search?q={wiki_q}&hl=en", self._extract_google, provider="google"
                )
            return BrowserSearchResult(provider="wikipedia", hits=hits, widget_data=widget, visible_text_excerpt=visible, debug=debug)
        return self.search(query, "google")


_GLOBAL: PlaywrightSearchController | None = None


def get_controller(cfg: RealtimeSearchConfig) -> PlaywrightSearchController:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = PlaywrightSearchController(cfg)
    return _GLOBAL


def dispose_controller() -> None:
    global _GLOBAL
    if _GLOBAL is not None:
        _GLOBAL.close()
        _GLOBAL = None
