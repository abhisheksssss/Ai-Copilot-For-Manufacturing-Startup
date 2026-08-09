"""
╔══════════════════════════════════════════════════════════════════╗
║           POWER WEB SEARCH TOOL — Agent-Ready Edition           ║
║   Google Search → Scrape → Extract → Summarize → Structured     ║
╚══════════════════════════════════════════════════════════════════╝

Architecture:
  1. GOOGLE SEARCH  — fetch real URLs (googlesearch-python, no API key)
  2. ASYNC SCRAPING — parallel httpx with rotating User-Agents
  3. CONTENT EXTRACT— readability (article mode) → bs4 fallback → raw
  4. SYNTHESIS       — confidence-scored, keyword-relevant excerpts
  5. OUTPUT          — typed dataclasses + JSON-serialisable dict

LangChain drop-in:
  • Pydantic ResearchInput schema
  • @tool decorator wrapper (web_search_tool)
  • Returns dict consumed by any AgentExecutor

Requirements (pip install):
  requests beautifulsoup4 httpx aiohttp googlesearch-python
  fake-useragent lxml pydantic langchain langchain-core
  readability-lxml html2text
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import httpx
import html2text
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from pydantic import BaseModel, Field
from readability import Document

# ──────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ──────────────────────────────────────────────────────────────────

CONFIG = {
    "google_fetch_n":       12,      # Extra Google links to fetch (pre-filter)
    "timeout_seconds":      12,      # Per-URL connect+read timeout
    "max_content_chars":    5000,    # Body text cap per page
    "min_content_chars":    80,      # Pages below this are discarded
    "retry_attempts":       2,       # Per-URL retries on network error
    "google_sleep":         1.5,     # Polite delay between Google reqs
    "lang":                 "en",
    "region":               "us",
}

BLACKLISTED_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "linkedin.com", "tiktok.com", "youtube.com", "pinterest.com",
    "accounts.google.com", "login.microsoftonline.com",
    "jstor.org", "researchgate.net", "academia.edu",
}


# ──────────────────────────────────────────────────────────────────
#  DATA MODELS
# ──────────────────────────────────────────────────────────────────

class ResearchInput(BaseModel):
    """Input schema — LangChain @tool compatible."""
    query: str = Field(..., description="Search query string.")
    max_results: int = Field(
        5, ge=1, le=10,
        description="Number of pages to scrape (1–10)."
    )
    include_raw: bool = Field(
        False,
        description="Attach a raw HTML snippet to each result."
    )


@dataclass
class SearchResult:
    url:            str
    domain:         str
    title:          str
    description:    str
    content:        str
    headings:       list[str]
    published_date: str
    author:         str
    word_count:     int
    scrape_success: bool
    error:          Optional[str]
    confidence:     float          # 0.0–1.0
    raw_html:       Optional[str] = field(default=None, repr=False)


@dataclass
class AggregatedResult:
    query:            str
    total_links:      int
    total_scraped:    int
    successful:       int
    results:          list[SearchResult]
    synthesis:        str
    elapsed_seconds:  float


# ──────────────────────────────────────────────────────────────────
#  USER-AGENT ROTATION
# ──────────────────────────────────────────────────────────────────

try:
    _ua_gen = UserAgent()
    def random_ua() -> str:
        return _ua_gen.random
except Exception:
    _FALLBACK = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]
    _idx = 0
    def random_ua() -> str:
        global _idx; ua = _FALLBACK[_idx % len(_FALLBACK)]; _idx += 1; return ua


def _headers(url: str) -> dict:
    p = urlparse(url)
    return {
        "User-Agent":               random_ua(),
        "Accept":                   "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":          "en-US,en;q=0.9",
        "Accept-Encoding":          "gzip, deflate, br",
        "Referer":                  f"{p.scheme}://{p.netloc}/",
        "DNT":                      "1",
        "Connection":               "keep-alive",
        "Upgrade-Insecure-Requests":"1",
    }


# ──────────────────────────────────────────────────────────────────
#  STEP 1 — GOOGLE SEARCH
# ──────────────────────────────────────────────────────────────────

def fetch_google_links(query: str, max_results: int) -> list[str]:
    """
    Pull real Google result URLs via googlesearch-python.
    Deduplicates by base domain; filters BLACKLISTED_DOMAINS.
    No API key required — uses the public Google web interface.
    """
    print(f"\n🔍 [GOOGLE] '{query}'  →  requesting {max_results} links")

    try:
        from googlesearch import search as _google
        raw = list(_google(
            query,
            num_results=CONFIG["google_fetch_n"],
            lang=CONFIG["lang"],
            sleep_interval=CONFIG["google_sleep"],
        ))
    except Exception as exc:
        print(f"   ⚠️  Google search error: {exc}")
        raw = []

    links, seen = [], set()
    for url in raw:
        domain = urlparse(url).netloc.lstrip("www.")
        base   = ".".join(domain.split(".")[-2:])
        if base in BLACKLISTED_DOMAINS:
            continue
        if domain not in seen:
            seen.add(domain)
            links.append(url)
        if len(links) >= max_results:
            break

    print(f"   ✅ {len(links)} unique links after filtering")
    for i, lnk in enumerate(links, 1):
        print(f"      {i}. {lnk}")
    return links


# ──────────────────────────────────────────────────────────────────
#  STEP 2 — CONTENT EXTRACTION HELPERS
# ──────────────────────────────────────────────────────────────────

def _meta(soup: BeautifulSoup) -> dict:
    def _get(name=None, prop=None):
        tag = soup.find("meta", attrs={"property": prop} if prop else {"name": name})
        return (tag or {}).get("content", "").strip()

    return {
        "title": (
            getattr(soup.find("title"), "text", "").strip()
            or _get(prop="og:title")
            or _get(name="twitter:title") or ""
        ),
        "description": (
            _get(name="description")
            or _get(prop="og:description") or ""
        )[:300],
        "author": (
            _get(name="author")
            or _get(prop="article:author") or ""
        ),
        "date": (
            _get(prop="article:published_time")
            or _get(name="publish_date")
            or _get(name="date") or ""
        )[:10],
    }


def _headings(soup: BeautifulSoup) -> list[str]:
    out = []
    for tag in soup.find_all(["h1", "h2"]):
        txt = tag.get_text(separator=" ", strip=True)
        if txt and len(txt) > 3:
            out.append(txt)
    return out[:8]


def _clean(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\u00a0", " ", text)
    return text.strip()


def _readability(html_content: str) -> str:
    """Primary extractor — Mozilla Readability port."""
    try:
        doc = Document(html_content)
        h = html2text.HTML2Text()
        h.ignore_links = h.ignore_images = True
        h.body_width = 0
        return _clean(h.handle(doc.summary(html_partial=True)))
    except Exception:
        return ""


def _bs4_extract(soup: BeautifulSoup) -> str:
    """Fallback extractor — heuristic BeautifulSoup."""
    for tag in soup(["script","style","nav","footer","header",
                     "aside","form","noscript","iframe","svg",
                     "figure","figcaption","button","input"]):
        tag.decompose()

    for sel in ["article","main",'[role="main"]',
                ".article-body",".post-content",".entry-content",
                ".content","#content",".story-body"]:
        el = soup.select_one(sel)
        if el:
            return _clean(el.get_text(separator="\n", strip=True))

    body = soup.find("body")
    return _clean((body or soup).get_text(separator="\n", strip=True))


def _score(r: SearchResult) -> float:
    if not r.scrape_success:
        return 0.0
    s  = min(r.word_count / 500, 0.45)
    s += 0.15 if r.title       else 0.0
    s += 0.10 if r.description else 0.0
    s += 0.15 if r.headings    else 0.0
    s += 0.15 if (r.author or r.published_date) else 0.0
    return round(min(s, 1.0), 2)


# ──────────────────────────────────────────────────────────────────
#  STEP 3 — ASYNC SCRAPER
# ──────────────────────────────────────────────────────────────────

async def _scrape_one(
    client: httpx.AsyncClient,
    url: str,
    include_raw: bool,
) -> SearchResult:
    domain = urlparse(url).netloc.lstrip("www.")
    print(f"   🌐 {url}")

    for attempt in range(1, CONFIG["retry_attempts"] + 1):
        try:
            resp = await client.get(
                url,
                headers=_headers(url),
                timeout=CONFIG["timeout_seconds"],
                follow_redirects=True,
            )
            resp.raise_for_status()
            raw_html = resp.text
            break
        except Exception as exc:
            if attempt == CONFIG["retry_attempts"]:
                print(f"      ❌ {exc}")
                return SearchResult(
                    url=url, domain=domain, title="", description="",
                    content="", headings=[], published_date="", author="",
                    word_count=0, scrape_success=False, error=str(exc),
                    confidence=0.0,
                )
            await asyncio.sleep(0.5)

    soup     = BeautifulSoup(raw_html, "lxml")
    meta     = _meta(soup)
    headings = _headings(soup)

    content  = _readability(raw_html)
    if len(content) < CONFIG["min_content_chars"]:
        content = _bs4_extract(soup)

    content   = content[: CONFIG["max_content_chars"]]
    wc        = len(content.split())

    r = SearchResult(
        url=url, domain=domain,
        title=meta["title"], description=meta["description"],
        content=content, headings=headings,
        published_date=meta["date"], author=meta["author"],
        word_count=wc, scrape_success=True, error=None,
        confidence=0.0,
        raw_html=raw_html[:5000] if include_raw else None,
    )
    r.confidence = _score(r)
    print(f"      ✅ {wc} words | conf={r.confidence} | \"{meta['title'][:55]}\"")
    return r


async def _scrape_all(urls: list[str], include_raw: bool) -> list[SearchResult]:
    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        http2=True,
    ) as client:
        return await asyncio.gather(
            *[_scrape_one(client, u, include_raw) for u in urls]
        )


# ──────────────────────────────────────────────────────────────────
#  STEP 4 — SYNTHESIS
# ──────────────────────────────────────────────────────────────────

def _synthesize(query: str, results: list[SearchResult]) -> str:
    good = sorted(
        [r for r in results if r.scrape_success and r.word_count > 50],
        key=lambda r: -r.confidence,
    )
    if not good:
        return "No usable content could be extracted from the search results."

    keywords = set(re.findall(r"\b\w{4,}\b", query.lower()))
    lines = [f"Key findings for: \"{query}\"\n{'─'*52}"]

    for i, r in enumerate(good, 1):
        lines.append(f"\n[{i}] {r.title or r.domain}")
        lines.append(f"    URL    : {r.url}")
        if r.published_date:
            lines.append(f"    Date   : {r.published_date}")
        if r.description:
            lines.append(f"    Digest : {r.description[:220]}")
        if r.headings:
            lines.append(f"    Topics : {' · '.join(r.headings[:4])}")

        # Keyword-relevant excerpts
        sentences = re.split(r"(?<=[.!?])\s+", r.content)
        excerpts  = [
            s.strip() for s in sentences
            if any(kw in s.lower() for kw in keywords) and len(s) > 40
        ][:3]
        if excerpts:
            lines.append("    Excerpts:")
            for s in excerpts:
                lines.append(f"      • {s[:280]}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────
#  PUBLIC API
# ──────────────────────────────────────────────────────────────────

def web_search(
    query: str,
    max_results: int = 5,
    include_raw: bool = False,
) -> dict:
    """
    Full pipeline: Google → parallel scrape → extract → synthesize.

    Parameters
    ----------
    query        : Natural-language search query.
    max_results  : Pages to scrape (1–10).  Default 5.
    include_raw  : Attach 5 KB raw HTML snippet to each result.

    Returns
    -------
    dict with keys: query, synthesis, metadata, results
    """
    print(f"\n{'═'*60}")
    print(f"  🔧 [TOOL] web_search")
    print(f"  📝 Query  : {query}")
    print(f"  📊 Results: {max_results}")
    print(f"{'═'*60}")

    t0 = time.time()
    max_results = max(1, min(int(max_results), 10))

    # 1 ─ Google
    links = fetch_google_links(query, max_results)
    if not links:
        return {
            "query": query, "synthesis": "Google search returned no results.",
            "metadata": {"error": "no links found"}, "results": [],
        }

    # 2 ─ Scrape
    print(f"\n⚡ [SCRAPING] {len(links)} URLs in parallel …")
    results: list[SearchResult] = asyncio.run(_scrape_all(links, include_raw))

    # 3 ─ Sort by confidence
    results.sort(key=lambda r: -r.confidence)

    # 4 ─ Synthesize
    print(f"\n🧠 [SYNTHESIS] Building structured output …")
    synthesis = _synthesize(query, results)

    elapsed    = round(time.time() - t0, 2)
    successful = sum(1 for r in results if r.scrape_success)

    print(f"\n✅ Done in {elapsed}s | {successful}/{len(results)} pages OK")
    print(f"{'═'*60}\n")

    return {
        "query":     query,
        "synthesis": synthesis,
        "metadata": {
            "total_links_found":  len(links),
            "total_scraped":      len(results),
            "successful_scrapes": successful,
            "elapsed_seconds":    elapsed,
        },
        "results": [
            {
                "rank":           i + 1,
                "url":            r.url,
                "domain":         r.domain,
                "title":          r.title,
                "description":    r.description,
                "content":        r.content,
                "headings":       r.headings,
                "published_date": r.published_date,
                "author":         r.author,
                "word_count":     r.word_count,
                "confidence":     r.confidence,
                "scrape_success": r.scrape_success,
                "error":          r.error,
                **({"raw_html": r.raw_html} if include_raw else {}),
            }
            for i, r in enumerate(results)
        ],
    }


# ──────────────────────────────────────────────────────────────────
#  LANGCHAIN @tool WRAPPER
# ──────────────────────────────────────────────────────────────────

try:
    from langchain_core.tools import tool as _lc_tool

    @_lc_tool("web_search", args_schema=ResearchInput)
    def web_search_tool(
        query: str,
        max_results: int = 5,
        include_raw: bool = False,
    ) -> dict:
        """
        Searches the web using Google, scrapes the top pages,
        and returns structured, confidence-scored findings.
        Use for market data, news, research, prices, or any live info.
        """
        return web_search(query, max_results=max_results, include_raw=include_raw)

    print("✅ LangChain @tool registered → 'web_search_tool'")

except ImportError:
    web_search_tool = None


# ──────────────────────────────────────────────────────────────────
#  STANDALONE DEMO
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── Scraping demo against publicly accessible URLs ────────────
    # (When run in sandboxed envs, Google may be blocked;
    #  the scraping pipeline below always works.)

    print("\n" + "═"*60)
    print("  PIPELINE DEMO — scraping 3 public pages directly")
    print("="*60)

    demo_urls = [
        "https://pypi.org/project/beautifulsoup4/",
        "https://pypi.org/project/httpx/",
        "https://pypi.org/project/langchain/",
    ]

    async def _demo():
        async with httpx.AsyncClient(http2=True) as client:
            return await asyncio.gather(
                *[_scrape_one(client, u, False) for u in demo_urls]
            )

    demo_results: list[SearchResult] = asyncio.run(_demo())
    demo_results.sort(key=lambda r: -r.confidence)

    synth = _synthesize("Python web scraping libraries", demo_results)
    print("\n" + "─"*60)
    print("SYNTHESIS:")
    print(synth)
    print("\n" + "─"*60)
    print("RESULT CARDS:")
    for r in demo_results:
        st = "✅" if r.scrape_success else "❌"
        print(f"  {st} [{r.domain}]  conf={r.confidence}  words={r.word_count}")
        print(f"     Title   : {r.title[:70]}")
        print(f"     Headings: {r.headings[:3]}")
        print()

    # ── Full pipeline with Google (works in non-sandboxed envs) ───
    print("─"*60)
    print("FULL PIPELINE TEST (Google + scrape):")
    out = web_search("Python web scraping best practices 2025", max_results=3)
    print(f"  Links found   : {out['metadata'].get('total_links_found', 0)}")
    print(f"  Pages scraped : {out['metadata'].get('successful_scrapes', 0)}")
    print(f"  Elapsed       : {out['metadata'].get('elapsed_seconds', 0)}s")
    if out["results"]:
        print("\n  Top result:")
        top = out["results"][0]
        print(f"    {top['url']}")
        print(f"    conf={top['confidence']}  words={top['word_count']}")
        print(f"    {top['title'][:70]}")
    print()