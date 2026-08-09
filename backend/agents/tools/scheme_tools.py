import os
import re
import glob
from typing import Tuple
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchResults


# ─── Input Schemas ──────────────────────────────────────────────────────────

class SchemeSearchInput(BaseModel):
    industry: str = Field(description="The industry of the startup")
    location: str = Field(description="The state/location of the manufacturing unit")


class EligibilityInput(BaseModel):
    industry: str = Field(description="The industry")
    investment: str = Field(description="The planned investment amount")
    location: str = Field(description="The state or location")
    company_type: str = Field(description="Type of company (e.g., Pvt Ltd, LLP)", default="Startup")


class SubsidyInput(BaseModel):
    scheme_name: str = Field(description="The name of the scheme")
    investment: str = Field(description="The total investment amount e.g. '50 lakhs', '2 crore'")
    investment_type: str = Field(
        description="Type of investment: 'machinery', 'total_project', 'working_capital'",
        default="total_project"
    )


class CompareInput(BaseModel):
    scheme_1: str = Field(description="First scheme to compare")
    scheme_2: str = Field(description="Second scheme to compare")
    user_profile: str = Field(
        description="Brief user context e.g. 'MSME manufacturer in Gujarat with ₹50L investment'",
        default=""
    )


# ─── Helper Functions ────────────────────────────────────────────────────────

def parse_investment_to_lakhs(investment_str: str) -> float:
    """
    Converts investment string to a float in Lakhs.
    
    Examples:
        '50 lakhs'   -> 50.0
        '2 crore'    -> 200.0
        '₹1.5Cr'     -> 150.0
        '5000000'    -> 50.0  (raw rupees)
        '10L'        -> 10.0
    """
    text = investment_str.lower().strip()
    
    # Remove currency symbols
    text = text.replace("₹", "").replace("rs", "").replace("inr", "").strip()
    
    # Extract numeric value
    number_match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    if not number_match:
        return 0.0
    
    value = float(number_match.group())
    
    # Convert to lakhs based on unit
    if any(k in text for k in ["crore", "cr"]):
        return value * 100          # 1 crore = 100 lakhs

    elif any(k in text for k in ["lakh", "lac", " l"]):
        return value                # already in lakhs

    elif value >= 100_000:
        return value / 100_000      # raw rupees -> lakhs

    return value                    # assume lakhs if no unit


# Scheme rules: define real subsidy logic here
SCHEME_SUBSIDY_RULES = {
    "startup india seed fund": {
        "rate": 0.0,                # Grant, not % based
        "fixed_amount_lakhs": 20.0,
        "max_cap_lakhs": 20.0,
        "basis": "fixed_grant",
        "notes": "Up to ₹20L as grant for PoC/prototype stage"
    },
    "cgtmse": {
        "rate": 0.0,
        "fixed_amount_lakhs": 0.0,
        "max_cap_lakhs": 500.0,     # up to ₹5 Crore
        "basis": "guarantee",       # not a subsidy — a guarantee
        "notes": "Credit guarantee, not a direct subsidy. Covers up to 85% of loan."
    },
    "pmegp": {
        "rate": 0.15,               # 15% for urban
        "max_cap_lakhs": 37.5,      # 15% of ₹25L max project
        "basis": "total_project",
        "notes": "15% subsidy (urban) or 25% (rural/special category) on project cost up to ₹25L"
    },
    "msme credit linked capital subsidy": {
        "rate": 0.15,
        "max_cap_lakhs": 15.0,      # 15% of ₹1Cr machinery
        "basis": "machinery",
        "notes": "15% upfront capital subsidy on institutional finance for technology upgradation"
    },
    "stand-up india": {
        "rate": 0.0,
        "fixed_amount_lakhs": 0.0,
        "max_cap_lakhs": 100.0,
        "basis": "loan",
        "notes": "Composite loan ₹10L–₹1Cr, not a direct subsidy"
    },
    "mudra": {
        "rate": 0.0,
        "max_cap_lakhs": 20.0,
        "basis": "loan",
        "notes": "Loan up to ₹20L — Shishu (₹50K), Kishor (₹5L), Tarun (₹20L)"
    },
}


def lookup_scheme_from_knowledge_base(scheme_name: str) -> str:
    """
    Looks up the scheme file from Knowledge_OKF using the index.md.
    Returns the raw markdown content or empty string if not found.
    """
    knowledge_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "Knowledge_OKF")
    )
    index_path = os.path.join(knowledge_dir, "index.md")

    if not os.path.exists(index_path):
        return ""

    with open(index_path, "r", encoding="utf-8") as f:
        index_content = f.read()

    # Parse all links from index.md: [SCHEME NAME](scheme/file.md)
    pattern = r'\[([^\]]+)\]\(([^)]+\.md)\)'
    matches = re.findall(pattern, index_content)

    # Find best matching scheme name
    scheme_lower = scheme_name.lower().strip()
    best_match = None
    best_score = 0

    for name, relative_path in matches:
        name_lower = name.lower()
        score = sum(1 for word in scheme_lower.split() if word in name_lower)
        if score > best_score:
            best_score = score
            best_match = (name, relative_path)

    if not best_match or best_score == 0:
        return ""

    scheme_file = os.path.join(knowledge_dir, best_match[1])
    if not os.path.exists(scheme_file):
        return ""

    with open(scheme_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Strip YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()

    print(f"[KB] Matched scheme file: {best_match[1]} (score={best_score})")
    return content


def extract_subsidy_from_content(content: str) -> dict:
    """
    Tries to extract subsidy percentage and cap from raw markdown content.
    Returns dict with rate, cap, and any notes found.
    """
    extracted = {"rate": None, "cap_lakhs": None, "notes": []}

    # Look for percentage patterns: "25%", "15 percent", "up to 30%"
    pct_matches = re.findall(r'(\d+(?:\.\d+)?)\s*%', content)
    if pct_matches:
        rates = [float(p) for p in pct_matches]
        extracted["rate"] = max(rates) / 100
        extracted["notes"].append(f"Subsidy rate found: {max(rates)}%")

    # Look for cap amounts: "₹50 lakh", "maximum 2 crore", "up to ₹1Cr"
    cap_matches = re.findall(
        r'(?:up to|maximum|max|ceiling)[^\d]*?([\d,]+\.?\d*)\s*(lakh|lac|crore|cr|l\b)',
        content.lower()
    )
    if cap_matches:
        amount, unit = cap_matches[0]
        amount = float(amount.replace(",", ""))
        if "crore" in unit or unit == "cr":
            extracted["cap_lakhs"] = amount * 100
        else:
            extracted["cap_lakhs"] = amount
        extracted["notes"].append(f"Cap found: Rs {extracted['cap_lakhs']}L")

    return extracted


# ─── Tools ──────────────────────────────────────────────────────────────────

@tool("scheme_knowledge_base", args_schema=SchemeSearchInput)
def scheme_knowledge_base(industry: str, location: str) -> str:
    """Searches the knowledge base for government schemes, Startup India, MSME, PLI, FAME, etc."""
    print("\n[TOOL CALLED] -> scheme_knowledge_base")

    knowledge_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "Knowledge_OKF")
    )

    if not os.path.exists(knowledge_dir):
        return f"[ERROR] Knowledge base not found at: {knowledge_dir}"

    index_path = os.path.join(knowledge_dir, "index.md")
    if not os.path.exists(index_path):
        return f"[ERROR] index.md not found at: {index_path}"
    
    with open(index_path, "r", encoding="utf-8") as f:
        index_content = f.read()

    print(f"[KB] index.md loaded — {len(index_content)} chars")

    pattern = r'\[([^\]]+)\]\(([^)]+\.md)\)'
    matches = re.findall(pattern, index_content)

    print(f"[KB] Total schemes in index: {len(matches)}")

    if not matches:
        return "[ERROR] index.md found but no scheme links could be parsed. Check its format."

    terms = industry.lower().split() + location.lower().split()
    search_terms = [t for t in terms if len(t) > 3] or terms
    print(f"[SEARCH] Terms: {search_terms}")

    content_matched = []
    for scheme_name, relative_path in matches:
        full_path = os.path.join(knowledge_dir, relative_path)

        if not os.path.exists(full_path):
            continue

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            content_lower = content.lower()
            name_lower = scheme_name.lower()

            name_score    = sum(2 for t in search_terms if t in name_lower)
            content_score = sum(1 for t in search_terms if t in content_lower)
            total_score   = name_score + content_score

            if total_score > 0:
                content_matched.append((total_score, scheme_name, full_path, content))

        except Exception as e:
            print(f"[WARNING] Could not read {full_path}: {e}")

    content_matched.sort(key=lambda x: x[0], reverse=True)

    if not content_matched:
        all_names = [name for name, _ in matches]
        fallback_list = "\n".join(f"- {n}" for n in all_names[:20])
        return (
            f"No schemes directly matched for industry='{industry}', location='{location}'.\n\n"
            f"**All available schemes ({len(matches)} total):**\n{fallback_list}"
            + ("\n...and more." if len(all_names) > 20 else "")
        )

    output = f"**Top schemes for** `{industry}` in `{location}` "
    output += f"*(matched {len(content_matched)} of {len(matches)} schemes)*\n\n"

    for score, scheme_name, filepath, content in content_matched[:3]:
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()

        preview = content[:350].strip()
        if len(content) > 350:
            preview += "..."

        output += f"### {scheme_name}\n"
        output += f"*Score: {score} | File: {os.path.basename(filepath)}*\n\n"
        output += f"{preview}\n\n---\n\n"

    return output


@tool("eligibility_checker", args_schema=EligibilityInput)
def eligibility_checker(industry: str, investment: str, location: str, company_type: str = "Startup") -> dict:
    """
    Checks startup and MSME eligibility for government schemes and subsidies based on industry, investment, location, and company type.
    """
    print("\n[TOOL CALLED] -> eligibility_checker")
    print(f"   Industry: {industry} | Investment: {investment} | Location: {location} | Type: {company_type}")

    investment_lakhs = parse_investment_to_lakhs(investment)

    eligible_schemes = []
    ineligible_schemes = []

    # Scheme eligibility evaluation
    if investment_lakhs <= 25.0:
        eligible_schemes.append({
            "scheme": "PMEGP (Prime Minister's Employment Generation Programme)",
            "status": "Eligible",
            "reason": f"Project cost ₹{investment_lakhs:.1f}L is within the ₹25L micro-manufacturing limit."
        })
    else:
        ineligible_schemes.append({
            "scheme": "PMEGP",
            "status": "Ineligible",
            "reason": f"Project cost ₹{investment_lakhs:.1f}L exceeds maximum project cost limit of ₹25L."
        })

    if investment_lakhs <= 500.0:
        eligible_schemes.append({
            "scheme": "CGTMSE (Credit Guarantee Fund Trust for Micro and Small Enterprises)",
            "status": "Eligible",
            "reason": f"Investment ₹{investment_lakhs:.1f}L is eligible for collateral-free credit guarantee up to ₹5 Crore."
        })

    if investment_lakhs <= 20.0:
        eligible_schemes.append({
            "scheme": "Startup India Seed Fund Scheme (SISFS)",
            "status": "Eligible",
            "reason": "PoC/prototype stage startups eligible for seed grant up to ₹20L."
        })

    if investment_lakhs <= 100.0:
        eligible_schemes.append({
            "scheme": "MSME Credit Linked Capital Subsidy Scheme (CLCSS)",
            "status": "Eligible",
            "reason": "15% capital subsidy for technology upgradation on investment up to ₹1 Crore."
        })

    if investment_lakhs <= 20.0:
        eligible_schemes.append({
            "scheme": "PM MUDRA Yojana (Tarun Category)",
            "status": "Eligible",
            "reason": "Collateral-free business loans up to ₹20 Lakhs."
        })

    location_note = f"State-level incentives for {location} (e.g. SGST reimbursement, electricity duty exemption, land allotment subsidy) apply for {industry} manufacturing units."

    return {
        "user_profile": {
            "industry": industry,
            "investment_lakhs": f"₹{investment_lakhs:.2f} Lakhs",
            "location": location,
            "company_type": company_type
        },
        "eligible_schemes": eligible_schemes,
        "ineligible_schemes": ineligible_schemes,
        "location_incentives_note": location_note
    }


@tool("subsidy_calculator", args_schema=SubsidyInput)
def subsidy_calculator(scheme_name: str, investment: str, investment_type: str = "total_project") -> dict:
    """
    Calculates the estimated subsidy for a scheme and investment amount.
    Looks up real scheme data from the knowledge base first,
    then falls back to hardcoded rules, then to a generic estimate.
    """
    print("\n[TOOL CALLED] -> subsidy_calculator")
    print(f"   Scheme: {scheme_name} | Investment: {investment} | Type: {investment_type}")

    investment_lakhs = parse_investment_to_lakhs(investment)
    print(f"   Parsed investment: Rs {investment_lakhs:.2f} Lakhs")

    if investment_lakhs <= 0:
        return {
            "error": f"Could not parse investment amount from '{investment}'. "
                      "Please use formats like '50 lakhs', '2 crore', '₹1.5Cr'."
        }

    scheme_lower = scheme_name.lower().strip()
    matched_rule = None

    for rule_key, rule_data in SCHEME_SUBSIDY_RULES.items():
        if any(word in scheme_lower for word in rule_key.split() if len(word) > 3):
            matched_rule = rule_data
            print(f"   Matched hardcoded rule: '{rule_key}'")
            break

    kb_content = ""
    kb_extracted = {}

    if not matched_rule:
        print("   No hardcoded rule found — checking knowledge base...")
        kb_content = lookup_scheme_from_knowledge_base(scheme_name)

        if kb_content:
            kb_extracted = extract_subsidy_from_content(kb_content)
            print(f"   Extracted from KB: {kb_extracted}")

    result = {
        "scheme": scheme_name,
        "investment_input": investment,
        "investment_lakhs": f"₹{investment_lakhs:.2f} Lakhs",
        "investment_type": investment_type,
        "data_source": None,
        "estimated_subsidy_lakhs": None,
        "estimated_subsidy_formatted": None,
        "maximum_cap": None,
        "basis": None,
        "notes": None,
        "scheme_preview": None,
    }

    if matched_rule:
        basis = matched_rule.get("basis", "total_project")
        rate  = matched_rule.get("rate", 0.0)
        cap   = matched_rule.get("max_cap_lakhs", None)
        fixed = matched_rule.get("fixed_amount_lakhs", 0.0)

        if basis == "fixed_grant":
            subsidy = fixed
        elif basis in ("loan", "guarantee"):
            subsidy = 0.0
        else:
            subsidy = investment_lakhs * rate
            if cap:
                subsidy = min(subsidy, cap)

        result.update({
            "data_source": "hardcoded_rules",
            "estimated_subsidy_lakhs": round(subsidy, 2),
            "estimated_subsidy_formatted": f"₹{subsidy:.2f} Lakhs",
            "maximum_cap": f"₹{cap} Lakhs" if cap else "No cap defined",
            "basis": basis,
            "notes": matched_rule.get("notes", ""),
        })

    elif kb_extracted.get("rate"):
        rate    = kb_extracted["rate"]
        cap     = kb_extracted.get("cap_lakhs")
        subsidy = investment_lakhs * rate
        if cap:
            subsidy = min(subsidy, cap)

        result.update({
            "data_source": "knowledge_base",
            "estimated_subsidy_lakhs": round(subsidy, 2),
            "estimated_subsidy_formatted": f"₹{subsidy:.2f} Lakhs",
            "maximum_cap": f"₹{cap} Lakhs" if cap else "Not specified",
            "basis": investment_type,
            "notes": "; ".join(kb_extracted.get("notes", [])),
            "scheme_preview": kb_content[:400] + "..." if kb_content else None,
        })

    else:
        generic_rate    = 0.20
        generic_subsidy = investment_lakhs * generic_rate
        generic_cap     = 50.0
        subsidy         = min(generic_subsidy, generic_cap)

        result.update({
            "data_source": "generic_fallback",
            "estimated_subsidy_lakhs": round(subsidy, 2),
            "estimated_subsidy_formatted": f"₹{subsidy:.2f} Lakhs",
            "maximum_cap": f"₹{generic_cap} Lakhs (generic cap)",
            "basis": investment_type,
            "notes": (
                f"Could not find specific data for '{scheme_name}'. "
                "Generic 20% estimate applied. Please verify with official sources."
            ),
            "scheme_preview": kb_content[:400] + "..." if kb_content else None,
        })

    print(f"   Result: {result['estimated_subsidy_formatted']} | Source: {result['data_source']}")
    return result


@tool("loan_recommendation_tool", args_schema=SchemeSearchInput)
def loan_recommendation_tool(industry: str, location: str) -> dict:
    """
    Search the web and local loan knowledge base for government loan schemes, subsidies,
    startup funding, bank credit products, and manufacturing finance programs.

    Returns:
    - Local loan knowledge base matches (from Knowledge_loan)
    - Live search snippets
    - Scraped content
    - Fallback schemes
    """
    print("\n==============================")
    print("[TOOL CALLED] -> LOAN RECOMMENDATION TOOL")
    print("==============================")

    # ── 1. Local Knowledge Base Search (Knowledge_loan) ──────────────────
    local_loan_results = []
    try:
        knowledge_loan_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "Knowledge_loan")
        )
        index_path = os.path.join(knowledge_loan_dir, "index.md")

        search_terms = list(set([
            t for t in (industry.lower().split() + location.lower().split() + ["manufacturing", "msme", "loan", "startup", "finance", "credit"])
            if len(t) > 2
        ]))

        loan_entries = []
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                index_lines = f.readlines()

            for line in index_lines:
                if line.startswith("|") and re.search(r"\|\s*\d+\s*\|", line):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 6:
                        title = parts[2]
                        topic = parts[3]
                        url_match = re.search(r"\((https?://[^)]+)\)", parts[4])
                        url = url_match.group(1) if url_match else ""
                        file_match = re.search(r"\(([^)]+\.md)\)", parts[5])
                        rel_file = file_match.group(1) if file_match else ""
                        if rel_file:
                            loan_entries.append({
                                "title": title,
                                "topic": topic,
                                "url": url,
                                "rel_file": rel_file
                            })

        scored_loans = []

        if loan_entries:
            for entry in loan_entries:
                full_path = os.path.join(knowledge_loan_dir, entry["rel_file"])
                if not os.path.exists(full_path):
                    continue
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    c_lower = content.lower()
                    title_lower = entry["title"].lower()
                    topic_lower = entry["topic"].lower()

                    title_score = sum(3 for t in search_terms if t in title_lower)
                    topic_score = sum(2 for t in search_terms if t in topic_lower)
                    content_score = sum(1 for t in search_terms if t in c_lower)
                    total_score = title_score + topic_score + content_score

                    if total_score > 0:
                        clean_content = content
                        if clean_content.startswith("---"):
                            parts = clean_content.split("---", 2)
                            if len(parts) >= 3:
                                clean_content = parts[2].strip()

                        scored_loans.append((
                            total_score,
                            entry["title"],
                            entry["topic"],
                            entry["url"],
                            entry["rel_file"],
                            clean_content[:1500].strip()
                        ))
                except Exception as fe:
                    print(f"[WARNING] Reading loan file {entry['rel_file']} failed: {fe}")

        else:
            loans_dir = os.path.join(knowledge_loan_dir, "loans")
            if os.path.exists(loans_dir):
                for filepath in glob.glob(os.path.join(loans_dir, "*.md")):
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        c_lower = content.lower()
                        score = sum(1 for t in search_terms if t in c_lower)
                        if score > 0:
                            clean_content = content
                            if clean_content.startswith("---"):
                                parts = clean_content.split("---", 2)
                                if len(parts) >= 3:
                                    clean_content = parts[2].strip()
                            fname = os.path.basename(filepath).replace(".md", "").replace("_", " ")
                            rel_file = os.path.relpath(filepath, knowledge_loan_dir)
                            scored_loans.append((score, fname, "Loan Scheme", "", rel_file, clean_content[:1500].strip()))
                    except Exception:
                        continue

        scored_loans.sort(key=lambda x: x[0], reverse=True)

        for score, title, topic, url, rel_file, snippet in scored_loans[:5]:
            local_loan_results.append({
                "title": title,
                "topic": topic,
                "url": url,
                "file": rel_file,
                "relevance_score": score,
                "summary": snippet
            })

    except Exception as e:
        print(f"[WARNING] Local loan database search error: {e}")

    # ── 2. Live Web Search & Scraping ────────────────────────────────────
    search = DuckDuckGoSearchResults()

    queries = [
        f"{industry} manufacturing startup loan schemes {location}",
        f"government manufacturing subsidy {location} {industry}",
        f"SIDBI loan {industry}",
        f"CGTMSE manufacturing finance",
        f"MSME loan schemes {location}",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    all_search_results = []
    all_urls = set()
    scraped_results = []

    try:
        for query in queries:
            print(f"\n[SEARCH] Query: {query}")
            try:
                result = search.invoke(query)
                all_search_results.append({
                    "query": query,
                    "results": result
                })
                urls = re.findall(
                    r"link:\s*(https?://[^\],]+)",
                    result
                )
                all_urls.update(urls)
            except Exception as e:
                print(e)

        for url in list(all_urls)[:5]:
            try:
                print(f"[SCRAPE] {url}")
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=8
                )
                soup = BeautifulSoup(
                    response.text,
                    "html.parser"
                )
                title = (
                    soup.title.text.strip()
                    if soup.title
                    else "No title"
                )
                paragraphs = soup.find_all("p")
                text = " ".join(
                    p.get_text(" ", strip=True)
                    for p in paragraphs
                )
                text = re.sub(r"\s+", " ", text)

                scraped_results.append({
                    "title": title,
                    "url": url,
                    "domain": urlparse(url).netloc,
                    "is_government": (
                        ".gov.in" in url
                        or "msme.gov.in" in url
                        or "sidbi.in" in url
                    ),
                    "summary": text[:1500]
                })
            except Exception as e:
                print(f"Failed: {url}")
                print(e)

    except Exception as e:
        print(f"[WARNING] Web search error: {e}")

    fallback = [
        {
            "name": "CGTMSE",
            "loan_amount": "Up to ₹5 Crore",
            "collateral": "No",
            "best_for": "MSME Manufacturing"
        },
        {
            "name": "SIDBI Make in India Soft Loan",
            "loan_amount": "Project Based",
            "collateral": "Depends",
            "best_for": "Manufacturing Startups"
        },
        {
            "name": "PM Mudra Loan",
            "loan_amount": "Up to ₹20 Lakhs",
            "collateral": "No",
            "best_for": "Micro Enterprises"
        },
        {
            "name": "Stand-Up India",
            "loan_amount": "₹10L - ₹1Cr",
            "collateral": "Bank Rules",
            "best_for": "SC/ST/Women Entrepreneurs"
        },
        {
            "name": "PMEGP",
            "loan_amount": "Project Based",
            "best_for": "New Manufacturing Units"
        }
    ]

    return {
        "status": "success",
        "industry": industry,
        "location": location,
        "local_loan_data": local_loan_results,
        "total_local_loans_found": len(local_loan_results),
        "searched_queries": queries,
        "scraped_sources": scraped_results,
        "fallback_schemes": fallback,
        "search_results": all_search_results
    }


COMPARISON_KEYS = [
    "eligibility",
    "benefit",
    "subsidy",
    "incentive",
    "funding",
    "loan",
    "grant",
    "deadline",
    "last date",
    "application",
    "sector",
    "industry",
    "turnover",
    "investment",
    "collateral",
    "repayment",
    "interest",
    "duration",
    "validity",
    "nodal agency",
    "ministry",
    "contact",
]


def fetch_scheme_content(scheme_name: str, knowledge_dir: str) -> Tuple[str, str]:
    """
    Looks up scheme content from index.md + scheme file.

    Returns:
        (matched_name, content) — both empty strings if not found
    """
    index_path = os.path.join(knowledge_dir, "index.md")
    if not os.path.exists(index_path):
        print(f"[WARNING] index.md not found at {index_path}")
        return "", ""

    with open(index_path, "r", encoding="utf-8") as f:
        index_content = f.read()

    pattern = r'\[([^\]]+)\]\(([^)]+\.md)\)'
    all_schemes = re.findall(pattern, index_content)

    if not all_schemes:
        print("[WARNING] No scheme links found in index.md")
        return "", ""

    query_words = [w for w in scheme_name.lower().split() if len(w) > 2]
    best_score  = 0
    best_match  = None

    for name, relative_path in all_schemes:
        name_lower = name.lower()
        score = sum(1 for w in query_words if w in name_lower)
        if score > best_score:
            best_score = score
            best_match = (name, relative_path)

    if not best_match or best_score == 0:
        print(f"[WARNING] No match found for scheme: '{scheme_name}'")
        return "", ""

    scheme_file = os.path.join(knowledge_dir, best_match[1])
    if not os.path.exists(scheme_file):
        print(f"[WARNING] Scheme file missing: {scheme_file}")
        return best_match[0], ""

    with open(scheme_file, "r", encoding="utf-8") as f:
        content = f.read()

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()

    print(f"[KB] Loaded: '{best_match[0]}' from {best_match[1]} (score={best_score})")
    return best_match[0], content


def extract_scheme_dimensions(content: str, scheme_name: str) -> dict:
    """
    Extracts structured comparison dimensions from raw markdown content.
    """
    dimensions = {key: None for key in [
        "eligibility", "benefits", "funding_amount",
        "subsidy_rate", "deadline", "sector",
        "nodal_agency", "collateral", "summary"
    ]}

    if not content:
        dimensions["summary"] = f"No content found for {scheme_name}"
        return dimensions

    content_lower = content.lower()
    lines         = content.splitlines()

    current_header = None
    header_content = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            current_header = stripped.lstrip("#").strip().lower()
            header_content[current_header] = []
        elif current_header and stripped:
            header_content[current_header].append(stripped)

    header_map = {
        "eligibility"   : "eligibility",
        "eligible"      : "eligibility",
        "who can apply" : "eligibility",
        "benefits"      : "benefits",
        "incentives"    : "benefits",
        "what you get"  : "benefits",
        "funding"       : "funding_amount",
        "loan amount"   : "funding_amount",
        "grant"         : "funding_amount",
        "deadline"      : "deadline",
        "last date"     : "deadline",
        "validity"      : "deadline",
        "sector"        : "sector",
        "industries"    : "sector",
        "nodal agency"  : "nodal_agency",
        "ministry"      : "nodal_agency",
        "implemented by": "nodal_agency",
        "collateral"    : "collateral",
        "security"      : "collateral",
    }

    for header, lines_list in header_content.items():
        for h_key, dim_key in header_map.items():
            if h_key in header and lines_list:
                dimensions[dim_key] = " ".join(lines_list[:3])
                break

    kv_pattern = re.compile(r'^\s*[\*\-]?\s*(.{3,40}?)\s*[:–]\s*(.+)$', re.MULTILINE)
    for match in kv_pattern.finditer(content):
        key_raw = match.group(1).strip().lower()
        val_raw = match.group(2).strip()

        for h_key, dim_key in header_map.items():
            if h_key in key_raw and not dimensions[dim_key]:
                dimensions[dim_key] = val_raw
                break

    if not dimensions["funding_amount"]:
        amount_match = re.search(
            r'(?:up to|maximum|loan of|grant of|funding of)?\s*₹?\s*([\d,]+\.?\d*)\s*(lakh|lac|crore|cr)',
            content_lower
        )
        if amount_match:
            dimensions["funding_amount"] = (
                f"₹{amount_match.group(1)} {amount_match.group(2)}"
            )

    if not dimensions["subsidy_rate"]:
        rate_match = re.findall(r'(\d+(?:\.\d+)?)\s*%', content)
        if rate_match:
            dimensions["subsidy_rate"] = f"{', '.join(rate_match[:3])}%"

    dimensions["summary"] = content[:350].strip() + ("..." if len(content) > 350 else "")

    return dimensions


def generate_recommendation(
    name_1: str, dims_1: dict,
    name_2: str, dims_2: dict,
    user_profile: str
) -> str:
    """
    Rule-based recommendation logic comparing two parsed scheme profiles.
    """
    rec_lines = []

    def parse_lakhs(text: str) -> float:
        if not text:
            return 0.0
        text = text.lower()
        nums = re.findall(r'[\d,]+\.?\d*', text.replace(",", ""))
        if not nums:
            return 0.0
        val = float(nums[0])
        if "crore" in text or " cr" in text:
            return val * 100
        return val

    fund_1 = parse_lakhs(dims_1.get("funding_amount", ""))
    fund_2 = parse_lakhs(dims_2.get("funding_amount", ""))

    if fund_1 and fund_2:
        higher = name_1 if fund_1 >= fund_2 else name_2
        rec_lines.append(f"💰 **Higher funding ceiling:** {higher}")

    col_1 = dims_1.get("collateral", "") or ""
    col_2 = dims_2.get("collateral", "") or ""
    no_col_1 = "no" in col_1.lower() or "nil" in col_1.lower()
    no_col_2 = "no" in col_2.lower() or "nil" in col_2.lower()

    if no_col_1 and not no_col_2:
        rec_lines.append(f"🏦 **No collateral required:** {name_1}")
    elif no_col_2 and not no_col_1:
        rec_lines.append(f"🏦 **No collateral required:** {name_2}")

    if user_profile:
        profile_lower = user_profile.lower()

        if any(w in profile_lower for w in ["women", "sc", "st", "tribal"]):
            rec_lines.append(f"👥 **Best for SC/ST/Women:** Consider Stand-Up India or PMEGP")

        if "machinery" in profile_lower or "equipment" in profile_lower:
            rec_lines.append(f"⚙️  **For machinery-heavy investment:** Look for Capital Subsidy schemes")

        if any(w in profile_lower for w in ["export", "international"]):
            rec_lines.append(f"🌍 **For exporters:** Check MEIS or Export Promotion schemes")

    if not rec_lines:
        rec_lines.append(
            f"Both schemes have merit. Choose **{name_1}** for higher subsidy rate, "
            f"**{name_2}** for easier eligibility. Verify deadlines before applying."
        )

    return "\n".join(rec_lines)


@tool("scheme_comparison_tool", args_schema=CompareInput)
def scheme_comparison_tool(scheme_1: str, scheme_2: str, user_profile: str = "") -> dict:
    """
    Compares two government schemes by reading their actual content
    from the Knowledge_OKF knowledge base. Returns structured
    comparison across eligibility, benefits, funding, deadlines, and more.
    """
    print("\n[TOOL CALLED] -> scheme_comparison_tool")
    print(f"   Comparing: '{scheme_1}'  vs  '{scheme_2}'")
    print(f"   User profile: {user_profile or 'Not provided'}")

    knowledge_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "Knowledge_OKF")
    )

    if not os.path.exists(knowledge_dir):
        return {"error": f"Knowledge base not found at: {knowledge_dir}"}

    matched_name_1, content_1 = fetch_scheme_content(scheme_1, knowledge_dir)
    matched_name_2, content_2 = fetch_scheme_content(scheme_2, knowledge_dir)

    not_found = []
    if not content_1:
        not_found.append(scheme_1)
    if not content_2:
        not_found.append(scheme_2)

    if len(not_found) == 2:
        return {
            "error": f"Neither scheme found in knowledge base: {not_found}",
            "tip": "Check scheme names against index.md entries"
        }

    dims_1 = extract_scheme_dimensions(content_1, matched_name_1 or scheme_1)
    dims_2 = extract_scheme_dimensions(content_2, matched_name_2 or scheme_2)

    display_name_1 = matched_name_1 or scheme_1
    display_name_2 = matched_name_2 or scheme_2

    comparison_table = {}
    all_dim_keys = [
        "eligibility", "benefits", "funding_amount",
        "subsidy_rate", "deadline", "sector",
        "nodal_agency", "collateral"
    ]

    for key in all_dim_keys:
        val_1 = dims_1.get(key) or "Not specified"
        val_2 = dims_2.get(key) or "Not specified"

        if val_1 != "Not specified" or val_2 != "Not specified":
            comparison_table[key.replace("_", " ").title()] = {
                display_name_1: val_1,
                display_name_2: val_2,
            }

    recommendation = generate_recommendation(
        display_name_1, dims_1,
        display_name_2, dims_2,
        user_profile
    )

    return {
        "schemes_compared": [display_name_1, display_name_2],
        "data_source": "Knowledge_OKF knowledge base",
        "user_profile": user_profile or "Not provided",
        "comparison": comparison_table,
        "summaries": {
            display_name_1: dims_1.get("summary", ""),
            display_name_2: dims_2.get("summary", ""),
        },
        "recommendation": recommendation,
        "warning": (
            f"⚠️ '{scheme_1}' not found in KB — used generic data."
            if not content_1 else
            f"⚠️ '{scheme_2}' not found in KB — used generic data."
            if not content_2 else None
        ),
    }


scheme_tools_list = [
    scheme_knowledge_base,
    eligibility_checker,
    subsidy_calculator,
    loan_recommendation_tool,
    scheme_comparison_tool
]