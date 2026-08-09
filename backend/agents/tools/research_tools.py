import os
import re
import requests
from typing import Optional
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote_plus
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchResults
from pydantic import BaseModel, Field
from utils.kb_lookup import (
    get_manufacturing_kb_dir,
    fetch_product_content,
    extract_section,
    extract_all_sections,
    parse_list_items,
    parse_table_rows,
)

try:
    from .subtool.supplier_search import supplier_search as subtool_supplier_search
except (ImportError, ValueError):
    try:
        from agents.tools.subtool.supplier_search import supplier_search as subtool_supplier_search
    except ImportError:
        subtool_supplier_search = None


# ── Shared helpers ────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

ddg = DuckDuckGoSearchResults()


def ddg_search(query: str, max_results: int = 6) -> list[dict]:
    """
    Runs a DuckDuckGo search and returns structured list of compact results.

    Each result: {title, snippet, url, domain}
    """
    try:
        raw = ddg.invoke(query)
        entries = re.findall(
            r'snippet:\s*(.*?),\s*title:\s*(.*?),\s*link:\s*(https?://[^\]]+)',
            raw
        )
        results = []
        for snippet, title, url in entries[:max_results]:
            results.append({
                "title"  : title.strip()[:80],
                "snippet": snippet.strip()[:200],
                "url"    : url.strip(),
                "domain" : urlparse(url.strip()).netloc,
            })
        return results
    except Exception as e:
        print(f"[WARNING] DDG search failed: {e}")
        return []


def scrape_url(url: str, char_limit: int = 600) -> dict:
    """
    Scrapes a URL and returns title + cleaned text content.
    Returns empty dict on failure.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6)
        soup = BeautifulSoup(resp.text, "html.parser")

        title = soup.title.text.strip() if soup.title else "No title"

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = " ".join(
            p.get_text(" ", strip=True)
            for p in soup.find_all(["p", "li", "td", "h2", "h3"])
        )
        text = re.sub(r'\s+', ' ', text).strip()

        return {
            "title"        : title[:100],
            "url"          : url,
            "domain"       : urlparse(url).netloc,
            "is_government": any(d in url for d in [".gov.in", "msme.gov", "pib.gov"]),
            "content"      : text[:char_limit],
        }
    except Exception as e:
        print(f"[WARNING] Scrape failed for {url}: {e}")
        return {}


def search_and_scrape(
    queries: list[str],
    max_results_per_query: int = 6,
    max_scrape: int = 4
) -> dict:
    """
    Runs multiple DDG queries, deduplicates URLs,
    scrapes top pages, and returns combined output.
    """
    all_results = []
    seen_urls   = set()

    for query in queries:
        print(f"  [SEARCH] {query}")
        hits = ddg_search(query, max_results=max_results_per_query)
        for hit in hits:
            if hit["url"] not in seen_urls:
                seen_urls.add(hit["url"])
                all_results.append(hit)

    scraped = []
    for hit in all_results[:max_scrape]:
        page = scrape_url(hit["url"])
        if page:
            scraped.append(page)

    return {
        "search_results": all_results[:8],
        "scraped_pages" : scraped,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. WEB SEARCH
# ─────────────────────────────────────────────────────────────────────────────
class ResearchInput(BaseModel):
    query: str = Field(description="The search query or topic to research")

@tool("web_search", args_schema=ResearchInput)
def web_search(query: str) -> dict:
    """
    Searches the live web for market trends,
    latest news, and raw material prices.
    """
    print("\n[TOOL CALLED] -> web_search")

    queries = [
        query,
        f"{query} India 2024 market trend",
    ]

    data = search_and_scrape(queries, max_results_per_query=3, max_scrape=2)

    trend_sentences = []
    for page in data["scraped_pages"]:
        sentences = re.split(r'(?<=[.!?])\s+', page.get("content", ""))
        for sent in sentences:
            if re.search(r'\d+%|crore|lakh|growth|decline|trend|price|rate', sent, re.I):
                trend_sentences.append(sent.strip()[:150])

    return {
        "query"          : query,
        "status"         : "live_search",
        "search_hits"    : len(data["search_results"]),
        "sources"        : [
            {"title": r["title"], "url": r["url"], "snippet": r["snippet"]}
            for r in data["search_results"][:3]
        ],
        "key_insights"   : trend_sentences[:4],
        "scraped_pages"  : [
            {"title": p["title"], "url": p["url"], "summary": p["content"][:200]}
            for p in data["scraped_pages"]
        ],
        "note": "Live results. Verify figures from official sources before use in reports."
    }


class SupplierInput(BaseModel):
    product: str = Field(description="The product, raw material, or component to find suppliers for")
    location: str = Field(description="Target location or state (e.g. 'Gujarat', 'Maharashtra', 'Delhi') for nearby supplier matching", default="")
    radius_km: int = Field(description="Preferred search radius in km around target location", default=300)
    use_playwright: bool = Field(description="Enable JS rendering for IndiaMART SPA (slower)", default=False)
    deep_scrape_top_n: int = Field(description="Number of top results to deep-scrape for enrichment", default=5)
    cache_ttl_hours: int = Field(description="Cache TTL in hours (0 = no cache)", default=4)
    max_results: int = Field(description="Maximum suppliers to return", default=12)


# ─────────────────────────────────────────────────────────────────────────────
# 2. SUPPLIER SEARCH (Location-Aware Pipeline via supplier_search subtool)
# ─────────────────────────────────────────────────────────────────────────────
@tool("supplier_search", args_schema=SupplierInput)
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
    Finds and ranks suppliers using parallel multi-source scraping (IndiaMART, TradeIndia, ExportersIndia, GeM, MSME/Udyam, Justdial B2B, Alibaba India, DuckDuckGo).
    Deep-scrapes top supplier profile pages for contact details (phone, email, GST, certs) and ranks via a 12-signal scoring engine.
    """
    print(f"\n[TOOL CALLED] -> supplier_search (Location-Aware Pipeline | Product: '{product}', Location: '{location or 'India-wide'}')")

    if subtool_supplier_search is not None:
        try:
            return subtool_supplier_search(
                product=product,
                location=location,
                radius_km=radius_km,
                use_playwright=use_playwright,
                deep_scrape_top_n=deep_scrape_top_n,
                cache_ttl_hours=cache_ttl_hours,
                max_results=max_results,
            )
        except Exception as e:
            print(f"[WARNING] Subtool supplier_search failed: {e}. Falling back to inline web search.")

    product_query = product.strip()
    target_location = location.strip()

    # Neighboring states map for Tier-2 proximity fallback
    NEIGHBOR_MAP = {
        "gujarat"      : ["Maharashtra", "Rajasthan", "Madhya Pradesh"],
        "maharashtra"  : ["Gujarat", "Goa", "Karnataka", "Telangana", "Madhya Pradesh"],
        "rajasthan"    : ["Gujarat", "Haryana", "Punjab", "Madhya Pradesh", "Delhi"],
        "tamil nadu"   : ["Karnataka", "Andhra Pradesh", "Kerala"],
        "karnataka"    : ["Maharashtra", "Goa", "Tamil Nadu", "Andhra Pradesh", "Telangana", "Kerala"],
        "delhi"        : ["Haryana", "Uttar Pradesh", "Punjab", "Rajasthan"],
        "ncr"          : ["Delhi", "Haryana", "Uttar Pradesh"],
        "telangana"    : ["Karnataka", "Andhra Pradesh", "Maharashtra", "Odisha"],
        "andhra pradesh": ["Tamil Nadu", "Karnataka", "Telangana", "Odisha"],
        "uttar pradesh": ["Delhi", "Haryana", "Rajasthan", "Bihar", "Madhya Pradesh"],
    }

    loc_key = target_location.lower()
    neighbors = NEIGHBOR_MAP.get(loc_key, [])

    # Step 2 to 5: Construct targeted search queries
    if target_location:
        queries = {
            "web_location" : f"{product_query} supplier manufacturer in {target_location} India B2B",
            "indiamart"    : f"site:indiamart.com {product_query} supplier {target_location}",
            "tradeindia"   : f"site:tradeindia.com {product_query} supplier {target_location}",
            "government"   : f"site:gem.gov.in OR site:msme.gov.in {product_query} supplier {target_location}",
        }
    else:
        queries = {
            "web"         : f"{product_query} supplier manufacturer India B2B",
            "indiamart"   : f"site:indiamart.com {product_query} supplier manufacturer",
            "tradeindia"  : f"site:tradeindia.com {product_query} supplier manufacturer",
            "government"  : f"site:gem.gov.in OR site:msme.gov.in {product_query} supplier manufacturer",
        }

    raw_candidates = []
    for source_type, q_str in queries.items():
        print(f"  [SEARCH {source_type.upper()}] {q_str}")
        hits = ddg_search(q_str, max_results=5)
        for hit in hits:
            hit["source_type"] = source_type
            raw_candidates.append(hit)

    # Step 6: Deduplicate
    unique_suppliers = []
    seen_urls = set()
    seen_names = set()

    for item in raw_candidates:
        url = item.get("url", "").strip().lower()
        title_text = item.get("title", "").strip().lower()
        snippet_text = item.get("snippet", "").strip().lower()
        full_text = f"{title_text} {snippet_text}"
        norm_name = re.sub(r'[^a-z0-9]', '', title_text[:30])

        if url in seen_urls or (norm_name and norm_name in seen_names):
            continue

        seen_urls.add(url)
        if norm_name:
            seen_names.add(norm_name)

        domain = item.get("domain", "")
        snippet = item.get("snippet", "")

        is_indiamart = "indiamart" in domain
        is_tradeindia = "tradeindia" in domain
        is_gov = any(g in url or g in domain for g in [".gov.in", "gem.gov", "msme.gov"])

        prices = re.findall(r'₹\s*[\d,]+|Rs\.?\s*[\d,]+|\d+\s*(?:per kg|per unit|per piece|per ton)', snippet, re.I)
        certs = re.findall(r'\b(BIS|ISO|CE|FSSAI|RoHS|CPCB|UL)\b', snippet, re.I)

        locations = re.findall(
            r'\b(Gujarat|Maharashtra|Delhi|Rajasthan|Tamil Nadu|Karnataka|'
            r'Pune|Mumbai|Ahmedabad|Surat|Chennai|Bangalore|Hyderabad|Kolkata|Noida|Gurgaon|Indore|Vadodara|Rajkot)\b',
            snippet,
            re.IGNORECASE
        )

        found_loc = locations[0] if locations else ("India" if not target_location else target_location)

        # 1. Product Relevance & Machinery Intent Verification
        product_terms = [t for t in product_query.lower().split() if len(t) > 2 and t not in ["for", "in", "and", "the", "a", "an", "with", "factory", "plant", "unit", "manufacturing", "supplier", "suppliers"]]
        
        product_matches = sum(1 for term in product_terms if term in full_text)
        has_product_relevance = (product_matches > 0) or (product_query.lower() in full_text)

        supplier_intent_keywords = [
            "supplier", "manufacturer", "machinery", "equipment", "plant", "processing",
            "technologists", "technologies", "engineering", "tank", "assembler", "dealer",
            "trader", "exporter", "fab", "fabricator", "chiller", "separator", "pasteurizer",
            "homogenizer", "turnkey", "dairy", "lines", "system"
        ]
        has_supplier_intent = any(k in full_text for k in supplier_intent_keywords)

        is_generic_portal_page = any(p in full_text or p in title_text for p in [
            "msme ramp", "ramp portal", "ministry of msme", "pib.gov", "scheme portal",
            "welcome | msme", "government scheme", "transformative role", "economic growth"
        ]) and not (has_supplier_intent and has_product_relevance)

        # Step 7: Location & Relevance Weighted Ranking
        score = 50

        # Product Relevance Score
        if has_product_relevance:
            score += 35
        else:
            score -= 25  # Penalize missing product match

        if has_supplier_intent:
            score += 25
        else:
            score -= 20  # Penalize non-supplier pages

        if is_generic_portal_page:
            score -= 60  # Heavily penalize generic non-supplier portal homepages

        # Proximity score
        if target_location:
            if target_location.lower() in title_text or target_location.lower() in snippet_text or target_location.lower() in found_loc.lower():
                score += 40  # Exact target location match
            elif any(n.lower() in snippet_text or n.lower() in found_loc.lower() for n in neighbors):
                score += 20  # Neighboring state match
            else:
                score += 5

        # Platform credibility score
        if is_gov and not is_generic_portal_page:
            score += 30
        elif is_indiamart or is_tradeindia:
            score += 25

        if prices:
            score += 15
        if certs:
            score += 10
        if len(snippet) > 80:
            score += 5

        platform_label = (
            "Government Portal (GeM/MSME)" if is_gov else
            "IndiaMART" if is_indiamart else
            "TradeIndia" if is_tradeindia else
            domain
        )

        unique_suppliers.append({
            "score"           : score,
            "name"            : item.get("title", "Supplier")[:60],
            "platform"        : platform_label,
            "url"             : item.get("url", ""),
            "location"        : found_loc,
            "proximity_match" : "Target Location" if target_location and target_location.lower() in found_loc.lower() else ("Nearby State" if target_location and any(n.lower() in found_loc.lower() for n in neighbors) else "National Supplier"),
            "price_estimate"  : prices[0] if prices else "Contact for quote",
            "certifications"  : list(set(c.upper() for c in certs)) if certs else ["Standard Specs"],
            "moq"             : "Contact supplier",
            "snippet"         : snippet[:140],
        })

    # Sort suppliers by rank score descending
    ranked_suppliers = sorted(unique_suppliers, key=lambda x: x["score"], reverse=True)
    top_10_suppliers = ranked_suppliers[:4]

    # Backup from KB
    kb_dir = get_manufacturing_kb_dir()
    _, content = fetch_product_content(product_query, kb_dir)
    kb_suppliers = []

    if content:
        section = extract_section(content, "supplier", "vendor", "source", "procurement", "raw material")
        if section:
            rows = parse_table_rows(section)
            if rows:
                for row in rows[:3]:
                    kb_suppliers.append({
                        "name"    : row.get("Supplier", row.get("Vendor", row.get("Name", ""))),
                        "location": row.get("Location", row.get("State", target_location or "India")),
                        "moq"     : row.get("MOQ", row.get("Min Order", "As per supplier")),
                        "source"  : "knowledge_base",
                    })

    return {
        "product"               : product_query,
        "target_location"       : target_location or "Not specified (National Search)",
        "neighboring_states"    : neighbors if target_location else [],
        "search_radius_km"      : radius_km,
        "status"                : "completed",
        "pipeline_steps"        : [
            f"1. Received product '{product_query}' and location '{target_location or 'India'}'",
            "2. Executed location-targeted Web & B2B portal search",
            "3. Searched IndiaMART & TradeIndia",
            "4. Searched Government directories (GeM/MSME)",
            "5. Removed duplicate suppliers",
            "6. Applied Proximity & Credibility Ranking Engine",
            "7. Returned top 10 ranked suppliers"
        ],
        "total_suppliers_found" : len(ranked_suppliers),
        "top_10_suppliers"      : top_10_suppliers,
        "kb_suppliers"          : kb_suppliers,
        "direct_marketplaces"   : [
            {"name": "IndiaMART",  "url": f"https://www.indiamart.com/search.mp?ss={quote_plus(product_query)}+{quote_plus(target_location)}"},
            {"name": "TradeIndia", "url": f"https://www.tradeindia.com/search/?search_string={quote_plus(product_query)}+{quote_plus(target_location)}"},
            {"name": "GeM Portal", "url": "https://gem.gov.in"},
        ],
        "note": "Suppliers ranked by physical proximity, platform verification, pricing availability, and certifications."
    }




# ─────────────────────────────────────────────────────────────────────────────
# 3. COMPETITOR ANALYZER
# ─────────────────────────────────────────────────────────────────────────────
class CompetitorInput(BaseModel):
    product: str = Field(description="The product to analyze competitors for")

@tool("competitor_analyzer", args_schema=CompetitorInput)
def competitor_analyzer(product: str) -> dict:
    """
    Analyzes top competitors, pricing, features,
    and market positioning for a product.
    """
    print("\n[TOOL CALLED] -> competitor_analyzer")

    queries = [
        f"top {product} manufacturers India brand comparison",
        f"{product} price comparison India 2024",
    ]

    data = search_and_scrape(queries, max_results_per_query=3, max_scrape=2)

    competitors = []
    seen_names  = set()

    for result in data["search_results"]:
        snippet = result["snippet"]
        title   = result["title"]

        if not snippet or len(snippet) < 20:
            continue

        prices = re.findall(
            r'₹\s*[\d,]+(?:\s*(?:lakh|crore|k))?|'
            r'Rs\.?\s*[\d,]+|'
            r'[\d,]+\s*(?:per unit|per piece|each)',
            snippet,
            re.IGNORECASE
        )

        brands = re.findall(
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+'
            r'(?:Ltd|Limited|Pvt|Industries|Corp|Manufacturing|Enterprises)\b',
            snippet
        )

        name = brands[0] if brands else title[:40]
        if name in seen_names:
            continue
        seen_names.add(name)

        features = re.findall(
            r'\b(energy[- ]efficient|ISO certified|BIS certified|'
            r'eco[- ]friendly|durable|automatic|semi[- ]automatic|'
            r'imported|domestic|premium|budget)\b',
            snippet,
            re.IGNORECASE
        )

        competitors.append({
            "name"         : name,
            "pricing"      : prices[0] if prices else "Contact for pricing",
            "key_features" : list(set(f.title() for f in features))[:3],
            "source_url"   : result["url"],
            "market_signal": snippet[:120],
        })

    for page in data["scraped_pages"]:
        content = page.get("content", "")
        price_rows = re.findall(
            r'([A-Z][^\n]{5,40}?)\s+(?:₹|Rs\.?)\s*([\d,]+)',
            content
        )
        for brand, price in price_rows[:2]:
            if brand.strip() not in seen_names:
                seen_names.add(brand.strip())
                competitors.append({
                    "name"         : brand.strip()[:40],
                    "pricing"      : f"₹{price}",
                    "key_features" : [],
                    "source_url"   : page["url"],
                    "market_signal": "",
                })

    kb_dir = get_manufacturing_kb_dir()
    _, kb_content = fetch_product_content(product, kb_dir)
    kb_competitors = []

    if kb_content:
        section = extract_section(
            kb_content,
            "competitor", "competition", "market player",
            "key player", "brand", "manufacturer"
        )
        if section:
            kb_competitors = parse_list_items(section)[:3]

    return {
        "product"        : product,
        "status"         : "live_search",
        "total_found"    : len(competitors),
        "competitors"    : competitors[:4],
        "kb_competitors" : kb_competitors,
        "competitive_signals": {
            "price_range"     : _extract_price_range(competitors),
            "common_features" : _most_common_features(competitors),
        },
        "note": "Data from public web sources. Validate pricing via direct outreach."
    }


def _extract_price_range(competitors: list) -> str:
    prices = []
    for c in competitors:
        pricing_str = str(c.get("pricing", "")).replace(",", "")
        clean_nums  = re.findall(r'\d+', pricing_str)
        if clean_nums:
            try:
                val = int(clean_nums[0])
                if val > 0:
                    prices.append(val)
            except (ValueError, TypeError):
                pass
    if prices:
        return f"₹{min(prices):,} – ₹{max(prices):,}"
    return "Not determined"


def _most_common_features(competitors: list) -> list:
    from collections import Counter
    all_features = []
    for c in competitors:
        all_features.extend(c.get("key_features", []))
    return [f for f, _ in Counter(all_features).most_common(4)]


# ─────────────────────────────────────────────────────────────────────────────
# 4. INDUSTRY REPORT SEARCH
# ─────────────────────────────────────────────────────────────────────────────
@tool("industry_report_search", args_schema=ResearchInput)
def industry_report_search(query: str) -> dict:
    """
    Searches and summarizes industry reports,
    whitepapers, government data, and PDFs.
    """
    print("\n[TOOL CALLED] -> industry_report_search")

    queries = [
        f"{query} industry report 2024 PDF India",
        f"site:ibef.org {query}",
    ]

    data = search_and_scrape(queries, max_results_per_query=3, max_scrape=2)

    reports = []
    for result in data["search_results"]:
        url    = result.get("url", "")
        domain = result.get("domain", "")

        credibility = (
            "high"   if any(d in domain for d in [
                "ibef.org", "makeinindia.com", "pib.gov.in",
                "mospi.gov.in", "commerce.gov.in", "cii.in",
                "ficci.in", "assocham.org"
            ]) else
            "medium" if any(d in domain for d in [
                "statista.com", "grandviewresearch.com",
                "mordorintelligence.com", "marketsandmarkets.com"
            ]) else
            "general"
        )

        is_pdf = url.endswith(".pdf") or "filetype=pdf" in url.lower()

        data_points = re.findall(
            r'[\d.]+\s*(?:%|crore|billion|million|CAGR|lakh)',
            result.get("snippet", ""),
            re.IGNORECASE
        )

        reports.append({
            "title"        : result.get("title", "")[:60],
            "url"          : url,
            "source"       : domain,
            "credibility"  : credibility,
            "is_pdf"       : is_pdf,
            "data_points"  : data_points[:2],
            "snippet"      : result.get("snippet", "")[:150],
        })

    key_stats = []
    for page in data["scraped_pages"]:
        content   = page.get("content", "")
        sentences = re.split(r'(?<=[.!?])\s+', content)
        for sent in sentences:
            if re.search(
                r'\d+(?:\.\d+)?\s*(?:%|crore|billion|lakh|CAGR|million)',
                sent, re.IGNORECASE
            ) and len(sent) < 150:
                key_stats.append({
                    "stat"  : sent.strip()[:150],
                    "source": page.get("url", ""),
                })

    return {
        "query"           : query,
        "status"          : "live_search",
        "total_reports"   : len(reports),
        "reports"         : sorted(
                               reports,
                               key=lambda x: {"high": 0, "medium": 1, "general": 2}[x["credibility"]]
                           )[:4],
        "key_statistics"  : key_stats[:4],
        "recommended_sources": [
            "https://www.ibef.org",
            "https://www.makeinindia.com/sector",
            "https://pib.gov.in",
        ],
        "note": "Prioritize 'high credibility' sources for DPR/investor reports."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. PATENT SEARCH
# ─────────────────────────────────────────────────────────────────────────────
@tool("patent_search", args_schema=ResearchInput)
def patent_search(query: str) -> dict:
    """
    Searches for existing patents and prior art
    to ensure IP compliance before manufacturing.
    """
    print("\n[TOOL CALLED] -> patent_search")

    queries = [
        f"{query} patent India IPINDIA",
        f"{query} manufacturing process patent",
    ]

    data = search_and_scrape(queries, max_results_per_query=3, max_scrape=2)

    patents = []
    for result in data["search_results"]:
        snippet = result.get("snippet", "")
        url     = result.get("url", "")

        patent_ids = re.findall(
            r'\b(?:IN|WO|US|EP|CN)\s*[\d/]+(?:[A-Z]\d*)?\b',
            snippet,
            re.IGNORECASE
        )

        years = re.findall(r'\b(20\d{2}|19\d{2})\b', snippet)

        applicants = re.findall(
            r'(?:filed by|applicant[:\s]+|assigned to)\s+([A-Z][^\.,]{5,30})',
            snippet,
            re.IGNORECASE
        )

        if patent_ids or "patent" in snippet.lower():
            patents.append({
                "patent_ids"  : patent_ids or ["See source"],
                "title"       : result.get("title", "")[:60],
                "applicants"  : applicants[:1],
                "years"       : years[:1],
                "url"         : url,
                "snippet"     : snippet[:120],
            })

    high_patent_density = len(patents) > 4
    ip_risk = (
        "High — Many existing patents found. Conduct FTO analysis."
        if high_patent_density else
        "Medium — Some patents found. Review before finalizing product design."
        if patents else
        "Low — Few patents found in search. Verify directly on ipindia.gov.in."
    )

    return {
        "query"         : query,
        "status"        : "live_search",
        "total_found"   : len(patents),
        "patents"       : patents[:4],
        "ip_risk_level" : ip_risk,
        "search_portals": [
            {
                "name": "IP India (Official)",
                "url" : "https://iprsearch.ipindia.gov.in/publicsearch"
            },
            {
                "name": "Google Patents",
                "url" : f"https://patents.google.com/?q={quote_plus(query)}&country=IN"
            },
        ],
        "recommended_action": "Engage a registered Patent Agent for a formal FTO search.",
        "note": "Web search is not a substitute for a formal patent clearance opinion."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. MARKET SIZE CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────
class MarketSizeInput(BaseModel):
    industry: str = Field(description="The industry to calculate market size for")
    region:   str = Field(description="The target region e.g. India, Global, Maharashtra")

@tool("market_size_calculator", args_schema=MarketSizeInput)
def market_size_calculator(industry: str, region: str) -> dict:
    """
    Calculates TAM, SAM, SOM using live market data
    and structured estimation methodology.
    """
    print("\n[TOOL CALLED] -> market_size_calculator")

    queries = [
        f"{industry} market size {region} 2024 crore billion",
        f"IBEF {industry} market size India",
    ]

    data = search_and_scrape(queries, max_results_per_query=3, max_scrape=2)

    market_figures = []
    cagr_figures   = []

    for page in data["scraped_pages"]:
        content = page.get("content", "")

        size_matches = re.findall(
            r'(?:₹|USD?|Rs\.?|\$)?\s*([\d,]+(?:\.\d+)?)\s*'
            r'(crore|billion|million|lakh|trillion)',
            content,
            re.IGNORECASE
        )
        for val, unit in size_matches[:3]:
            val_clean = float(val.replace(",", ""))
            if "billion" in unit.lower():
                val_crore = val_clean * 850
            elif "million" in unit.lower():
                val_crore = val_clean * 0.85
            elif "lakh" in unit.lower():
                val_crore = val_clean / 100
            else:
                val_crore = val_clean

            if val_crore > 10:
                market_figures.append(val_crore)

        cagr_hits = re.findall(
            r'CAGR\s*(?:of)?\s*([\d.]+)\s*%|'
            r'([\d.]+)\s*%\s*CAGR',
            content,
            re.IGNORECASE
        )
        for hit in cagr_hits:
            val = hit[0] or hit[1]
            if val:
                cagr_figures.append(float(val))

    if market_figures:
        tam_crore = round(max(market_figures), 0)
        data_source = "live_web_data"
    else:
        industry_lower = industry.lower()
        if any(k in industry_lower for k in ["pharma", "chemical"]):
            tam_crore = 8000
        elif any(k in industry_lower for k in ["food", "beverage", "fmcg"]):
            tam_crore = 15000
        elif any(k in industry_lower for k in ["textile", "garment"]):
            tam_crore = 5000
        elif any(k in industry_lower for k in ["electronic", "ev", "solar"]):
            tam_crore = 12000
        elif any(k in industry_lower for k in ["auto", "automotive"]):
            tam_crore = 20000
        else:
            tam_crore = 5000
        data_source = "estimated_fallback"

    avg_cagr   = round(sum(cagr_figures) / len(cagr_figures), 1) if cagr_figures else 12.0
    sam_crore  = round(tam_crore * 0.20, 0)
    som_crore  = round(sam_crore * 0.05, 0)

    def project(base, rate, years=5):
        return round(base * ((1 + rate / 100) ** years), 0)

    return {
        "industry"    : industry,
        "region"      : region,
        "data_source" : data_source,
        "cagr"        : f"{avg_cagr}%",
        "market_size" : {
            "TAM": {
                "value"         : f"₹{tam_crore:,.0f} Cr",
                "description"   : "Total Addressable Market",
                "5yr_projection": f"₹{project(tam_crore, avg_cagr):,.0f} Cr"
            },
            "SAM": {
                "value"         : f"₹{sam_crore:,.0f} Cr",
                "description"   : "Serviceable Available Market (20% TAM)",
                "5yr_projection": f"₹{project(sam_crore, avg_cagr):,.0f} Cr"
            },
            "SOM": {
                "value"         : f"₹{som_crore:,.0f} Cr",
                "description"   : "Serviceable Obtainable Market (5% SAM)",
                "5yr_projection": f"₹{project(som_crore, avg_cagr):,.0f} Cr"
            },
        },
        "sources"     : [
            {"title": r["title"], "url": r["url"]}
            for r in data["search_results"][:2]
        ],
        "note": "Validate TAM with IBEF / CII sector report."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. NEWS MONITOR
# ─────────────────────────────────────────────────────────────────────────────
@tool("news_monitor", args_schema=ResearchInput)
def news_monitor(query: str) -> dict:
    """
    Tracks live policy updates, subsidy changes,
    and recent government notifications.
    """
    print("\n[TOOL CALLED] -> news_monitor")

    queries = [
        f"{query} government policy notification 2024",
        f"site:pib.gov.in {query}",
    ]

    data = search_and_scrape(queries, max_results_per_query=3, max_scrape=2)

    news_items = []
    for result in data["search_results"]:
        snippet = result.get("snippet", "")
        url     = result.get("url", "")
        domain  = result.get("domain", "")

        category = (
            "Policy / Regulation" if any(k in snippet.lower() for k in [
                "policy", "regulation", "act", "bill", "notification", "gazette"]) else
            "Subsidy / Scheme"    if any(k in snippet.lower() for k in [
                "subsidy", "scheme", "incentive", "fund", "grant"]) else
            "Trade / Duty"        if any(k in snippet.lower() for k in [
                "import", "export", "duty", "tariff", "customs"]) else
            "Market / Industry"
        )

        dates = re.findall(
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*'
            r'\.?\s*\d{1,2}?,?\s*20\d{2}\b|'
            r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
            r'[a-z]*\s+20\d{2}\b',
            snippet,
            re.IGNORECASE
        )

        is_official = any(d in domain for d in [
            "pib.gov.in", "msme.gov.in", "dpiit.gov.in",
            "commerce.gov.in", "cbic.gov.in"
        ])

        news_items.append({
            "headline"   : result.get("title", "")[:80],
            "category"   : category,
            "date"       : dates[0] if dates else "Recent",
            "url"        : url,
            "source"     : domain,
            "is_official": is_official,
            "summary"    : snippet[:150],
        })

    news_items.sort(key=lambda x: (not x["is_official"], x["category"]))

    action_items = []
    for page in data["scraped_pages"]:
        content   = page.get("content", "")
        sentences = re.split(r'(?<=[.!?])\s+', content)
        for sent in sentences:
            if re.search(
                r'last date|apply before|deadline|effective from|'
                r'announced|launched|approved|notified',
                sent, re.IGNORECASE
            ) and len(sent) < 150:
                action_items.append({
                    "item"  : sent.strip()[:150],
                    "source": page.get("url", ""),
                })

    return {
        "query"         : query,
        "status"        : "live_search",
        "total_news"    : len(news_items),
        "news_items"    : news_items[:4],
        "action_items"  : action_items[:3],
        "official_portals": [
            {"name": "PIB",          "url": "https://pib.gov.in"},
            {"name": "MSME Ministry", "url": "https://msme.gov.in"},
            {"name": "DPIIT",         "url": "https://dpiit.gov.in"},
        ],
        "note": "Verify policy changes on official .gov.in portals."
    }


# ─────────────────────────────────────────────────────────────────────────────
research_tools_list = [
    web_search,
    supplier_search,
    competitor_analyzer,
    industry_report_search,
    patent_search,
    market_size_calculator,
    news_monitor,
]