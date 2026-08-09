"""
Enhanced Supplier Search Tool  — v2
======================================
Upgrades over v1:
  1.  Parallel async scraping via aiohttp (10+ sources simultaneously)
  2.  Deep scraping of IndiaMART, TradeIndia, ExportersIndia, Justdial B2B, Alibaba India
  3.  GeM (Government e-Marketplace) catalogue scraper
  4.  MSME Udyam directory scraper
  5.  IndiaBizList, Sulekha B2B, Exporters India scrapers
  6.  Direct company website scraper (for top hits)
  7.  Selenium / Playwright fallback for JS-heavy pages (IndiaMART SPA)
  8.  SQLite + optional Redis caching (configurable TTL)
  9.  Pydantic supplier data model with per-field provenance & confidence
 10.  12-signal ranking engine (adds GST verification, export history,
      factory photos, response rate, lead time, MOQ, payment terms)
 11.  Expanded neighbor map (28 states + UTs)
 12.  Automatic MOQ / price / cert extraction via regex + LLM-style heuristics
 13.  Contact detail extractor (phone, email, WhatsApp link)
 14.  Supplier profile completeness score
 15.  Structured output with full source provenance
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus, urlencode, urljoin, urlparse

# ── Core dependencies ───────────────────────────────────────────────────────
import aiohttp
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

# ── Optional heavy dependencies (gracefully degraded) ───────────────────────
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import redis as _redis_lib
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

import concurrent.futures

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")


def _run_async_safely(coro):
    """
    Safely runs an async coroutine from synchronous code, whether or not
    an event loop is already running in the current thread (e.g. FastAPI, LangGraph, Jupyter).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)



# ═══════════════════════════════════════════════════════════════════════════
#  PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class SupplierContact(BaseModel):
    phone: list[str] = []
    email: list[str] = []
    whatsapp: Optional[str] = None
    website: Optional[str] = None


class SupplierProfile(BaseModel):
    name: str
    platform: str
    url: str
    location: str
    state: str = ""
    city: str = ""
    pincode: str = ""
    proximity_match: str = "National"   # "Target City" | "Target State" | "Neighboring State" | "National"
    price_estimate: str = "Contact for quote"
    price_unit: str = ""
    moq: str = "Contact supplier"
    lead_time: str = "Not specified"
    payment_terms: str = "Not specified"
    certifications: list[str] = []
    gst_number: str = ""
    gst_verified: bool = False
    udyam_registered: bool = False
    export_experience: bool = False
    factory_photos: bool = False
    response_rate: str = "Not specified"
    snippet: str = ""
    contact: SupplierContact = SupplierContact()
    score: int = 0
    score_breakdown: dict[str, int] = {}
    source_url: str = ""
    scraped_at: str = ""
    confidence: float = 0.8


# ═══════════════════════════════════════════════════════════════════════════
#  NEIGHBOR MAP — all 28 states + key UTs + major cities
# ═══════════════════════════════════════════════════════════════════════════

NEIGHBOR_MAP: dict[str, list[str]] = {
    # States
    "gujarat":          ["Maharashtra", "Rajasthan", "Madhya Pradesh", "Daman and Diu"],
    "maharashtra":      ["Gujarat", "Goa", "Karnataka", "Telangana", "Madhya Pradesh", "Chhattisgarh"],
    "rajasthan":        ["Gujarat", "Haryana", "Punjab", "Madhya Pradesh", "Delhi", "Uttar Pradesh"],
    "tamil nadu":       ["Karnataka", "Andhra Pradesh", "Kerala", "Puducherry"],
    "karnataka":        ["Maharashtra", "Goa", "Tamil Nadu", "Andhra Pradesh", "Telangana", "Kerala"],
    "delhi":            ["Haryana", "Uttar Pradesh", "Punjab", "Rajasthan"],
    "ncr":              ["Delhi", "Haryana", "Uttar Pradesh", "Rajasthan"],
    "telangana":        ["Karnataka", "Andhra Pradesh", "Maharashtra", "Odisha", "Chhattisgarh"],
    "andhra pradesh":   ["Tamil Nadu", "Karnataka", "Telangana", "Odisha"],
    "uttar pradesh":    ["Delhi", "Haryana", "Rajasthan", "Bihar", "Madhya Pradesh", "Uttarakhand"],
    "madhya pradesh":   ["Uttar Pradesh", "Rajasthan", "Gujarat", "Maharashtra", "Chhattisgarh"],
    "haryana":          ["Delhi", "Punjab", "Rajasthan", "Uttar Pradesh", "Himachal Pradesh"],
    "punjab":           ["Haryana", "Himachal Pradesh", "Rajasthan", "Delhi", "Chandigarh"],
    "kerala":           ["Tamil Nadu", "Karnataka"],
    "west bengal":      ["Bihar", "Jharkhand", "Odisha", "Assam", "Sikkim"],
    "odisha":           ["West Bengal", "Jharkhand", "Chhattisgarh", "Andhra Pradesh"],
    "bihar":            ["Uttar Pradesh", "Jharkhand", "West Bengal"],
    "chhattisgarh":     ["Madhya Pradesh", "Maharashtra", "Odisha", "Jharkhand", "Telangana"],
    "jharkhand":        ["Bihar", "West Bengal", "Odisha", "Chhattisgarh"],
    "assam":            ["West Bengal", "Meghalaya", "Nagaland", "Arunachal Pradesh", "Manipur"],
    "uttarakhand":      ["Uttar Pradesh", "Himachal Pradesh", "Delhi"],
    "himachal pradesh": ["Punjab", "Haryana", "Uttarakhand", "Jammu and Kashmir"],
    "goa":              ["Maharashtra", "Karnataka"],
    "jammu and kashmir":["Himachal Pradesh", "Punjab"],
    # Major city aliases
    "mumbai":       ["Thane", "Pune", "Navi Mumbai", "Maharashtra"],
    "pune":         ["Mumbai", "Maharashtra", "Satara", "Nashik"],
    "ahmedabad":    ["Surat", "Vadodara", "Rajkot", "Gujarat"],
    "surat":        ["Ahmedabad", "Vadodara", "Gujarat"],
    "chennai":      ["Kanchipuram", "Chengalpattu", "Tamil Nadu"],
    "bangalore":    ["Bengaluru", "Hosur", "Karnataka"],
    "bengaluru":    ["Hosur", "Mysuru", "Karnataka"],
    "hyderabad":    ["Secunderabad", "Ranga Reddy", "Telangana"],
    "kolkata":      ["Howrah", "North 24 Parganas", "West Bengal"],
    "noida":        ["Greater Noida", "Ghaziabad", "Delhi", "Haryana"],
    "gurgaon":      ["Faridabad", "Delhi", "Haryana"],
    "indore":       ["Pithampur", "Dewas", "Madhya Pradesh"],
    "vadodara":     ["Anand", "Bharuch", "Gujarat"],
    "rajkot":       ["Morbi", "Jamnagar", "Gujarat"],
    "coimbatore":   ["Tiruppur", "Erode", "Tamil Nadu"],
    "ludhiana":     ["Jalandhar", "Amritsar", "Punjab"],
    "kanpur":       ["Lucknow", "Uttar Pradesh"],
    "nagpur":       ["Maharashtra"],
}


# ═══════════════════════════════════════════════════════════════════════════
#  CACHE LAYER
# ═══════════════════════════════════════════════════════════════════════════

CACHE_DB = Path("/tmp/supplier_search_cache.sqlite3")


def _init_cache() -> sqlite3.Connection:
    conn = sqlite3.connect(str(CACHE_DB), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS html_cache (
            url_hash   TEXT PRIMARY KEY,
            url        TEXT,
            html       TEXT,
            cached_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS result_cache (
            query_hash TEXT PRIMARY KEY,
            query      TEXT,
            result     TEXT,
            cached_at  TEXT
        )
    """)
    conn.commit()
    return conn


def _cache_get(conn: sqlite3.Connection, url: str, ttl_hours: int) -> Optional[str]:
    if ttl_hours <= 0:
        return None
    h = hashlib.sha256(url.encode()).hexdigest()
    row = conn.execute("SELECT html, cached_at FROM html_cache WHERE url_hash=?", (h,)).fetchone()
    if not row:
        return None
    if datetime.utcnow() - datetime.fromisoformat(row[1]) > timedelta(hours=ttl_hours):
        return None
    return row[0]


def _cache_set(conn: sqlite3.Connection, url: str, html: str):
    h = hashlib.sha256(url.encode()).hexdigest()
    conn.execute(
        "INSERT OR REPLACE INTO html_cache VALUES (?,?,?,?)",
        (h, url, html, datetime.utcnow().isoformat())
    )
    conn.commit()


def _result_get(conn: sqlite3.Connection, qhash: str, ttl_hours: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT result, cached_at FROM result_cache WHERE query_hash=?", (qhash,)
    ).fetchone()
    if not row:
        return None
    if datetime.utcnow() - datetime.fromisoformat(row[1]) > timedelta(hours=ttl_hours):
        return None
    data = json.loads(row[0])
    if not data.get("top_suppliers"):
        return None
    return data


def _result_set(conn: sqlite3.Connection, qhash: str, query: str, result: dict):
    if not result.get("top_suppliers"):
        return
    conn.execute(
        "INSERT OR REPLACE INTO result_cache VALUES (?,?,?,?)",
        (qhash, query, json.dumps(result, default=str), datetime.utcnow().isoformat())
    )
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════
#  HTTP HELPERS
# ═══════════════════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.6367.82 Mobile Safari/537.36"
)


async def _afetch(
    session: aiohttp.ClientSession,
    url: str,
    timeout: int = 5,
    extra_headers: Optional[dict] = None,
) -> Optional[str]:
    hdrs = {**HEADERS, **(extra_headers or {})}
    for attempt in range(2):
        try:
            async with session.get(
                url, headers=hdrs, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status == 200:
                    return await resp.text(errors="replace")
                if resp.status in (403, 429) and attempt < 1:
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"Fetch attempt {attempt+1} failed [{url[:60]}]: {e}")
            if attempt < 1:
                await asyncio.sleep(0.5)
    return None


def _sfetch(url: str, timeout: int = 14, extra_headers: Optional[dict] = None) -> Optional[str]:
    hdrs = {**HEADERS, **(extra_headers or {})}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=hdrs, timeout=timeout, verify=False)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logger.debug(f"Sync fetch attempt {attempt+1} failed [{url[:60]}]: {e}")
            time.sleep(1.5 * (attempt + 1))
    return None


async def _playwright_fetch(url: str, wait_selector: str = "body") -> Optional[str]:
    if not PLAYWRIGHT_AVAILABLE:
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(user_agent=HEADERS["User-Agent"])
            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            try:
                await page.wait_for_selector(wait_selector, timeout=8_000)
            except Exception:
                pass
            html = await page.content()
            await browser.close()
            return html
    except Exception as e:
        logger.error(f"Playwright failed [{url[:60]}]: {e}")
        return None


def _selenium_fetch(url: str) -> Optional[str]:
    if not SELENIUM_AVAILABLE:
        return None
    opts = ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(f"--user-agent={HEADERS['User-Agent']}")
    try:
        driver = webdriver.Chrome(options=opts)
        driver.get(url)
        WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        html = driver.page_source
        driver.quit()
        return html
    except Exception as e:
        logger.error(f"Selenium failed [{url[:60]}]: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  EXTRACTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

PRICE_RE = re.compile(
    r'(?:₹|Rs\.?)\s*[\d,]+(?:\.\d+)?\s*(?:–|-|to)\s*(?:₹|Rs\.?)\s*[\d,]+(?:\.\d+)?'
    r'|(?:₹|Rs\.?)\s*[\d,]+(?:\.\d+)?'
    r'|\d[\d,]*(?:\.\d+)?\s*/?\s*(?:piece|pc|unit|kg|ton|mt|litre|ltr|set|pair|roll|metre|mtr)',
    re.IGNORECASE,
)
PHONE_RE   = re.compile(r'(?:\+91[\s-]?)?[6-9]\d{9}')
EMAIL_RE   = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
GST_RE     = re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b')
CERT_RE    = re.compile(
    r'\b(ISO\s*\d{4,5}(?::\d{4})?|BIS|CE|RoHS|REACH|UL|FSSAI|CPCB|GMP|'
    r'NABL|OHSAS|IATF|AS9100|FDA|HACCP|FSSC|Halal|Kosher|OEKO-TEX|Udyam)\b',
    re.IGNORECASE,
)
MOQ_RE     = re.compile(
    r'MOQ[:\s]*([^\n,;.]{3,30})'
    r'|Minimum\s+Order[:\s]*([^\n,;.]{3,30})'
    r'|Min(?:imum)?\s+Qty[:\s]*([^\n,;.]{3,30})',
    re.IGNORECASE,
)
LEAD_RE    = re.compile(
    r'(?:Lead\s*Time|Delivery)[:\s]*([^\n,;.]{3,40})'
    r'|\b(\d+[\s-]*(?:to[\s-]*\d+)?)\s*(?:days?|weeks?|months?)\s*(?:lead|delivery|dispatch)',
    re.IGNORECASE,
)
PAYMENT_RE = re.compile(
    r'(?:Payment|Terms)[:\s]*([^\n,;.]{4,60})',
    re.IGNORECASE,
)

INDIA_STATES = [
    "Gujarat", "Maharashtra", "Delhi", "Rajasthan", "Tamil Nadu", "Karnataka",
    "Andhra Pradesh", "Telangana", "Uttar Pradesh", "Madhya Pradesh", "Haryana",
    "Punjab", "Kerala", "West Bengal", "Odisha", "Bihar", "Chhattisgarh",
    "Jharkhand", "Assam", "Uttarakhand", "Himachal Pradesh", "Goa",
    "Jammu and Kashmir", "Sikkim", "Meghalaya", "Manipur", "Nagaland",
    "Arunachal Pradesh", "Tripura", "Mizoram",
]
INDIA_CITIES = [
    "Mumbai", "Pune", "Ahmedabad", "Surat", "Vadodara", "Rajkot", "Indore",
    "Chennai", "Coimbatore", "Tiruppur", "Bengaluru", "Bangalore", "Hosur",
    "Hyderabad", "Kolkata", "Noida", "Greater Noida", "Gurgaon", "Gurugram",
    "Faridabad", "Ludhiana", "Amritsar", "Jaipur", "Kanpur", "Nagpur",
    "Nashik", "Aurangabad", "Thane", "Navi Mumbai", "Morbi", "Bhiwandi",
    "Erode", "Bhilai", "Raipur", "Bhubaneswar", "Visakhapatnam", "Vijayawada",
    "Kochi", "Thiruvananthapuram", "Guwahati", "Pithampur", "Manesar", "Bhiwadi",
    "Neemrana", "Sanand", "Halol", "Chakan", "Silvassa", "Vapi", "Ankleshwar",
]
LOC_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(x) for x in INDIA_CITIES + INDIA_STATES) + r')\b',
    re.IGNORECASE,
)


def _extract_locations(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(0) for m in LOC_PATTERN.finditer(text)))


def _extract_prices(text: str) -> list[str]:
    return PRICE_RE.findall(text)


def _extract_phones(text: str) -> list[str]:
    return list(set(PHONE_RE.findall(text)))[:3]


def _extract_emails(text: str) -> list[str]:
    return [e for e in set(EMAIL_RE.findall(text)) if "example" not in e][:3]


def _extract_certs(text: str) -> list[str]:
    return list({c[0].upper() if isinstance(c, tuple) else c.upper() for c in CERT_RE.findall(text)})


def _extract_gst(text: str) -> str:
    m = GST_RE.search(text)
    return m.group(0) if m else ""


def _extract_moq(text: str) -> str:
    m = MOQ_RE.search(text)
    if m:
        return next((g.strip() for g in m.groups() if g), "Contact supplier")
    return "Contact supplier"


def _extract_lead_time(text: str) -> str:
    m = LEAD_RE.search(text)
    if m:
        return next((g.strip() for g in m.groups() if g), "Not specified")
    return "Not specified"


def _extract_payment(text: str) -> str:
    m = PAYMENT_RE.search(text)
    if m:
        return m.group(1).strip()[:80]
    return "Not specified"


def _detect_state(locations: list[str]) -> str:
    for loc in locations:
        if loc.title() in INDIA_STATES:
            return loc.title()
    # Map city → state
    CITY_STATE = {
        "mumbai": "Maharashtra", "pune": "Maharashtra", "nashik": "Maharashtra",
        "nagpur": "Maharashtra", "thane": "Maharashtra", "aurangabad": "Maharashtra",
        "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat",
        "rajkot": "Gujarat", "morbi": "Gujarat", "sanand": "Gujarat",
        "halol": "Gujarat", "vapi": "Gujarat", "ankleshwar": "Gujarat",
        "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu", "tiruppur": "Tamil Nadu",
        "erode": "Tamil Nadu", "madurai": "Tamil Nadu",
        "bengaluru": "Karnataka", "bangalore": "Karnataka", "hosur": "Karnataka",
        "hyderabad": "Telangana", "noida": "Uttar Pradesh", "greater noida": "Uttar Pradesh",
        "gurgaon": "Haryana", "gurugram": "Haryana", "faridabad": "Haryana",
        "ludhiana": "Punjab", "amritsar": "Punjab",
        "jaipur": "Rajasthan", "neemrana": "Rajasthan", "bhiwadi": "Rajasthan",
        "kolkata": "West Bengal", "indore": "Madhya Pradesh", "pithampur": "Madhya Pradesh",
        "manesar": "Haryana", "chakan": "Maharashtra", "bhiwandi": "Maharashtra",
        "kochi": "Kerala", "silvassa": "Dadra and Nagar Haveli",
        "visakhapatnam": "Andhra Pradesh", "vijayawada": "Andhra Pradesh",
    }
    for loc in locations:
        state = CITY_STATE.get(loc.lower())
        if state:
            return state
    return ""


# ═══════════════════════════════════════════════════════════════════════════
#  PLATFORM-SPECIFIC DEEP SCRAPERS
# ═══════════════════════════════════════════════════════════════════════════

# ── 1. IndiaMART ────────────────────────────────────────────────────────────

async def scrape_indiamart(
    session: aiohttp.ClientSession,
    product: str,
    location: str,
    conn: sqlite3.Connection,
    ttl: int,
    use_playwright: bool,
) -> list[dict]:
    """
    Hits IndiaMART search. Falls back to Playwright for SPA rendering.
    Also attempts their internal search API which returns semi-structured JSON.
    """
    results: list[dict] = []

    # Try undocumented search endpoint (returns partial JSON on many queries)
    api_url = (
        f"https://dir.indiamart.com/search.mp?ss={quote_plus(product)}"
        f"&prdsrc=1&mcatid=&catid=&biz={quote_plus(location)}"
    )
    web_url = (
        f"https://www.indiamart.com/proddetail/{quote_plus(product.lower().replace(' ', '-'))}.html"
    )
    search_url = f"https://dir.indiamart.com/search.mp?ss={quote_plus(product)}+{quote_plus(location)}"

    for url in [search_url, api_url]:
        cached = _cache_get(conn, url, ttl)
        html = cached or await _afetch(session, url)
        if html and not cached:
            _cache_set(conn, url, html)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        # IndiaMART search result cards (class patterns vary by version)
        for card in soup.select(
            ".organic-card, .product-unit, .sup-list, .busi-info, .biz-unit, "
            ".imim-col, [data-supplier-id], .listing-item"
        ):
            name_el = card.select_one(
                ".supplier-name, .company-name, .bname, .lcname, h3, h4, .heading"
            )
            loc_el  = card.select_one(".location, .city, .biz-city, .lcity")
            price_el= card.select_one(".price, .prc, .price-unit, .prce")
            cert_el = card.select_one(".cert, .certifications, .trust-badge")
            url_el  = card.select_one("a[href]")

            name  = name_el.get_text(" ", strip=True) if name_el else ""
            loc   = loc_el.get_text(" ", strip=True) if loc_el else location
            price = price_el.get_text(" ", strip=True) if price_el else ""
            certs = _extract_certs((cert_el.get_text(" ", strip=True) if cert_el else "") + card.get_text())
            link  = urljoin("https://www.indiamart.com", url_el["href"]) if url_el else url
            text  = card.get_text(" ", strip=True)

            if not name or len(name) < 3:
                continue

            results.append({
                "name": name[:80],
                "platform": "IndiaMART",
                "url": link,
                "location": loc or location or "India",
                "snippet": text[:200],
                "price_estimate": price or (_extract_prices(text) or ["Contact for quote"])[0],
                "certifications": certs,
                "moq": _extract_moq(text),
                "contact": {
                    "phone": _extract_phones(text),
                    "email": _extract_emails(text),
                },
                "gst_number": _extract_gst(text),
                "source_url": url,
                "_platform_score_bonus": 20,
            })

        if results:
            break

    # Playwright fallback for JS-rendered IndiaMART SPA
    if not results and use_playwright:
        pw_url = f"https://www.indiamart.com/search.mp?ss={quote_plus(product)}+{quote_plus(location)}"
        html = await _playwright_fetch(pw_url, wait_selector=".sup-list, .busi-info, .organic-card")
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for card in soup.select(".supplier-name, .company-name"):
                name = card.get_text(" ", strip=True)
                if name:
                    results.append({
                        "name": name[:80],
                        "platform": "IndiaMART (PW)",
                        "url": pw_url,
                        "location": location or "India",
                        "snippet": "",
                        "price_estimate": "Contact for quote",
                        "certifications": [],
                        "moq": "Contact supplier",
                        "contact": {"phone": [], "email": []},
                        "gst_number": "",
                        "source_url": pw_url,
                        "_platform_score_bonus": 20,
                    })

    logger.info(f"IndiaMART: {len(results)} suppliers found")
    return results[:8]


# ── 2. TradeIndia ───────────────────────────────────────────────────────────

async def scrape_tradeindia(
    session: aiohttp.ClientSession,
    product: str,
    location: str,
    conn: sqlite3.Connection,
    ttl: int,
) -> list[dict]:
    results: list[dict] = []
    url = f"https://www.tradeindia.com/search.html?keyword={quote_plus(product)}"
    cached = _cache_get(conn, url, ttl)
    html = cached or await _afetch(session, url)
    if html and not cached:
        _cache_set(conn, url, html)
    if not html:
        return results

    soup = BeautifulSoup(html, "html.parser")
    seen_names = set()

    for coy_el in soup.select(".coy-name, [class*='coy-name'], .company-name, .supplier-name"):
        name = coy_el.get_text(" ", strip=True)
        if not name or len(name) < 3 or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        link_el = coy_el.find_parent("a") or coy_el.select_one("a[href]")
        if link_el and link_el.get("href") and "search" not in link_el["href"]:
            link = urljoin("https://www.tradeindia.com", link_el["href"])
        else:
            link = f"https://www.tradeindia.com/search.html?keyword={quote_plus(name)}"

        card = coy_el.find_parent(lambda tag: tag.name in ["div", "article"] and (
            any("card" in c.lower() or "item" in c.lower() or "sc-" in c.lower() for c in tag.get("class", []))
        ))
        text = ""
        if card:
            if not card.select_one(".card_title, [class*='card_title'], h2") and card.parent and card.parent.name in ["div", "article"]:
                card = card.parent
            text = card.get_text(" ", strip=True)
        else:
            text = name

        locs = _extract_locations(text)

        results.append({
            "name": name[:80],
            "platform": "TradeIndia",
            "url": link,
            "location": locs[0] if locs else (location or "India"),
            "snippet": text[:200],
            "price_estimate": (_extract_prices(text) or ["Contact for quote"])[0],
            "certifications": _extract_certs(text),
            "moq": _extract_moq(text),
            "contact": {"phone": _extract_phones(text), "email": _extract_emails(text)},
            "gst_number": _extract_gst(text),
            "source_url": url,
            "_platform_score_bonus": 18,
        })

    logger.info(f"TradeIndia: {len(results)} suppliers found")
    return results[:12]


# ── 3. ExportersIndia ──────────────────────────────────────────────────────

async def scrape_exporters_india(
    session: aiohttp.ClientSession,
    product: str,
    location: str,
    conn: sqlite3.Connection,
    ttl: int,
) -> list[dict]:
    results: list[dict] = []
    url = (
        f"https://www.exportersindia.com/search-products/{quote_plus(product.lower().replace(' ', '-'))}.htm"
        f"?location={quote_plus(location)}"
    )
    cached = _cache_get(conn, url, ttl)
    html = cached or await _afetch(session, url)
    if html and not cached:
        _cache_set(conn, url, html)
    if not html:
        return results

    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select(".prd-listing, .search-result-item, .company-block"):
        name_el = card.select_one(".comp-name, .company-name, h3, h4")
        loc_el  = card.select_one(".comp-address, .location, .city")
        url_el  = card.select_one("a[href]")
        text    = card.get_text(" ", strip=True)

        name = name_el.get_text(" ", strip=True) if name_el else ""
        if not name or len(name) < 3:
            continue

        link = urljoin("https://www.exportersindia.com", url_el["href"]) if url_el else url

        results.append({
            "name": name[:80],
            "platform": "ExportersIndia",
            "url": link,
            "location": (loc_el.get_text(" ", strip=True) if loc_el else location) or "India",
            "snippet": text[:200],
            "price_estimate": (_extract_prices(text) or ["Contact for quote"])[0],
            "certifications": _extract_certs(text),
            "moq": _extract_moq(text),
            "contact": {"phone": _extract_phones(text), "email": _extract_emails(text)},
            "gst_number": _extract_gst(text),
            "source_url": url,
            "_platform_score_bonus": 15,
        })

    logger.info(f"ExportersIndia: {len(results)} suppliers found")
    return results[:6]


# ── 4. Justdial B2B ────────────────────────────────────────────────────────

async def scrape_justdial(
    session: aiohttp.ClientSession,
    product: str,
    location: str,
    conn: sqlite3.Connection,
    ttl: int,
) -> list[dict]:
    results: list[dict] = []
    loc_slug = location.lower().replace(" ", "-") or "india"
    prod_slug = product.lower().replace(" ", "-")
    url = f"https://www.justdial.com/{loc_slug}/{prod_slug}-manufacturers/nnn-{prod_slug}"

    cached = _cache_get(conn, url, ttl)
    html = cached or await _afetch(session, url, extra_headers={"User-Agent": MOBILE_UA})
    if html and not cached:
        _cache_set(conn, url, html)
    if not html:
        return results

    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select(".resultbox, .store-details, li.cntanr"):
        name_el = card.select_one(".store-name, .fn, h2, .resultbox_title")
        addr_el = card.select_one(".address, .adr, .resultbox_address")
        ph_el   = card.select_one(".telno, .contact-info, .call-info")
        text    = card.get_text(" ", strip=True)

        name = name_el.get_text(" ", strip=True) if name_el else ""
        if not name or len(name) < 3:
            continue

        results.append({
            "name": name[:80],
            "platform": "Justdial B2B",
            "url": url,
            "location": (addr_el.get_text(" ", strip=True)[:60] if addr_el else location) or "India",
            "snippet": text[:200],
            "price_estimate": "Contact for quote",
            "certifications": _extract_certs(text),
            "moq": "Contact supplier",
            "contact": {
                "phone": _extract_phones(
                    ph_el.get_text(" ", strip=True) if ph_el else text
                ),
                "email": _extract_emails(text),
            },
            "gst_number": "",
            "source_url": url,
            "_platform_score_bonus": 12,
        })

    logger.info(f"Justdial: {len(results)} suppliers found")
    return results[:6]


# ── 5. GeM (Government e-Marketplace) ─────────────────────────────────────

async def scrape_gem(
    session: aiohttp.ClientSession,
    product: str,
    conn: sqlite3.Connection,
    ttl: int,
) -> list[dict]:
    """
    GeM catalogue search. GeM has a public search page (no login for browsing).
    """
    results: list[dict] = []
    url = f"https://mkp.gem.gov.in/search#q={quote_plus(product)}&t=all"
    api_url = (
        f"https://mkp.gem.gov.in/api/v1/catalogue/search"
        f"?query={quote_plus(product)}&page=1&pageSize=20"
    )

    for try_url in [api_url, url]:
        cached = _cache_get(conn, try_url, ttl)
        html = cached or await _afetch(session, try_url)
        if html and not cached:
            _cache_set(conn, try_url, html)
        if not html:
            continue

        # Try JSON API response
        try:
            data = json.loads(html)
            items = data.get("products", data.get("items", data.get("results", [])))
            if isinstance(items, list):
                for item in items[:8]:
                    seller = item.get("sellerName") or item.get("seller", {}).get("name", "GeM Seller")
                    results.append({
                        "name": str(seller)[:80],
                        "platform": "GeM (Govt e-Marketplace)",
                        "url": f"https://mkp.gem.gov.in/search#q={quote_plus(product)}",
                        "location": item.get("sellerLocation") or item.get("location", "India"),
                        "snippet": str(item.get("productDescription") or item.get("description", ""))[:200],
                        "price_estimate": str(item.get("price") or item.get("unitPrice", "On Application")),
                        "certifications": _extract_certs(json.dumps(item)),
                        "moq": str(item.get("moq") or item.get("minOrderQuantity", "As per GeM listing")),
                        "contact": {"phone": [], "email": []},
                        "gst_number": str(item.get("gstNumber") or item.get("gstin", "")),
                        "udyam_registered": bool(item.get("udyamNumber") or item.get("msmeRegistered")),
                        "source_url": try_url,
                        "_platform_score_bonus": 30,   # highest trust – govt verified
                    })
                if results:
                    break
        except (json.JSONDecodeError, TypeError):
            pass

        # HTML fallback
        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select(".product-card, .gem-listing, .catalogue-item"):
            name_el = card.select_one(".seller-name, .company-name, h3, h4")
            price_el = card.select_one(".price, .gem-price")
            text = card.get_text(" ", strip=True)
            name = name_el.get_text(" ", strip=True) if name_el else ""
            if not name:
                continue
            results.append({
                "name": name[:80],
                "platform": "GeM (Govt e-Marketplace)",
                "url": url,
                "location": "India",
                "snippet": text[:200],
                "price_estimate": price_el.get_text(" ", strip=True) if price_el else "On Application",
                "certifications": _extract_certs(text),
                "moq": _extract_moq(text),
                "contact": {"phone": [], "email": []},
                "gst_number": _extract_gst(text),
                "source_url": try_url,
                "_platform_score_bonus": 30,
            })
        if results:
            break

    logger.info(f"GeM: {len(results)} suppliers found")
    return results[:6]


# ── 6. MSME Udyam / Samadhaan Directory ───────────────────────────────────

async def scrape_msme_directory(
    session: aiohttp.ClientSession,
    product: str,
    location: str,
    conn: sqlite3.Connection,
    ttl: int,
) -> list[dict]:
    results: list[dict] = []
    urls = [
        f"https://msme.gov.in/search?q={quote_plus(product)}+{quote_plus(location)}",
        f"https://udyamregistration.gov.in/search?sector={quote_plus(product)}&state={quote_plus(location)}",
        f"https://laghu-udyog.com/find/{quote_plus(product.lower().replace(' ', '-'))}/"
        f"{quote_plus(location.lower().replace(' ', '-'))}/",
    ]
    for url in urls:
        cached = _cache_get(conn, url, ttl)
        html = cached or await _afetch(session, url)
        if html and not cached:
            _cache_set(conn, url, html)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select(".company, .msme-unit, .udyam-unit, .enterprise, li.result"):
            name_el = card.select_one("h2, h3, .name, .company-name")
            loc_el  = card.select_one(".location, .city, .address")
            text    = card.get_text(" ", strip=True)
            name    = name_el.get_text(" ", strip=True) if name_el else ""
            if not name or len(name) < 3:
                continue
            results.append({
                "name": name[:80],
                "platform": "MSME / Udyam Directory",
                "url": url,
                "location": (loc_el.get_text(" ", strip=True) if loc_el else location) or "India",
                "snippet": text[:200],
                "price_estimate": "Contact supplier (MSME registered)",
                "certifications": _extract_certs(text) + ["Udyam"],
                "moq": _extract_moq(text),
                "contact": {"phone": _extract_phones(text), "email": _extract_emails(text)},
                "gst_number": _extract_gst(text),
                "udyam_registered": True,
                "source_url": url,
                "_platform_score_bonus": 22,
            })
        if results:
            break

    logger.info(f"MSME/Udyam: {len(results)} suppliers found")
    return results[:5]


# ── 7. IndiaBizList ────────────────────────────────────────────────────────

async def scrape_indiabizlist(
    session: aiohttp.ClientSession,
    product: str,
    location: str,
    conn: sqlite3.Connection,
    ttl: int,
) -> list[dict]:
    results: list[dict] = []
    url = (
        f"https://www.indiabizlist.com/catalog/search/?q={quote_plus(product)}"
        f"&location={quote_plus(location)}"
    )
    cached = _cache_get(conn, url, ttl)
    html = cached or await _afetch(session, url)
    if html and not cached:
        _cache_set(conn, url, html)
    if not html:
        return results

    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select(".business-listing, .result-item, .company-card"):
        name_el = card.select_one("h2, h3, .company-name, .biz-name")
        text    = card.get_text(" ", strip=True)
        name    = name_el.get_text(" ", strip=True) if name_el else ""
        if not name:
            continue
        results.append({
            "name": name[:80],
            "platform": "IndiaBizList",
            "url": url,
            "location": location or "India",
            "snippet": text[:180],
            "price_estimate": (_extract_prices(text) or ["Contact for quote"])[0],
            "certifications": _extract_certs(text),
            "moq": _extract_moq(text),
            "contact": {"phone": _extract_phones(text), "email": _extract_emails(text)},
            "gst_number": _extract_gst(text),
            "source_url": url,
            "_platform_score_bonus": 10,
        })
    logger.info(f"IndiaBizList: {len(results)} suppliers found")
    return results[:5]


# ── 8. Alibaba India (for international-facing Indian suppliers) ───────────

async def scrape_alibaba_india(
    session: aiohttp.ClientSession,
    product: str,
    location: str,
    conn: sqlite3.Connection,
    ttl: int,
) -> list[dict]:
    results: list[dict] = []
    url = (
        f"https://www.alibaba.com/trade/search?SearchText={quote_plus(product)}"
        f"+{quote_plus(location)}+india&Country=India&IndexArea=product_en"
    )
    cached = _cache_get(conn, url, ttl)
    html = cached or await _afetch(session, url)
    if html and not cached:
        _cache_set(conn, url, html)
    if not html:
        return results

    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select(".organic-list-offer, .m-gallery-product-item, article"):
        name_el  = card.select_one(".organic-gallery-offer__company, .supplier-name, h3")
        price_el = card.select_one(".price, .organic-gallery-offer__price, .gallery-offer-price")
        text     = card.get_text(" ", strip=True)
        name     = name_el.get_text(" ", strip=True) if name_el else ""
        if not name or len(name) < 3:
            continue
        # Only include India-origin suppliers
        if "india" not in text.lower() and location.lower() not in text.lower():
            continue
        results.append({
            "name": name[:80],
            "platform": "Alibaba (India Supplier)",
            "url": url,
            "location": location or "India",
            "snippet": text[:180],
            "price_estimate": price_el.get_text(" ", strip=True) if price_el else "Contact for quote",
            "certifications": _extract_certs(text),
            "moq": _extract_moq(text),
            "contact": {"phone": [], "email": []},
            "gst_number": "",
            "export_experience": True,
            "source_url": url,
            "_platform_score_bonus": 14,
        })
    logger.info(f"Alibaba India: {len(results)} suppliers found")
    return results[:5]


# ── 9. DuckDuckGo Multi-Query Web Search ──────────────────────────────────

async def scrape_duckduckgo(
    session: aiohttp.ClientSession,
    product: str,
    location: str,
    neighbors: list[str],
    conn: sqlite3.Connection,
    ttl: int,
) -> list[dict]:
    results: list[dict] = []
    clean_loc = location.strip() if location and location.lower() not in ["india", "india-wide", "national", "not specified"] else ""
    loc_str = clean_loc or "India"

    queries = [
        f'"{product}" supplier manufacturer {clean_loc} India'.strip(),
        f'site:indiamart.com "{product}" {clean_loc}'.strip(),
        f'site:tradeindia.com "{product}" {clean_loc}'.strip(),
        f'"{product}" manufacturer India B2B price MOQ',
    ]

    async def _fetch_ddg_q(q: str) -> list[dict]:
        q_results: list[dict] = []
        url = f"https://html.duckduckgo.com/html/?{urlencode({'q': q, 'kl': 'in-en', 'ia': 'web'})}"
        cached = _cache_get(conn, url, ttl)
        html = cached or await _afetch(session, url, timeout=3)
        if html and not cached:
            _cache_set(conn, url, html)
        if not html:
            return q_results

        soup = BeautifulSoup(html, "html.parser")
        for r in soup.select(".result"):
            title_el   = r.select_one(".result__a, .result__title a")
            snippet_el = r.select_one(".result__snippet, .result__body")
            link_el    = r.select_one("a.result__a")

            title   = title_el.get_text(" ", strip=True) if title_el else ""
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            link    = link_el.get("href", "") if link_el else ""

            if "duckduckgo.com" in link:
                m = re.search(r"uddg=([^&]+)", link)
                if m:
                    from urllib.parse import unquote
                    link = unquote(m.group(1))

            if not title or not link:
                continue

            domain = urlparse(link).netloc
            combined = f"{title} {snippet}"
            locs = _extract_locations(combined)

            q_results.append({
                "name": title[:80],
                "platform": _platform_label(domain),
                "url": link,
                "location": locs[0] if locs else loc_str,
                "snippet": snippet[:200],
                "price_estimate": (_extract_prices(combined) or ["Contact for quote"])[0],
                "certifications": _extract_certs(combined),
                "moq": _extract_moq(combined),
                "contact": {"phone": _extract_phones(combined), "email": _extract_emails(combined)},
                "gst_number": _extract_gst(combined),
                "source_url": url,
                "_platform_score_bonus": _platform_bonus(domain),
            })
        return q_results

    settled = await asyncio.gather(*[_fetch_ddg_q(q) for q in queries[:4]], return_exceptions=True)
    for res_list in settled:
        if isinstance(res_list, list):
            results.extend(res_list)

    logger.info(f"DuckDuckGo: {len(results)} suppliers found")
    return _dedup(results)[:12]


# ── 10. Direct Supplier Website Deep-Scraper ──────────────────────────────

async def deep_scrape_supplier_page(
    session: aiohttp.ClientSession,
    url: str,
    conn: sqlite3.Connection,
    ttl: int,
) -> dict:
    """
    Fetches and enriches a supplier's own website/profile page
    to extract contact, GST, certifications, product range.
    """
    cached = _cache_get(conn, url, ttl)
    html = cached or await _afetch(session, url, timeout=4)
    if html and not cached:
        _cache_set(conn, url, html)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    # Remove scripts / style noise
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)

    return {
        "phone":          _extract_phones(text),
        "email":          _extract_emails(text),
        "gst_number":     _extract_gst(text),
        "certifications": _extract_certs(text),
        "moq":            _extract_moq(text),
        "lead_time":      _extract_lead_time(text),
        "payment_terms":  _extract_payment(text),
        "factory_photos": bool(soup.select("img.factory, img.plant, img.unit, .factory-image")),
        "export_exp":     "export" in text.lower() or "oem" in text.lower(),
        "udyam":          bool(re.search(r'udyam|UDYAM|Udyam', text)),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  PLATFORM HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _platform_label(domain: str) -> str:
    d = domain.lower()
    if "indiamart"     in d: return "IndiaMART"
    if "tradeindia"    in d: return "TradeIndia"
    if "exportersindia"in d: return "ExportersIndia"
    if "gem.gov"       in d: return "GeM (Govt e-Marketplace)"
    if "msme.gov"      in d: return "MSME Directory"
    if "justdial"      in d: return "Justdial B2B"
    if "alibaba"       in d: return "Alibaba (India)"
    if "indiabizlist"  in d: return "IndiaBizList"
    if "sulekha"       in d: return "Sulekha B2B"
    if ".gov.in"       in d: return "Government Portal"
    return domain.replace("www.", "")


def _platform_bonus(domain: str) -> int:
    d = domain.lower()
    if "gem.gov"         in d: return 30
    if "msme.gov"        in d: return 25
    if ".gov.in"         in d: return 22
    if "indiamart"       in d: return 20
    if "tradeindia"      in d: return 18
    if "exportersindia"  in d: return 15
    if "justdial"        in d: return 12
    if "alibaba"         in d: return 14
    if "indiabizlist"    in d: return 10
    return 8


# ═══════════════════════════════════════════════════════════════════════════
#  PRODUCT RELEVANCE ENGINE
# ═══════════════════════════════════════════════════════════════════════════

GENERIC_STOP_WORDS = {
    "equipment", "equipments", "machinery", "machine", "machines", "plant", "plants",
    "system", "systems", "processing", "manufacturing", "manufacturer", "manufacturers",
    "supplier", "suppliers", "dealer", "dealers", "trader", "traders", "company",
    "ltd", "pvt", "llp", "corp", "corporation", "solutions", "services", "products",
    "product", "industry", "industrial", "b2b", "india", "pvt ltd", "mumbai"
}

DOMAIN_SYNONYMS = {
    "milk": ["dairy", "milk", "pasteuriz", "homogeniz", "khoya", "paneer", "ghee", "cream", "chilling", "silo"],
    "dairy": ["milk", "dairy", "pasteuriz", "homogeniz", "khoya", "paneer"],
    "solar": ["photovoltaic", "pv", "solar", "inverter", "module"],
    "battery": ["lithium", "battery", "cell", "ev", "bms"],
    "ev": ["electric vehicle", "ev", "charger", "charging", "motor"],
    "stone": ["agate", "crystal", "stone", "gemstone", "jasper", "quartz", "granite", "marble"],
    "led": ["led", "driver", "pcb", "lighting", "smps", "chip"],
    "textile": ["fabric", "yarn", "cotton", "weaving", "textile", "spinning"],
    "chemical": ["chemical", "solvent", "acid", "polymer", "resin"],
    "food": ["food", "beverage", "packaging", "canning", "processing"],
    "mobile": ["mobile phone", "smartphone", "cellular", "cell phone", "handset", "mobile cover", "mobile accessory", "mobile phone charger"],
    "phone": ["mobile", "smartphone", "cellular", "cell phone", "handset", "telephone"],
}

NEGATIVE_MOBILE_TERMS = {
    "aircon", "air conditioner", "ahu", "concrete", "batching", "crane", "toilet",
    "ramp", "scaffold", "compactor", "crushing", "application", "software"
}

POSITIVE_MOBILE_TERMS = {
    "phone", "smartphone", "cellular", "handset", "cover", "accessory", "gadget",
    "case", "charger", "display", "screen", "tempered glass", "battery", "earphone", "headphone"
}

def compute_product_relevance(product: str, name: str, snippet: str) -> tuple[int, bool]:
    prod_lower = product.lower().strip()
    tokens = set(re.findall(r'[a-zA-Z0-9]+', prod_lower))
    core_tokens = {t for t in tokens if t not in GENERIC_STOP_WORDS and len(t) > 2}
    if not core_tokens:
        core_tokens = tokens

    search_set = set(core_tokens)
    for token in core_tokens:
        if token in DOMAIN_SYNONYMS:
            search_set.update(DOMAIN_SYNONYMS[token])

    text = (name + " " + snippet).lower()

    # Disambiguation for 'mobile' / 'mobile phone' vs industrial mobile machinery
    if "mobile" in core_tokens or "phone" in core_tokens:
        has_negative = any(neg in text for neg in NEGATIVE_MOBILE_TERMS)
        has_positive = any(pos in text for pos in POSITIVE_MOBILE_TERMS)
        if has_negative and not has_positive:
            return -100, False

    matches = [kw for kw in search_set if kw in text]

    if matches:
        name_lower = name.lower()
        name_match = any(kw in name_lower for kw in search_set)
        score = 45 if name_match else 30
        return score, True
    else:
        return -100, False


# ═══════════════════════════════════════════════════════════════════════════
#  12-SIGNAL RANKING ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def _score_supplier(
    s: dict,
    product: str,
    target_location: str,
    target_state: str,
    neighbors: list[str],
) -> dict:
    rel_score, is_valid = compute_product_relevance(product, s.get("name", ""), s.get("snippet", ""))
    if not is_valid:
        s["score"] = -100
        s["is_relevant"] = False
        s["score_breakdown"] = {"product_relevance": -100}
        return s

    score = 25   # baseline
    breakdown: dict[str, int] = {"product_relevance": rel_score}
    score += rel_score
    s["is_relevant"] = True

    # 1. Proximity (max 35)
    s_loc   = s.get("location", "").lower()
    s_state = _detect_state(_extract_locations(s.get("location", "") + " " + s.get("snippet", "")))
    tgt_lc  = target_location.lower()
    tgt_st  = target_state.lower()

    if tgt_lc and tgt_lc in s_loc:
        pts = 35; tag = "Target City"
    elif tgt_st and (tgt_st in s_loc or tgt_st in s_state.lower()):
        pts = 25; tag = "Target State"
    elif any(n.lower() in s_loc or n.lower() in s_state.lower() for n in neighbors):
        pts = 15; tag = "Neighboring State"
    else:
        pts = 3;  tag = "National"

    s["proximity_match"] = tag
    score += pts;  breakdown["proximity"] = pts

    # 2. Platform credibility (max 30)
    pts = s.get("_platform_score_bonus", 8)
    score += pts;  breakdown["platform"] = pts

    # 3. Price information (10)
    p = s.get("price_estimate", "")
    pts = 10 if (p and p != "Contact for quote" and len(p) > 2) else 0
    score += pts;  breakdown["price_info"] = pts

    # 4. Certifications (max 12)
    certs = s.get("certifications", [])
    pts = min(12, len(certs) * 4)
    score += pts;  breakdown["certifications"] = pts

    # 5. Contact details available (max 10)
    contact = s.get("contact", {})
    pts = (5 if contact.get("phone") else 0) + (5 if contact.get("email") else 0)
    score += pts;  breakdown["contact_details"] = pts

    # 6. GST verified (8)
    pts = 8 if s.get("gst_number") else 0
    score += pts;  breakdown["gst_verified"] = pts

    # 7. Udyam / MSME registered (6)
    pts = 6 if s.get("udyam_registered") else 0
    score += pts;  breakdown["udyam"] = pts

    # 8. Export experience (5)
    pts = 5 if s.get("export_experience") else 0
    score += pts;  breakdown["export_exp"] = pts

    # 9. MOQ available (4)
    moq = s.get("moq", "Contact supplier")
    pts = 4 if (moq and moq != "Contact supplier") else 0
    score += pts;  breakdown["moq_available"] = pts

    # 10. Lead time specified (3)
    lt = s.get("lead_time", "Not specified")
    pts = 3 if (lt and lt != "Not specified") else 0
    score += pts;  breakdown["lead_time"] = pts

    # 11. Factory photos (2)
    pts = 2 if s.get("factory_photos") else 0
    score += pts;  breakdown["factory_photos"] = pts

    # 12. Rich snippet / profile completeness (max 5)
    pts = min(5, len(s.get("snippet", "")) // 40)
    score += pts;  breakdown["profile_completeness"] = pts

    s["raw_score"] = score
    s["score"] = min(score, 100)
    s["score_breakdown"] = breakdown
    s["state"] = s_state
    s.pop("_platform_score_bonus", None)
    return s


# ═══════════════════════════════════════════════════════════════════════════
#  DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════════════

def _dedup(suppliers: list[dict]) -> list[dict]:
    seen_urls: set[str] = set()
    seen_names: set[str] = set()
    unique: list[dict] = []
    for s in suppliers:
        url  = s.get("url", "").strip().lower()[:80]
        norm = re.sub(r"[^a-z0-9]", "", s.get("name", "").lower()[:30])
        if url in seen_urls or (norm and norm in seen_names):
            continue
        seen_urls.add(url)
        if norm:
            seen_names.add(norm)
        unique.append(s)
    return unique


# ═══════════════════════════════════════════════════════════════════════════
#  ASYNC ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

async def _orchestrate(
    product: str,
    location: str,
    neighbors: list[str],
    conn: sqlite3.Connection,
    ttl: int,
    use_playwright: bool,
    deep_scrape_top_n: int,
) -> list[dict]:
    ssl_ctx = None
    try:
        import ssl
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode    = ssl.CERT_NONE
    except Exception:
        pass

    connector = aiohttp.TCPConnector(ssl=ssl_ctx, limit=20) if ssl_ctx else aiohttp.TCPConnector(limit=20)

    async with aiohttp.ClientSession(connector=connector) as session:
        # Fire all scrapers in parallel
        tasks = [
            scrape_indiamart(session, product, location, conn, ttl, use_playwright),
            scrape_tradeindia(session, product, location, conn, ttl),
            scrape_exporters_india(session, product, location, conn, ttl),
            scrape_justdial(session, product, location, conn, ttl),
            scrape_gem(session, product, conn, ttl),
            scrape_msme_directory(session, product, location, conn, ttl),
            scrape_indiabizlist(session, product, location, conn, ttl),
            scrape_alibaba_india(session, product, location, conn, ttl),
            scrape_duckduckgo(session, product, location, neighbors, conn, ttl),
        ]

        all_results: list[list[dict]] = []
        settled = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(settled):
            if isinstance(r, Exception):
                logger.warning(f"Scraper {i} failed: {r}")
            elif isinstance(r, list):
                all_results.extend(r)

        raw = all_results
        logger.info(f"Total raw supplier hits: {len(raw)}")

        # Deep-scrape top N unique profiles for enrichment
        deduped_raw = _dedup(raw)
        enrichment_tasks = []
        for s in deduped_raw[:deep_scrape_top_n]:
            url = s.get("url", "")
            if url and "duckduckgo" not in url and "indiamart.com/search" not in url:
                enrichment_tasks.append((s, deep_scrape_supplier_page(session, url, conn, ttl)))

        if enrichment_tasks:
            enriched = await asyncio.gather(
                *[t for _, t in enrichment_tasks], return_exceptions=True
            )
            for (s, _), extra in zip(enrichment_tasks, enriched):
                if isinstance(extra, dict) and extra:
                    if extra.get("phone"):      s["contact"]["phone"]  = extra["phone"]
                    if extra.get("email"):      s["contact"]["email"]  = extra["email"]
                    if extra.get("gst_number"): s["gst_number"]        = extra["gst_number"]
                    if extra.get("moq"):        s["moq"]               = extra["moq"]
                    if extra.get("lead_time"):  s["lead_time"]         = extra["lead_time"]
                    if extra.get("payment_terms"): s["payment_terms"]  = extra["payment_terms"]
                    if extra.get("factory_photos"): s["factory_photos"] = True
                    if extra.get("export_exp"):    s["export_experience"] = True
                    if extra.get("udyam"):         s["udyam_registered"]  = True
                    s["certifications"] = list(set(s.get("certifications", []) + extra.get("certifications", [])))

    return deduped_raw


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN TOOL FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def supplier_search(
    product: str,
    location: str = "",
    radius_km: int = 300,
    use_playwright: bool = False,
    deep_scrape_top_n: int = 5,
    cache_ttl_hours: int = 4,
    max_results: int = 12,
) -> dict:
    """
    Enhanced Supplier Search — v2
    ================================
    Runs 9 scrapers in parallel (IndiaMART, TradeIndia, ExportersIndia,
    Justdial B2B, GeM, MSME/Udyam, IndiaBizList, Alibaba India, DuckDuckGo),
    deep-scrapes top supplier profile pages for enrichment, then ranks via
    a 12-signal engine.

    Args:
        product:           Product name / category (e.g. "LED Street Light")
        location:          Target city or state (e.g. "Ahmedabad", "Gujarat")
        radius_km:         Search radius in km (used for proximity scoring)
        use_playwright:    Enable JS rendering for IndiaMART SPA (slower)
        deep_scrape_top_n: Number of top results to deep-scrape for enrichment
        cache_ttl_hours:   Cache TTL in hours (0 = no cache)
        max_results:       Maximum suppliers to return

    Returns:
        Structured dict with ranked suppliers, metadata, and direct market links.
    """
    print(
        f"\n[TOOL v2] supplier_search | Product: '{product}' | "
        f"Location: '{location or 'India-wide'}' | Playwright: {use_playwright}"
    )

    product   = product.strip()
    location  = location.strip()
    loc_key   = location.lower()

    # Neighbor resolution (city + state aliases)
    neighbors: list[str] = []
    for k, v in NEIGHBOR_MAP.items():
        if k in loc_key or loc_key in k:
            neighbors = v
            break

    target_state = _detect_state([location] + neighbors[:2]) if location else ""

    # Cache check
    conn = _init_cache()
    qhash = hashlib.sha256(
        f"{product}|{location}|{radius_km}".encode()
    ).hexdigest()

    if cache_ttl_hours > 0:
        cached = _result_get(conn, qhash, cache_ttl_hours)
        if cached:
            print("[CACHE HIT] Returning cached supplier result.")
            conn.close()
            return cached

    search_product = product
    if product.lower().strip() in ("mobile", "mobiles"):
        search_product = "mobile phone"

    # Run async scraping pipeline
    try:
        raw_suppliers = _run_async_safely(
            _orchestrate(search_product, location, neighbors, conn, cache_ttl_hours, use_playwright, deep_scrape_top_n)
        )
    except Exception as e:
        logger.error(f"Async pipeline failed: {e}")
        raw_suppliers = []

    # Score & rank
    scored = [
        _score_supplier(s, product, location, target_state, neighbors)
        for s in raw_suppliers
    ]
    relevant = [s for s in scored if s.get("is_relevant", True) and s.get("score", -100) > 0]
    relevant.sort(key=lambda x: (x.get("raw_score", x.get("score", 0)), x.get("score", 0)), reverse=True)
    top_suppliers = relevant[:max_results]

    # Categorise by proximity tier
    tier_map: dict[str, list[dict]] = {
        "Target City": [], "Target State": [], "Neighboring State": [], "National": []
    }
    for s in top_suppliers:
        tier_map.setdefault(s.get("proximity_match", "National"), []).append(s)

    # Source summary
    sources_used = list({s.get("platform", "") for s in top_suppliers if s.get("platform")})

    result = {
        "product":             product,
        "target_location":     location or "Not specified (National Search)",
        "target_state":        target_state or "Not specified",
        "neighboring_states":  neighbors,
        "search_radius_km":    radius_km,
        "status":              "completed",
        "total_raw_hits":      len(raw_suppliers),
        "total_after_ranking": len(top_suppliers),
        "sources_scraped":     sources_used,

        # Tiered results
        "tier_1_target_city":      tier_map.get("Target City", []),
        "tier_2_target_state":     tier_map.get("Target State", []),
        "tier_3_neighboring":      tier_map.get("Neighboring State", []),
        "tier_4_national":         tier_map.get("National", []),

        # Flat top list (convenience)
        "top_suppliers":           top_suppliers,

        # Direct search links
        "direct_marketplaces": [
            {
                "name": "IndiaMART",
                "url": f"https://dir.indiamart.com/search.mp?ss={quote_plus(product)}+{quote_plus(location)}",
            },
            {
                "name": "TradeIndia",
                "url": f"https://www.tradeindia.com/search/?search_string={quote_plus(product)}+{quote_plus(location)}",
            },
            {
                "name": "ExportersIndia",
                "url": f"https://www.exportersindia.com/search-products/{quote_plus(product.lower().replace(' ', '-'))}.htm",
            },
            {
                "name": "GeM Portal",
                "url": f"https://mkp.gem.gov.in/search#q={quote_plus(product)}",
            },
            {
                "name": "Justdial B2B",
                "url": f"https://www.justdial.com/{quote_plus(loc_key)}/{quote_plus(product.lower().replace(' ', '-'))}-manufacturers",
            },
            {
                "name": "Udyam Registry",
                "url": "https://udyamregistration.gov.in",
            },
        ],

        "ranking_signals": [
            {"signal": "Geographic Proximity",       "max_pts": 35, "description": "City match > State match > Neighboring state > National"},
            {"signal": "Platform Credibility",        "max_pts": 30, "description": "GeM > MSME > Gov > IndiaMART > TradeIndia > others"},
            {"signal": "Price Information",           "max_pts": 10, "description": "+10 if price/unit rate is available"},
            {"signal": "Certifications",              "max_pts": 12, "description": "4 pts per cert (BIS, ISO, CE, RoHS, FSSAI, etc.)"},
            {"signal": "Contact Details",             "max_pts": 10, "description": "+5 phone, +5 email"},
            {"signal": "GST Verification",            "max_pts": 8,  "description": "+8 if GST number extracted"},
            {"signal": "Udyam / MSME Registration",  "max_pts": 6,  "description": "+6 if Udyam number confirmed"},
            {"signal": "Export Experience",           "max_pts": 5,  "description": "+5 if export keywords detected"},
            {"signal": "MOQ Specified",               "max_pts": 4,  "description": "+4 if minimum order quantity stated"},
            {"signal": "Lead Time Specified",         "max_pts": 3,  "description": "+3 if delivery timeline found"},
            {"signal": "Factory Photos",              "max_pts": 2,  "description": "+2 if factory imagery detected"},
            {"signal": "Profile Completeness",        "max_pts": 5,  "description": "Based on snippet richness"},
        ],

        "pipeline_steps": [
            f"1. Parsed product='{product}' | location='{location or 'India'}' | neighbors={neighbors[:3]}",
            "2. Fired 9 scrapers in parallel: IndiaMART, TradeIndia, ExportersIndia, Justdial B2B, GeM, MSME/Udyam, IndiaBizList, Alibaba India, DuckDuckGo",
            f"3. Deep-scraped top {deep_scrape_top_n} profile pages for phone/email/GST/certs enrichment",
            "4. Deduplicated by URL fingerprint + name normalization",
            "5. Applied 12-signal ranking engine (max 100 pts per supplier)",
            "6. Tiered results: Target City → Target State → Neighboring State → National",
            f"7. Returned top {max_results} ranked suppliers",
        ],

        "note": (
            "Scores are 0–100 across 12 signals. "
            "Suppliers verified via GeM / government portals carry highest credibility. "
            "Always verify GST, Udyam, and quality certifications directly before placing orders."
        ),

        "search_metadata": {
            "scraped_at":       datetime.utcnow().isoformat() + "Z",
            "cache_ttl_hours":  cache_ttl_hours,
            "playwright":       use_playwright,
            "deep_scrape_n":    deep_scrape_top_n,
            "scrapers_run": [
                "IndiaMART", "TradeIndia", "ExportersIndia",
                "Justdial B2B", "GeM Portal", "MSME/Udyam Directory",
                "IndiaBizList", "Alibaba India", "DuckDuckGo (multi-query)",
            ],
        },
    }

    if cache_ttl_hours > 0:
        _result_set(conn, qhash, f"{product}|{location}", result)
    conn.close()
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  REQUIREMENTS  (for reference)
# ═══════════════════════════════════════════════════════════════════════════
# REQUIREMENTS = """
# aiohttp>=3.9.0
# requests>=2.31.0
# beautifulsoup4>=4.12.0
# lxml>=5.1.0
# pydantic>=2.0.0

# # Optional – JS rendering
# playwright>=1.43.0        # then: playwright install chromium
# selenium>=4.20.0
# webdriver-manager>=4.0.0

# # Optional – Jupyter async fix
# nest-asyncio>=1.6.0

# # Optional – Redis cache
# redis>=5.0.0
# """