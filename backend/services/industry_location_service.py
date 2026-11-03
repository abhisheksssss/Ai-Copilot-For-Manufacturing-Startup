"""Search and enrich the Government industrial-park catalogue.

The CSV is the source of truth for recommendations. Google Places is only used
to enrich the short-list with live place information when a server-side API key
is configured. This separation prevents an LLM or map search from inventing
industrial park availability data.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import httpx

DATASET_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "Industry_Location"
    / "IILB_Park_Report (2).csv"
)
GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

# Words that add no intent when matching a natural-language location request.
STOP_WORDS = {
    "a", "an", "and", "area", "best", "for", "find", "in", "industrial",
    "industry", "location", "locations", "me", "near", "of", "park", "parks",
    "please", "show", "the", "to", "with", "setup", "want", "start", "plant",
    "factory", "shed", "sqft", "sq", "ft", "workers", "units", "day", "setting",
    "up", "establish",
}

INDIAN_STATES_CANONICAL = {
    "andaman & nicobar": "Andaman & Nicobar",
    "andaman": "Andaman & Nicobar",
    "andhra pradesh": "Andhra Pradesh",
    "andhra": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "arunachal": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chandigarh": "Chandigarh",
    "chhattisgarh": "Chhattisgarh",
    "dadra & nagar haveli": "Dadra & Nagar Haveli",
    "daman & diu": "Daman & Diu",
    "delhi": "Delhi",
    "delhi ncr": "Delhi",
    "ncr": "Delhi",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh",
    "himachal": "Himachal Pradesh",
    "jammu & kashmir": "Jammu & Kashmir",
    "kashmir": "Jammu & Kashmir",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "ladakh": "Ladakh",
    "madhya pradesh": "Madhya Pradesh",
    "mp": "Madhya Pradesh",
    "maharashtra": "Maharashtra",
    "mh": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "puducherry": "Puducherry",
    "pondicherry": "Puducherry",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
    "tn": "Tamil Nadu",
    "telangana": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh",
    "up": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "uk": "Uttarakhand",
    "uttaranchal": "Uttarakhand",
    "west bengal": "West Bengal",
    "bengal": "West Bengal",
}

TOP_INDUSTRIAL_DISTRICTS = {
    "pune": ("Pune", "Maharashtra"),
    "chakan": ("Pune", "Maharashtra"),
    "talegaon": ("Pune", "Maharashtra"),
    "pimpri": ("Pune", "Maharashtra"),
    "kurkumbh": ("Pune", "Maharashtra"),
    "baramati": ("Pune", "Maharashtra"),
    "jejuri": ("Pune", "Maharashtra"),
    "thane": ("Thane", "Maharashtra"),
    "aurangabad": ("Aurangabad", "Maharashtra"),
    "chhatrapati sambhajinagar": ("Aurangabad", "Maharashtra"),
    "nagpur": ("Nagpur", "Maharashtra"),
    "nashik": ("Nashik", "Maharashtra"),
    "ahmedabad": ("Ahmedabad", "Gujarat"),
    "ahmadabad": ("Ahmedabad", "Gujarat"),
    "sanand": ("Ahmedabad", "Gujarat"),
    "changodar": ("Ahmedabad", "Gujarat"),
    "dholera": ("Ahmedabad", "Gujarat"),
    "surat": ("Surat", "Gujarat"),
    "vadodara": ("Vadodara", "Gujarat"),
    "baroda": ("Vadodara", "Gujarat"),
    "bharuch": ("Bharuch", "Gujarat"),
    "dahej": ("Bharuch", "Gujarat"),
    "ankleshwar": ("Bharuch", "Gujarat"),
    "rajkot": ("Rajkot", "Gujarat"),
    "kutch": ("Kutch", "Gujarat"),
    "mundra": ("Kutch", "Gujarat"),
    "chennai": ("Chennai", "Tamil Nadu"),
    "sriperumbudur": ("Kanchipuram", "Tamil Nadu"),
    "kanchipuram": ("Kanchipuram", "Tamil Nadu"),
    "oragadam": ("Kanchipuram", "Tamil Nadu"),
    "hosur": ("Krishnagiri", "Tamil Nadu"),
    "coimbatore": ("Coimbatore", "Tamil Nadu"),
    "tiruppur": ("Tiruppur", "Tamil Nadu"),
    "tirupur": ("Tiruppur", "Tamil Nadu"),
    "bengaluru": ("Bengaluru", "Karnataka"),
    "bangalore": ("Bengaluru", "Karnataka"),
    "bommasandra": ("Bengaluru", "Karnataka"),
    "peenya": ("Bengaluru", "Karnataka"),
    "mysuru": ("Mysuru", "Karnataka"),
    "gurgaon": ("Gurugram", "Haryana"),
    "gurugram": ("Gurugram", "Haryana"),
    "faridabad": ("Faridabad", "Haryana"),
    "manesar": ("Gurugram", "Haryana"),
    "sonipat": ("Sonipat", "Haryana"),
    "rai": ("Sonipat", "Haryana"),
    "panipat": ("Panipat", "Haryana"),
    "noida": ("Gautam Buddha Nagar", "Uttar Pradesh"),
    "greater noida": ("Gautam Buddha Nagar", "Uttar Pradesh"),
    "ghaziabad": ("Ghaziabad", "Uttar Pradesh"),
    "kanpur": ("Kanpur", "Uttar Pradesh"),
    "lucknow": ("Lucknow", "Uttar Pradesh"),
    "indore": ("Indore", "Madhya Pradesh"),
    "pithampur": ("Dhar", "Madhya Pradesh"),
    "bhopal": ("Bhopal", "Madhya Pradesh"),
    "mandideep": ("Raisen", "Madhya Pradesh"),
    "dewas": ("Dewas", "Madhya Pradesh"),
    "jaipur": ("Jaipur", "Rajasthan"),
    "jodhpur": ("Jodhpur", "Rajasthan"),
    "bhiwadi": ("Alwar", "Rajasthan"),
    "neemrana": ("Alwar", "Rajasthan"),
    "haridwar": ("Haridwar", "Uttarakhand"),
    "dehradun": ("Dehradun", "Uttarakhand"),
    "pantnagar": ("Udham Singh Nagar", "Uttarakhand"),
    "hyderabad": ("Hyderabad", "Telangana"),
    "medak": ("Medak", "Telangana"),
    "baddi": ("Solan", "Himachal Pradesh"),
    "solan": ("Solan", "Himachal Pradesh"),
    "ludhiana": ("Ludhiana", "Punjab"),
}

CURATED_SECTOR_HUBS: Dict[str, Dict[str, Any]] = {
    "battery": {
        "sector": "EV & Lithium-Ion Battery Pack Assembly",
        "state": "Maharashtra",
        "district": "Pune",
        "cluster": "Chakan - Talegaon Industrial Corridor (MIDC)",
        "score": 96,
        "summary": "Pune is India's premier EV manufacturing capital, hosting major EV OEMs (Tata Motors, Bajaj Auto, Kinetic Green, Mahindra) and 450+ tier-1 automotive suppliers within a 35 km radius.",
        "advantages": {
            "supply_chain_ecosystem": "Direct access to precision metal stamping, aluminum battery enclosures, BMS fabricators, and wiring harness vendors within a 30-minute transit.",
            "state_subsidies_policy": "Qualifies for Maharashtra Electric Vehicle Policy 2025: up to 15% capital subsidy, 100% stamp duty exemption, and ₹1.50/unit industrial electricity tariff rebate for 5 years.",
            "logistics_connectivity": "Direct access to Mumbai-Pune Expressway and JNPT Port (Nhava Sheva, 120 km) for duty-free containerized import of lithium cells from global cell manufacturers.",
            "spcb_clearance_siting": "MIDC notified industrial zones provide pre-zoned Green/Orange category approvals with 21-day fast-track Consent to Operate (CTO) on MPCB OCMMS portal.",
            "skilled_workforce": "Abundant availability of mechatronics engineers, robotics technicians, and high-voltage electrical safety personnel from 75+ accredited technical colleges."
        }
    },
    "solar": {
        "sector": "Solar PV Module Assembly & CleanTech Equipment",
        "state": "Gujarat",
        "district": "Ahmedabad",
        "cluster": "Sanand - Dholera Special Investment Region (DSIR)",
        "score": 95,
        "summary": "Gujarat anchors India's renewable energy manufacturing ecosystem with dedicated solar equipment zones, high solar insolation, and rapid coastal export gateways.",
        "advantages": {
            "supply_chain_ecosystem": "Direct access to solar glass suppliers, aluminum frame extrusion units, junction box makers, and EVA/backsheet converters.",
            "state_subsidies_policy": "Covered under Gujarat Electronics & Renewable Policy: 20% capital subsidy on equipment, ₹1/unit power tariff subsidy for 5 years, and 100% electricity duty waiver.",
            "logistics_connectivity": "Proximity to Mundra and Kandla ports (deep-water sea terminals) for rapid containerized export of finished PV modules and raw wafer imports.",
            "spcb_clearance_siting": "White/Green Category notification under GPCB with zero trade effluent discharge protocol.",
            "skilled_workforce": "Abundant industrial workforce trained at Gujarat Energy Research & Management Institute (GERMI) and state technical ITIs."
        }
    },
    "pharma": {
        "sector": "Pharmaceutical Formulations & Herbal / AYUSH Manufacturing",
        "state": "Uttarakhand",
        "district": "Haridwar",
        "cluster": "SIIDCUL Integrated Industrial Estate (IIE Haridwar)",
        "score": 94,
        "summary": "Haridwar is Northern India's largest Ayurvedic and pharmaceutical formulation cluster, housing 300+ herbal formulation units, Patanjali, and leading AYUSH GMP manufacturers.",
        "advantages": {
            "supply_chain_ecosystem": "Direct access to Himalayan medicinal herb collection hubs, standardized botanical extracts, and pharmaceutical packaging converters.",
            "state_subsidies_policy": "Uttarakhand Industrial Policy: Special AYUSH MSME capital subsidy, 5% interest subvention, and state GST reimbursement for 5 years.",
            "logistics_connectivity": "Strategic connectivity via NH-334 and Delhi-Dehradun Expressway providing 3-hour freight transit to the Delhi NCR consumer distribution hub.",
            "spcb_clearance_siting": "UEPPCB Green Category clearance for dry formulation without boiler, exempt from heavy effluent treatment norms.",
            "skilled_workforce": "Experienced Ayurvedic pharmacists, AYUSH-certified quality control chemists, and GMP packaging labor."
        }
    },
    "food": {
        "sector": "Automated Bakery, Confectionery & Food Processing",
        "state": "Madhya Pradesh",
        "district": "Indore",
        "cluster": "Pithampur - Dewas Industrial Corridor (MPIDC)",
        "score": 93,
        "summary": "Indore is the food processing and confectionery capital of central India, offering direct access to Central India's rich wheat, grain, sugar, and dairy agricultural belts.",
        "advantages": {
            "supply_chain_ecosystem": "Proximity to India's premier flour mills, commercial sugar refineries, edible oil packaging hubs, and dairy processing cooperatives.",
            "state_subsidies_policy": "MP Food Processing Scheme: 25% capital subsidy (up to ₹2.5 Cr), concession on mandi tax, and subsidized industrial land rates.",
            "logistics_connectivity": "Centrally positioned in India with Western & Central railway freight hubs, direct access to Delhi-Mumbai Expressway, and Indore Air Cargo.",
            "spcb_clearance_siting": "MPPCB Green Category classification for automated dry bakeries, minimal water pollution index score.",
            "skilled_workforce": "Readily available workforce specialized in high-speed confectionery wrapping, food technology, and FSSAI sanitation standards."
        }
    },
    "textile": {
        "sector": "Textiles, Weaving, Garments & Technical Fabrics",
        "state": "Gujarat",
        "district": "Surat",
        "cluster": "Surat Textile Mega Cluster & Apparel Park",
        "score": 95,
        "summary": "Surat produces over 40% of India's man-made fabric and synthetic textiles, featuring complete vertical integration from polyester yarn spinning to finished apparel.",
        "advantages": {
            "supply_chain_ecosystem": "Unmatched density of yarn texturizers, jacquard weaving looms, fabric dyeing units, and packaging material suppliers.",
            "state_subsidies_policy": "Gujarat Textile Policy: 6% interest subsidy on term loans, power tariff subsidy of ₹1/unit, and technology upgrade grant.",
            "logistics_connectivity": "Direct access to Western Dedicated Freight Corridor (DFC), Surat Airport, and Hazira Port for global fabric shipments.",
            "spcb_clearance_siting": "Dedicated industrial parks with functional Common Effluent Treatment Plants (CETPs) and GPCB monitoring.",
            "skilled_workforce": "Largest concentration of skilled power-loom technicians, cutting masters, and fashion garment tailors in Asia."
        }
    },
    "plastic": {
        "sector": "Plastic Injection Molding, Containers & Polymers",
        "state": "Gujarat",
        "district": "Ahmedabad",
        "cluster": "Sanand - Changodar Industrial Belt (GIDC)",
        "score": 94,
        "summary": "Gujarat produces over 60% of India's petrochemical polymers, anchoring world-class injection molding, blow molding, and industrial packaging ecosystems.",
        "advantages": {
            "supply_chain_ecosystem": "Immediate proximity to Reliance Industries (Hazira/Jamnagar) and ONGC petrochemical complexes for direct polymer granule supply at factory prices.",
            "state_subsidies_policy": "Gujarat Industrial Policy MSME incentives, capital investment subsidy, and assistance for quality certification.",
            "logistics_connectivity": "Direct highway connectivity to Mundra port and major domestic consumer markets across North and West India.",
            "spcb_clearance_siting": "Green Category classification for virgin polymer molding without plastic waste recycling emissions.",
            "skilled_workforce": "High availability of CIPET-certified plastic mold engineers and automated injection machine operators."
        }
    },
    "electronic": {
        "sector": "Electronics Hardware, SMT & PCB Assembly",
        "state": "Tamil Nadu",
        "district": "Kanchipuram",
        "cluster": "Sriperumbudur - Oragadam Industrial Corridor (SIPCOT)",
        "score": 96,
        "summary": "Sriperumbudur is India's hardware electronics capital, hosting global electronics manufacturers (Foxconn, Pegatron, Salcomp) and 150+ component ecosystems.",
        "advantages": {
            "supply_chain_ecosystem": "Concentrated cluster of SMT assembly lines, PCB manufacturers, semiconductor packaging, and precision metal stamping.",
            "state_subsidies_policy": "Tamil Nadu Electronics & Hardware Policy: Special capital subsidy, payroll subsidy, and training allowances.",
            "logistics_connectivity": "Direct proximity to Chennai Port (40 km), Ennore Port, and Chennai International Airport for air-freight electronics exports.",
            "spcb_clearance_siting": "TNPCB fast-track green approvals within notified SIPCOT industrial parks with uninterrupted 24/7 dual power feeder lines.",
            "skilled_workforce": "Largest pool of diploma electronics technicians and female precision assembly operators in India."
        }
    },
    "auto": {
        "sector": "Automotive & Precision Component Engineering",
        "state": "Maharashtra",
        "district": "Pune",
        "cluster": "Pimpri-Chinchwad & Chakan MIDC",
        "score": 96,
        "summary": "Pune's auto belt is the engineering backbone of Western India, hosting Tata, Bharat Forge, Cummins, and 2,000+ precision machining and auto ancillary units.",
        "advantages": {
            "supply_chain_ecosystem": "Unrivaled concentration of forging shops, CNC machining centers, foundry castings, heat treatment facilities, and automotive paint shops.",
            "state_subsidies_policy": "Maharashtra Package Scheme of Incentives (PSI): Industrial promotion subsidy on SGST, electricity duty waiver, and interest subsidy.",
            "logistics_connectivity": "Connected to NH-48, Mumbai-Pune Expressway, and air cargo connectivity via Pune International Airport.",
            "spcb_clearance_siting": "Pre-zoned MIDC industrial areas with dedicated industrial water and sub-station power allocations.",
            "skilled_workforce": "Dense concentration of mechanical engineers, CNC programmers, tool & die makers, and certified welding specialists."
        }
    }
}


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _tokens(value: str) -> set[str]:
    # Light stemming handles common catalogue/query variants such as textile/textiles.
    return {
        token.rstrip("s")
        for token in _normalise(value).split()
        if token not in STOP_WORDS and len(token) > 1
    }


def _as_float(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


@lru_cache(maxsize=1)
def load_industry_locations() -> list[dict[str, Any]]:
    """Read the source CSV once per process and return normalized records."""
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Industry location data was not found at {DATASET_PATH}")

    with DATASET_PATH.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))

    locations: list[dict[str, Any]] = []
    for row in rows:
        name = (row.get("Park Name") or "").strip()
        if not name:
            continue
        state = (row.get("State") or "").strip()
        district = (row.get("District") or "").strip()
        sector = (row.get("Sector") or "Mixed").strip()
        ind_type = (row.get("Industrial Park Type") or "").strip()

        locations.append(
            {
                "id": (row.get("Park ID") or row.get("SrNO") or name).strip(),
                "name": name,
                "state": state,
                "district": district,
                "sector": sector,
                "industrial_park_type": ind_type,
                "park_type": (row.get("Park Type") or "").strip(),
                "land_category": (row.get("Land Category") or "").strip(),
                "land_available_hectares": _as_float(row.get("Land Available (ha.)")),
                "total_land_hectares": _as_float(row.get("Total Land Area (ha.)")),
                "plug_and_play": (row.get("Plug And Play") or "").strip().lower() == "yes",
                "updated_at": (row.get("Update Date") or "").strip(),
                "name_tokens": _tokens(name),
                "sector_tokens": _tokens(sector),
                "search_tokens": _tokens(f"{name} {district} {state} {sector} {ind_type}"),
            }
        )
    return locations


@lru_cache(maxsize=1)
def list_all_states() -> List[str]:
    """Returns sorted unique Indian states present in the IILB catalogue."""
    locations = load_industry_locations()
    states_set = {loc["state"].title() for loc in locations if loc.get("state")}
    return sorted(list(states_set))


def detect_user_specified_location(query: str) -> Optional[Dict[str, Any]]:
    """
    Scans a natural-language query to determine if the user has explicitly requested
    a specific state, city, or district in India.
    Returns {"state": ..., "district": ..., "label": ...} or None if no place was requested.
    """
    clean_q = _normalise(query)
    q_spaced = f" {clean_q} "

    # 1. District / City checks (more specific)
    for district_key, (district_name, state_name) in TOP_INDUSTRIAL_DISTRICTS.items():
        pattern = f" {district_key} "
        if pattern in q_spaced:
            return {
                "district": district_name,
                "state": state_name,
                "label": f"{district_name}, {state_name}"
            }

    # 2. State checks
    for state_key, canonical_state in INDIAN_STATES_CANONICAL.items():
        pattern = f" {state_key} "
        if pattern in q_spaced:
            return {
                "district": None,
                "state": canonical_state,
                "label": canonical_state
            }

    return None


def _has_network_access() -> bool:
    import socket
    try:
        s = socket.create_connection(("8.8.8.8", 53), timeout=0.15)
        s.close()
        return True
    except OSError:
        return False


def get_optimal_location_recommendation(
    query: str,
    state_preference: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Determines the single most optimal manufacturing cluster in India for the query,
    providing a comprehensive 5-pillar 'Why this land will be good for you' rationale.
    Uses Groq LLM with a curated sector-hub knowledge base fallback.
    """
    clean_q = query.strip()
    query_lower = clean_q.lower()

    # Step A: Attempt Groq LLM Generation if configured and online
    groq_key = os.getenv("GROQ_API_KEY") if os.getenv("TESTING") != "1" else None
    if groq_key and _has_network_access():
        try:
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                api_key=groq_key,
                model_name="openai/gpt-oss-20b",
                temperature=0.1,
                max_tokens=1000,
                request_timeout=2.0,
                max_retries=0
            )

            prompt = (
                f"You are India's premier industrial siting, manufacturing SEZ, and factory location advisor.\n"
                f"Analyze this industrial plant setup query:\n"
                f"Query: \"{clean_q}\"\n"
                f"State Preference: {state_preference or 'All India (Recommend Best State)'}\n\n"
                f"Task: Recommend the single #1 most optimal manufacturing state, district, and industrial corridor in India for this product.\n"
                f"Provide a structured justification across the 5 industrial pillars.\n"
                f"Return strictly a JSON object with this exact structure:\n"
                f"{{\n"
                f"  \"sector\": \"Manufacturing sector name\",\n"
                f"  \"recommended_state\": \"Official Indian State (Title Case, e.g. Maharashtra)\",\n"
                f"  \"recommended_district\": \"District name (e.g. Pune)\",\n"
                f"  \"recommended_cluster\": \"Industrial corridor name (e.g. Chakan - Talegaon Industrial Corridor (MIDC))\",\n"
                f"  \"suitability_score\": 95,\n"
                f"  \"why_recommended_summary\": \"2-3 concise sentences explaining why this cluster is #1 in India for this plant\",\n"
                f"  \"key_advantages\": {{\n"
                f"    \"supply_chain_ecosystem\": \"Details on supplier density, raw material access & OEM buyers\",\n"
                f"    \"state_subsidies_policy\": \"State industrial policy benefits, capital subsidy %, power tariff rebates\",\n"
                f"    \"logistics_connectivity\": \"Access to expressways, dedicated freight corridors, ports & air cargo\",\n"
                f"    \"spcb_clearance_siting\": \"Pollution control board clearance ease, green zoning, fast-track single-window portal\",\n"
                f"    \"skilled_workforce\": \"Availability of technical engineers, ITIs & specialized labor pool\"\n"
                f"  }}\n"
                f"}}\n"
                f"Respond with JSON ONLY. Do not wrap in markdown or backticks."
            )

            resp = llm.invoke(prompt)
            text_content = resp.content if hasattr(resp, "content") else str(resp)

            # Clean JSON
            text_content = re.sub(r"^```(?:json)?\s*", "", text_content.strip())
            text_content = re.sub(r"\s*```$", "", text_content.strip())

            parsed = json.loads(text_content)
            if isinstance(parsed, dict) and "recommended_state" in parsed and "key_advantages" in parsed:
                return parsed
        except Exception as e:
            print(f"[LOCATION ADVISOR] Groq recommendation fallback triggered: {e}")

    # Step B: Curated Fallback Matrix Matching
    best_hub = None
    if any(k in query_lower for k in ["battery", "lithium", "ev", "electric vehicle", "cell pack"]):
        best_hub = CURATED_SECTOR_HUBS["battery"]
    elif any(k in query_lower for k in ["solar", "pv", "photovoltaic", "cleantech", "renewable"]):
        best_hub = CURATED_SECTOR_HUBS["solar"]
    elif any(k in query_lower for k in ["pharma", "ayurved", "herbal", "medicine", "tablet", "capsule", "drug"]):
        best_hub = CURATED_SECTOR_HUBS["pharma"]
    elif any(k in query_lower for k in ["bakery", "biscuit", "confectionery", "food", "snack", "flour", "beverage"]):
        best_hub = CURATED_SECTOR_HUBS["food"]
    elif any(k in query_lower for k in ["textile", "fabric", "yarn", "garment", "apparel", "weaving"]):
        best_hub = CURATED_SECTOR_HUBS["textile"]
    elif any(k in query_lower for k in ["plastic", "polymer", "injection", "molding", "moulding", "pet bottle"]):
        best_hub = CURATED_SECTOR_HUBS["plastic"]
    elif any(k in query_lower for k in ["electronic", "pcb", "smt", "chip", "semiconductor", "hardware"]):
        best_hub = CURATED_SECTOR_HUBS["electronic"]
    elif any(k in query_lower for k in ["auto", "machining", "forging", "cnc", "engine", "gear"]):
        best_hub = CURATED_SECTOR_HUBS["auto"]
    else:
        # Default intelligent multi-sector industrial hub
        best_hub = CURATED_SECTOR_HUBS["battery"]

    # Adapt if state preference was specified
    target_state = state_preference.strip() if state_preference and state_preference != "All India" else best_hub["state"]

    return {
        "sector": best_hub["sector"],
        "recommended_state": target_state,
        "recommended_district": best_hub["district"],
        "recommended_cluster": best_hub["cluster"],
        "suitability_score": best_hub["score"],
        "why_recommended_summary": best_hub["summary"],
        "key_advantages": best_hub["advantages"]
    }


def _score_location(
    location: dict[str, Any],
    query: str,
    target_state: Optional[str] = None,
    target_district: Optional[str] = None,
    q_norm: Optional[str] = None,
    q_tokens: Optional[set[str]] = None
) -> tuple[float, list[str]]:
    """Score a catalogue record and retain the exact reasons shown to users."""
    loc_state = location["state"].lower()
    loc_district = location["district"].lower()

    # If target state is specified, strictly filter
    if target_state:
        if loc_state != target_state.lower():
            return 0.0, []

    query_normalised = q_norm if q_norm is not None else _normalise(query)
    query_terms = q_tokens if q_tokens is not None else _tokens(query)
    reasons: list[str] = []
    score = 0.0

    # District target boost
    if target_district and target_district.lower() in loc_district:
        score += 50.0
        reasons.append(f"Located in target district: {location['district']}")

    fields = {
        "park name": _normalise(location["name"]),
        "district": loc_district,
        "state": loc_state,
        "sector": _normalise(location["sector"]),
        "park type": _normalise(location["industrial_park_type"]),
    }

    # Exact name and sector matches
    name_terms = location.get("name_tokens") or _tokens(location["name"])
    sector_terms = location.get("sector_tokens") or _tokens(location["sector"])
    if name_terms and name_terms.issubset(query_terms) and name_terms != sector_terms:
        score += 16
        reasons.append("Matches requested park name")

    for label, weight in (("district", 14), ("state", 10), ("sector", 14), ("park type", 6)):
        value = fields[label]
        if value and value in query_normalised:
            score += weight
            if label in {"district", "state", "sector"}:
                reasons.append(f"Matches requested {label}: {location[label.replace(' ', '_')]}")

    loc_tokens = location.get("search_tokens")
    if loc_tokens is None:
        loc_tokens = _tokens(" ".join(fields.values()))
    matched_terms = query_terms.intersection(loc_tokens)
    score += len(matched_terms) * 3

    available = location["land_available_hectares"]
    if available > 0:
        score += min(10.0, available / 10)
        reasons.append(f"{available:g} ha available land reported")
    if location["plug_and_play"]:
        score += 4
        reasons.append("Plug-and-play ready facility")

    if not reasons:
        reasons.append("Government IILB catalogue verified park")

    return score, reasons[:3]


def _maps_search_link(location: dict[str, Any]) -> str:
    place_query = ", ".join(
        part for part in (location["name"], location["district"], location["state"], "India") if part
    )
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(place_query)}"


async def _enrich_with_google_place(location: dict[str, Any], client: httpx.AsyncClient, api_key: str) -> dict[str, Any] | None:
    """Retrieve a narrowly scoped, live Google Places result for one park."""
    text_query = ", ".join(
        part for part in (location["name"], location["district"], location["state"], "India") if part
    )
    try:
        response = await client.post(
            GOOGLE_PLACES_URL,
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": (
                    "places.id,places.displayName,places.formattedAddress,places.location,"
                    "places.businessStatus,places.rating,places.userRatingCount,"
                    "places.websiteUri,places.googleMapsLinks"
                ),
            },
            json={"textQuery": text_query, "maxResultCount": 1},
        )
        response.raise_for_status()
        places = response.json().get("places", [])
        if not places:
            return None
        place = places[0]
        maps_links = place.get("googleMapsLinks") or {}
        return {
            "source": "google_places",
            "place_id": place.get("id"),
            "name": (place.get("displayName") or {}).get("text"),
            "formatted_address": place.get("formattedAddress"),
            "latitude": (place.get("location") or {}).get("latitude"),
            "longitude": (place.get("location") or {}).get("longitude"),
            "business_status": place.get("businessStatus"),
            "rating": place.get("rating"),
            "user_rating_count": place.get("userRatingCount"),
            "website_uri": place.get("websiteUri"),
            "maps_uri": maps_links.get("placeUri"),
        }
    except (httpx.HTTPError, ValueError):
        return None


def search_industry_locations_sync(
    query: str,
    limit: int = 5,
    state_filter: Optional[str] = None,
    mode: str = "auto"  # "auto" | "specific" | "recommendation"
) -> dict[str, Any]:
    """
    Synchronously ranks catalogue entries and provides optimal location recommendations.
    - If user specifies a location or mode='specific': Honors their location strictly, recommendation=None.
    - If user did not mention location or mode='recommendation': Generates #1 optimal recommendation and explains why.
    """
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("A plant description, industry sector, or target location is required.")

    # 1. Determine mode & location specification
    detected_loc = detect_user_specified_location(clean_query)
    user_specified_location: Optional[str] = None
    recommendation: Optional[Dict[str, Any]] = None

    target_state = state_filter
    target_district = None

    if mode == "specific" or state_filter:
        # User explicitly requested a specific location
        if detected_loc:
            user_specified_location = detected_loc["label"]
            target_state = target_state or detected_loc["state"]
            target_district = detected_loc.get("district")
        else:
            user_specified_location = state_filter or clean_query
        recommendation = None
    elif mode == "recommendation":
        # Always generate optimal location recommendation
        recommendation = get_optimal_location_recommendation(clean_query, state_preference=state_filter)
        user_specified_location = None
        if recommendation:
            target_state = recommendation.get("recommended_state")
            target_district = recommendation.get("recommended_district")
    else:  # mode == "auto"
        if detected_loc:
            # User provided a particular place in the natural language query -> Do not provide unsolicited recommendation
            user_specified_location = detected_loc["label"]
            target_state = detected_loc["state"]
            target_district = detected_loc.get("district")
            recommendation = None
        else:
            # No location mentioned -> Suggest optimal place with deep explanation
            user_specified_location = None
            recommendation = get_optimal_location_recommendation(clean_query, state_preference=state_filter)
            if recommendation:
                target_state = recommendation.get("recommended_state")
                target_district = recommendation.get("recommended_district")

    # 2. Score and rank IILB catalogue records
    q_norm = _normalise(clean_query)
    q_tokens = _tokens(clean_query)
    all_locations = load_industry_locations()

    ranked = []
    for location in all_locations:
        score, reasons = _score_location(
            location,
            clean_query,
            target_state=target_state,
            target_district=target_district,
            q_norm=q_norm,
            q_tokens=q_tokens
        )
        if score > 0:
            ranked.append((score, location, reasons))

    # Fallback to broader search if strict district search produced zero hits
    if not ranked and target_district:
        for location in all_locations:
            score, reasons = _score_location(
                location,
                clean_query,
                target_state=target_state,
                target_district=None,
                q_norm=q_norm,
                q_tokens=q_tokens
            )
            if score > 0:
                ranked.append((score, location, reasons))

    ranked.sort(key=lambda item: (-item[0], -item[1]["land_available_hectares"], item[1]["name"]))
    selected = ranked[:limit]

    results: list[dict[str, Any]] = []
    for score, location, reasons in selected:
        maps_url = _maps_search_link(location)
        results.append(
            {
                **location,
                "score": round(score, 2),
                "match_reasons": reasons,
                "maps_url": maps_url,
                "live_place": None,
                "summary": (
                    f"{location['name']} is a {location['industrial_park_type'] or 'notified industrial park'} "
                    f"in {location['district']}, {location['state']}. "
                    f"Sector: {location['sector']}. "
                    f"Reported available land: {location['land_available_hectares']:g} ha."
                ),
            }
        )

    return {
        "query": clean_query,
        "mode": mode,
        "user_specified_location": user_specified_location,
        "recommendation": recommendation,
        "total_catalogue_locations": len(all_locations),
        "google_places_enrichment": "not_configured",
        "results": results,
        "disclaimer": (
            "Land and facility metrics originate from the India Industrial Land Bank (IILB) catalogue. "
            "Verify current plot booking availability and SPCB zoning with the state industrial development authority."
        ),
    }


async def search_industry_locations(
    query: str,
    limit: int = 5,
    enrich: bool = True,
    state_filter: Optional[str] = None,
    mode: str = "auto"  # "auto" | "specific" | "recommendation"
) -> dict[str, Any]:
    """
    Ranks catalogue entries and provides optimal location recommendations when applicable.
    Enriches with live Google Places data if enrich=True and GOOGLE_MAPS_API_KEY is configured.
    """
    base_response = search_industry_locations_sync(
        query=query,
        limit=limit,
        state_filter=state_filter,
        mode=mode
    )
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not (enrich and api_key and base_response["results"]):
        return base_response

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            google_results = await asyncio.gather(
                *[_enrich_with_google_place(loc, client, api_key) for loc in base_response["results"]]
            )

        for res, google_place in zip(base_response["results"], google_results):
            if google_place:
                res["live_place"] = google_place
                if google_place.get("maps_uri"):
                    res["maps_url"] = google_place["maps_uri"]

        base_response["google_places_enrichment"] = "enabled"
    except Exception:
        pass

    return base_response
