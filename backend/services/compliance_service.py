import os
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from models.compliance import (
    ComplianceAssessmentRequest,
    ComplianceAssessmentResponse,
    PermitItem,
    CarbonMetrics,
    SolarProjection,
    SectorSummary
)

_CACHE_SECTORS: Dict[str, Any] = {}
_KNOWLEDGE_COMPLIANCE_DIR: Optional[str] = None


def get_compliance_data_dir() -> str:
    global _KNOWLEDGE_COMPLIANCE_DIR
    if _KNOWLEDGE_COMPLIANCE_DIR and os.path.exists(_KNOWLEDGE_COMPLIANCE_DIR):
        return _KNOWLEDGE_COMPLIANCE_DIR

    candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "Knowledge_compliance")),
        os.path.abspath("d:/CodeWIthMe/HackMatrix/backend/data/Knowledge_compliance"),
        os.path.abspath("d:/CodeWIthMe/Ai Copilot For manufacturing Startups/backend/data/Knowledge_compliance"),
    ]
    for path in candidates:
        if os.path.exists(path):
            _KNOWLEDGE_COMPLIANCE_DIR = path
            return path

    return candidates[0]


def load_master_sectors() -> Dict[str, Any]:
    global _CACHE_SECTORS
    if _CACHE_SECTORS:
        return _CACHE_SECTORS

    kb_dir = get_compliance_data_dir()
    json_path = os.path.join(kb_dir, "cpcb_sectors.json")

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                _CACHE_SECTORS = json.load(f)
                return _CACHE_SECTORS
        except Exception as e:
            print(f"[COMPLIANCE] Error reading cpcb_sectors.json: {e}")

    return {}


def list_all_sectors(query: Optional[str] = None, category: Optional[str] = None, limit: int = 50) -> List[SectorSummary]:
    sectors = load_master_sectors()
    results = []

    q_lower = (query or "").strip().lower()
    cat_lower = (category or "").strip().lower()

    for slug, item in sectors.items():
        if cat_lower and item.get("category", "").lower() != cat_lower:
            continue

        if q_lower:
            title = str(item.get("title", "")).lower()
            tags = " ".join([str(t) for t in item.get("tags", [])]).lower()
            if q_lower not in title and q_lower not in slug and q_lower not in tags:
                continue

        results.append(
            SectorSummary(
                slug=slug,
                title=str(item.get("title", slug)),
                category=str(item.get("category", "Green")),
                pollution_index_score=float(item.get("pollution_index_score", 0)),
                pollution_index_range=str(item.get("pollution_index_range", "")),
                cpcb_serial_no=str(item.get("cpcb_serial_no", "")),
                requires_cte=bool(item.get("requires_cte", True)),
                requires_cto=bool(item.get("requires_cto", True)),
                validity_period=str(item.get("validity_period", "5 Years")),
                etp_apcd_mandatory=bool(item.get("etp_apcd_mandatory", False)),
                tags=[str(t) for t in item.get("tags", [])],
            )
        )
        if len(results) >= limit:
            break

    return results


def find_best_matching_sector(req: ComplianceAssessmentRequest) -> Tuple[Dict[str, Any], str]:
    sectors = load_master_sectors()

    # 1. Exact slug match
    if req.industry_slug and req.industry_slug in sectors:
        return sectors[req.industry_slug], "Exact match from CPCB official harmonized sectors."

    # 2. Text / Keyword matching
    search_text = (req.custom_industry_text or req.industry_slug or "assembly").lower()
    search_words = [w for w in re.split(r"\W+", search_text) if len(w) > 2]

    best_match = None
    best_score = 0

    for slug, item in sectors.items():
        title_lower = str(item.get("title", "")).lower()
        tags_lower = [str(t).lower() for t in item.get("tags", [])]

        score = 0
        for word in search_words:
            if word in slug:
                score += 3
            if word in title_lower:
                score += 4
            if word in tags_lower:
                score += 2

        if score > best_score:
            best_score = score
            best_match = item

    if best_match and best_score >= 3:
        return best_match, f"Best match for query '{search_text}' with confidence score {best_score}."

    # 3. Default fallback
    if "battery" in search_text or "chemical" in search_text:
        fallback_slug = "lead-acid-battery-manufacturing-excluding-assembling-and-charging-of-lead-a"
    elif "electronic" in search_text or "solar" in search_text:
        fallback_slug = "manufacturing-of-solar-module-non-conventional-energy-apparatus-without"
    else:
        fallback_slug = "engineering-and-fabrication-units-dry-process-without-painting-and-heat"

    if fallback_slug in sectors:
        return sectors[fallback_slug], f"No direct match for '{search_text}'. Mapped to standard sector."

    # Minimal default object if dataset missing
    return {
        "slug": "general-manufacturing-unit",
        "title": "General Manufacturing / Assembly Unit",
        "category": "Green",
        "pollution_index_score": 32.0,
        "pollution_index_range": "21-40",
        "cpcb_serial_no": "G-GEN",
        "requires_cte": True,
        "requires_cto": True,
        "validity_period": "10 Years",
        "etp_apcd_mandatory": False,
        "tags": ["manufacturing", "general"],
        "relative_path": "sectors/green/general-manufacturing.md",
    }, "Default fallback categorization."


def generate_statutory_permits(
    req: ComplianceAssessmentRequest,
    category: str,
    etp_mandatory: bool
) -> List[PermitItem]:
    permits: List[PermitItem] = []
    state = req.state.strip() or "State"
    spcb_name = f"{state} Pollution Control Board"

    # 1. CTE (Consent to Establish)
    if category != "White":
        fee = 35000.0 if category == "Red" else (22000.0 if category == "Orange" else 10000.0)
        lead = 60 if category == "Red" else (45 if category == "Orange" else 30)
        permits.append(
            PermitItem(
                id="SPCB_CTE",
                name="Consent to Establish (CTE)",
                authority=spcb_name,
                category="Mandatory Pre-Construction",
                mandatory=True,
                lead_time_days=lead,
                estimated_fee_inr=fee,
                description=f"Statutory approval under Water Act 1974 & Air Act 1981 required before commencing civil construction or site alteration for {category} category industries.",
                documents_required=[
                    "Land ownership deed / Lease agreement (min 5 years)",
                    "Comprehensive Project Report (DPR) with process flow diagram",
                    "Plant layout showing ETP, green belt (33%), and machinery placement",
                    "Water balance and material balance calculations",
                    "Topographical map within 5 km radius"
                ]
            )
        )
    else:
        permits.append(
            PermitItem(
                id="SPCB_WHITE_INTIMATION",
                name="White Category Online Intimation & Acknowledgment",
                authority=spcb_name,
                category="Mandatory Pre-Construction",
                mandatory=True,
                lead_time_days=1,
                estimated_fee_inr=0.0,
                description="Exempt from formal CTE/CTO inspections. Requires simple online self-declaration on the state OCMMS portal.",
                documents_required=[
                    "Factory registration / Udyam MSME certificate",
                    "Process undertaking declaring zero toxic trade effluent and no boiler emissions"
                ]
            )
        )

    # 2. CTO (Consent to Operate)
    if category != "White":
        fee = 28000.0 if category == "Red" else (18000.0 if category == "Orange" else 8000.0)
        lead = 45 if category == "Red" else (30 if category == "Orange" else 21)
        permits.append(
            PermitItem(
                id="SPCB_CTO",
                name="Consent to Operate (CTO)",
                authority=spcb_name,
                category="Pre-Commissioning",
                mandatory=True,
                lead_time_days=lead,
                estimated_fee_inr=fee,
                description=f"Mandatory clearance under Water and Air Acts before commissioning machinery, raw material feeding, or trial runs.",
                documents_required=[
                    "CTE compliance report with physical proof of environmental safeguards",
                    "ETP / APCD commissioning certificate by certified environmental engineer",
                    "Adequacy report of pollution control systems",
                    "Analysis report of treated effluent/stack emission"
                ]
            )
        )

    # 3. Factory License & Plan Approval (Factories Act, 1948)
    if req.workforce_count >= 10:
        permits.append(
            PermitItem(
                id="DISH_FACTORY_LICENSE",
                name="Factory License & Structural Plan Approval",
                authority="Directorate of Industrial Safety & Health (DISH)",
                category="Mandatory Pre-Construction",
                mandatory=True,
                lead_time_days=40,
                estimated_fee_inr=15000.0,
                description="Statutory license under Section 6 & 7 of the Factories Act, 1948 for manufacturing facilities employing 10+ workers using electrical power.",
                documents_required=[
                    "Form 1 factory building plans in triplicate prepared by chartered structural engineer",
                    "Emergency evacuation exits and natural ventilation layout",
                    "List of manufacturing machinery with horse-power (HP) ratings",
                    "Occupational health and safety welfare amenities plan (crèche, canteen, toilets)"
                ]
            )
        )

    # 4. Fire Safety NOC
    if req.built_up_area_sqft >= 5000 or category in ["Red", "Orange"] or req.has_chemical_treatment:
        permits.append(
            PermitItem(
                id="FIRE_SAFETY_NOC",
                name="Fire Safety No Objection Certificate (Fire NOC)",
                authority="State Fire and Emergency Services",
                category="Pre-Commissioning",
                mandatory=True,
                lead_time_days=30,
                estimated_fee_inr=12000.0,
                description="Fire safety clearance verifying compliance with National Building Code (NBC) 2016 Part 4 for industrial buildings.",
                documents_required=[
                    "Fire hydrant system schematic and water tank capacity drawing (min 50,000 L)",
                    "Locations of ABC/CO2 fire extinguishers and smoke detection alarms",
                    "Building completion certificate from local municipal planning authority",
                    "Fire clearance training certificate for workplace safety officers"
                ]
            )
        )

    # 5. Hazardous Waste Authorization (Rule 6)
    if category == "Red" or req.has_chemical_treatment or etp_mandatory:
        permits.append(
            PermitItem(
                id="HAZARDOUS_WASTE_AUTH",
                name="Hazardous Waste Authorization (Form 1 / Rule 6)",
                authority=spcb_name,
                category="Operational",
                mandatory=True,
                lead_time_days=35,
                estimated_fee_inr=15000.0,
                description="Mandatory authorization under Hazardous and Other Wastes (Management & Transboundary Movement) Rules, 2016 for storing or disposing chemical sludge, e-waste, or paint residue.",
                documents_required=[
                    "Membership agreement with an authorized Common Hazardous Waste TSDF facility",
                    "Specification of hazardous waste storage shed with impervious concrete flooring",
                    "Emergency response and spill management SOPs"
                ]
            )
        )

    # 6. Steam Boiler Registration
    if req.has_steam_boiler:
        permits.append(
            PermitItem(
                id="BOILER_CLEARANCE",
                name="Boiler Registration & Hydraulic Inspection",
                authority="Directorate of Steam Boilers",
                category="Pre-Commissioning",
                mandatory=True,
                lead_time_days=25,
                estimated_fee_inr=18000.0,
                description="Mandatory inspection and hydraulic pressure safety testing under the Indian Boilers Act, 1923.",
                documents_required=[
                    "Boiler manufacturer test certificate (Form II & III)",
                    "Steam pipeline fabrication blueprint by certified boiler maker",
                    "Qualified IBR certified boiler attendant appointment letter"
                ]
            )
        )

    # 7. CGWA Groundwater Extraction NOC
    permits.append(
        PermitItem(
            id="CGWA_GROUNDWATER_NOC",
            name="Groundwater Extraction NOC (CGWA)",
            authority="Central Ground Water Authority / State Ground Water Authority",
            category="Operational",
            mandatory=False,
            lead_time_days=45,
            estimated_fee_inr=10000.0,
            description="Applicable if factory operates private borewells or tube-wells for industrial water supply.",
            documents_required=[
                "Hydro-geological assessment report",
                "Rainwater harvesting and artificial groundwater recharge plan",
                "Tamper-proof telemetric digital flow meter calibration certificate"
            ]
        )
    )

    return permits


def compute_carbon_and_solar(
    req: ComplianceAssessmentRequest,
    power_kwh: float,
    diesel_liters: float,
    built_up_sqft: float,
    production_units: int
) -> Tuple[CarbonMetrics, SolarProjection]:
    # Scope 1 (Direct Fuel): Diesel emits ~2.68 kg CO2e per liter
    scope_1_kg = diesel_liters * 2.68

    # Scope 2 (Grid Electricity): India CEA Grid Emission Factor is ~0.716 kg CO2e per kWh
    scope_2_kg = power_kwh * 0.716

    monthly_total_kg = scope_1_kg + scope_2_kg
    total_annual_tons = round((monthly_total_kg * 12.0) / 1000.0, 2)
    emissions_per_unit = round(monthly_total_kg / max(production_units, 1), 3)

    carbon_metrics = CarbonMetrics(
        scope_1_kg_co2_monthly=round(scope_1_kg, 1),
        scope_2_kg_co2_monthly=round(scope_2_kg, 1),
        total_carbon_tons_annual=total_annual_tons,
        emissions_per_unit_kg=emissions_per_unit,
        scope_1_breakdown=f"{diesel_liters} L/mo diesel backup @ 2.68 kg CO2e/L",
        scope_2_breakdown=f"{power_kwh} kWh/mo state grid @ 0.716 kg CO2e/kWh (CEA India Factor)"
    )

    # Solar Rooftop ROI
    # 70% of built-up area is shadow-free usable roof space; 80 sq.ft per kWp
    usable_roof_sqft = round(built_up_sqft * 0.70, 1)
    max_roof_capacity_kwp = round(usable_roof_sqft / 80.0, 1)

    # Annual generation in India: ~1,450 kWh per kWp installed
    annual_power_demand_kwh = power_kwh * 12.0
    consumption_cap_kwp = round(annual_power_demand_kwh / 1450.0, 1)

    # Optimal recommendation: fulfill up to 100% of demand or max roof space
    recommended_kwp = round(min(max_roof_capacity_kwp, max(consumption_cap_kwp, 5.0)), 1)
    capex_inr = round(recommended_kwp * 48000.0)  # Standard ~₹48,000/kWp turnkey
    annual_gen_kwh = round(recommended_kwp * 1450.0)
    annual_savings_inr = round(annual_gen_kwh * 9.0)  # Commercial tariff ₹9.0/kWh
    payback_years = round(capex_inr / max(annual_savings_inr, 1), 1)
    annual_carbon_offset_tons = round((annual_gen_kwh * 0.716) / 1000.0, 2)
    lifetime_25yr_savings_inr = round((annual_savings_inr * 25) - capex_inr)

    solar_projection = SolarProjection(
        recommended_capacity_kwp=recommended_kwp,
        estimated_capex_inr=capex_inr,
        annual_generation_kwh=annual_gen_kwh,
        annual_savings_inr=annual_savings_inr,
        payback_period_years=payback_years,
        annual_carbon_offset_tons=annual_carbon_offset_tons,
        lifetime_25yr_savings_inr=lifetime_25yr_savings_inr,
        usable_roof_area_sqft=usable_roof_sqft
    )

    return carbon_metrics, solar_projection


def read_sector_markdown(relative_path: str) -> Optional[str]:
    kb_dir = get_compliance_data_dir()
    full_path = os.path.join(kb_dir, relative_path)
    if os.path.exists(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Strip YAML frontmatter for rendering
            content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL)
            return content.strip()
        except Exception as e:
            print(f"[COMPLIANCE] Error reading sector markdown at {full_path}: {e}")
    return None


def run_compliance_assessment(req: ComplianceAssessmentRequest) -> ComplianceAssessmentResponse:
    matched_data, match_rationale = find_best_matching_sector(req)

    category = matched_data.get("category", "Green")
    pi_score = float(matched_data.get("pollution_index_score", 30.0))
    etp_mandatory = matched_data.get("etp_apcd_mandatory", False)

    # Category override if dangerous chemicals are added
    if req.has_chemical_treatment and category in ["White", "Green"]:
        category = "Red"
        pi_score = max(pi_score, 82.0)
        match_rationale += " [Overridden to Red Category due to chemical/acid surface treatment]."

    sector_summary = SectorSummary(
        slug=matched_data.get("slug", "sector"),
        title=matched_data.get("title", "Sector"),
        category=category,
        pollution_index_score=pi_score,
        pollution_index_range=matched_data.get("pollution_index_range", ""),
        cpcb_serial_no=matched_data.get("cpcb_serial_no", ""),
        requires_cte=matched_data.get("requires_cte", True) if category != "White" else False,
        requires_cto=matched_data.get("requires_cto", True) if category != "White" else False,
        validity_period=matched_data.get("validity_period", "5 Years"),
        etp_apcd_mandatory=etp_mandatory,
        tags=[str(t) for t in matched_data.get("tags", [])],
    )

    permits = generate_statutory_permits(req, category, etp_mandatory)
    carbon_metrics, solar_proj = compute_carbon_and_solar(
        req,
        power_kwh=req.monthly_power_kwh,
        diesel_liters=req.monthly_diesel_liters,
        built_up_sqft=req.built_up_area_sqft,
        production_units=req.monthly_production_units
    )

    star_rating_eligible = category in ["Red", "Orange", "Green"]

    roadmap = [
        f"1. Pre-Construction: File online Consent to Establish (CTE) on {req.state} SPCB OCMMS portal before site grading.",
        f"2. Factory Architecture: Submit floor blueprints to DISH for Factory License approval ({req.workforce_count} workers).",
        "3. Life Safety: Install NBC-compliant fire water lines and fire extinguishers to clear Fire Safety NOC inspection.",
        f"4. Renewable Energy: Deploy {solar_proj.recommended_capacity_kwp} kWp rooftop solar to offset ~{solar_proj.annual_carbon_offset_tons} tons CO2e and slash power OPEX.",
        "5. Pre-Commissioning: Complete physical trial runs and obtain Consent to Operate (CTO) before issuing the first commercial invoice."
    ]

    rel_path = matched_data.get("relative_path", "")
    markdown_content = read_sector_markdown(rel_path) if rel_path else None

    return ComplianceAssessmentResponse(
        matched_sector=sector_summary,
        spcb_category=category,
        pollution_index_score=pi_score,
        category_rationale=match_rationale,
        star_rating_eligible=star_rating_eligible,
        required_permits=permits,
        carbon_metrics=carbon_metrics,
        solar_projection=solar_proj,
        compliance_roadmap=roadmap,
        sector_guidelines_markdown=markdown_content
    )


def ai_parse_and_assess_compliance(query: str) -> ComplianceAssessmentResponse:
    """
    Parses a founder's natural language description of a factory,
    extracts operational parameters via LLM or heuristics,
    matches against 419 official CPCB sectors, and runs the full compliance assessment.
    """
    prompt = (query or "").strip()
    if not prompt:
        prompt = "General assembly and fabrication unit in Maharashtra"

    extracted: Optional[Dict[str, Any]] = None

    def _extract_json_dict(raw_content: Any) -> Optional[Dict[str, Any]]:
        if not raw_content:
            return None
        text = str(raw_content).strip()
        if not text:
            return None
        # 1. Look for ```json { ... } ``` or ``` { ... } ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1).strip())
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        # 2. Look for outermost { ... }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1].strip())
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        # 3. Direct JSON parse
        try:
            clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
            data = json.loads(clean)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    sys_prompt = (
        "You are an expert Indian industrial legal, environmental, and compliance analyzer. "
        "Analyze the founder's factory query and respond with ONLY a pure JSON object (no markdown backticks, no text before or after) with these keys:\n"
        "{\n"
        '  "industry_text": "short core manufacturing activity",\n'
        '  "state": "Indian state name if mentioned, otherwise Maharashtra",\n'
        '  "monthly_power_kwh": float,\n'
        '  "monthly_diesel_liters": float,\n'
        '  "workforce_count": int,\n'
        '  "built_up_area_sqft": float,\n'
        '  "monthly_production_units": int,\n'
        '  "has_chemical_treatment": bool,\n'
        '  "has_effluent_discharge": bool,\n'
        '  "has_steam_boiler": bool\n'
        "}"
    )

    # 1. Attempt Primary Default LLM
    try:
        from models.llm import get_default_LLM
        llm = get_default_LLM(temperature=0.1, max_tokens=600)
        resp = llm.invoke(f"{sys_prompt}\n\nFounder Query: {prompt}")
        raw = resp.content if hasattr(resp, "content") else str(resp)
        extracted = _extract_json_dict(raw)
        if extracted:
            print(f"[COMPLIANCE AI] Successfully extracted parameters via default LLM.")
    except Exception as err:
        print(f"[COMPLIANCE AI] Default LLM extraction failed: {err}. Trying fallback...")
        extracted = None

    # 2. Attempt Fallback LLM if primary failed
    if not extracted:
        try:
            from models.llm import get_fallback_llm
            fallback_llm = get_fallback_llm(temperature=0.1, max_tokens=600)
            resp = fallback_llm.invoke(f"{sys_prompt}\n\nFounder Query: {prompt}")
            raw = resp.content if hasattr(resp, "content") else str(resp)
            extracted = _extract_json_dict(raw)
            if extracted:
                print(f"[COMPLIANCE AI] Successfully extracted parameters via fallback LLM.")
        except Exception as err2:
            print(f"[COMPLIANCE AI] Fallback LLM also failed: {err2}.")
            extracted = None

    # 2. Heuristic extraction fallback
    if not extracted or not isinstance(extracted, dict):
        states = [
            "Maharashtra", "Gujarat", "Tamil Nadu", "Karnataka", "Telangana",
            "Uttar Pradesh", "Rajasthan", "Haryana", "Madhya Pradesh", "Andhra Pradesh",
            "Punjab", "West Bengal", "Kerala", "Odisha", "Delhi NCR"
        ]
        matched_state = "Maharashtra"
        for s in states:
            if s.lower() in prompt.lower():
                matched_state = s
                break

        workers = 25
        m_w = re.search(r"(\d+)\s*(?:workers?|employees?|people|labou?rs?|staff)", prompt, re.I)
        if m_w:
            workers = int(m_w.group(1))

        area = 15000.0
        m_a = re.search(r"(\d+(?:,\d+)?)\s*(?:sq\.?\s*ft|sqft|square\s*feet|sq\s*meters?)", prompt, re.I)
        if m_a:
            area = float(m_a.group(1).replace(",", ""))

        units = 1000
        m_u = re.search(r"(\d+(?:,\d+)?)\s*(?:units?|pieces?|capacity|packs?|items?)", prompt, re.I)
        if m_u:
            units = int(m_u.group(1).replace(",", ""))

        power = 8500.0
        m_p = re.search(r"(\d+(?:,\d+)?)\s*(?:kwh|units\s*power|kw)", prompt, re.I)
        if m_p:
            power = float(m_p.group(1).replace(",", ""))

        extracted = {
            "industry_text": prompt,
            "state": matched_state,
            "monthly_power_kwh": power,
            "monthly_diesel_liters": 250.0,
            "workforce_count": workers,
            "built_up_area_sqft": area,
            "monthly_production_units": units,
            "has_chemical_treatment": any(k in prompt.lower() for k in ["chemical", "plating", "electroplating", "acid", "toxic", "wash", "anodiz"]),
            "has_effluent_discharge": any(k in prompt.lower() for k in ["effluent", "discharge", "liquid waste", "drain", "water wash"]),
            "has_steam_boiler": any(k in prompt.lower() for k in ["boiler", "steam", "furnace", "combustion", "heat treatment"]),
        }

    # 3. Construct ComplianceAssessmentRequest
    req = ComplianceAssessmentRequest(
        custom_industry_text=str(extracted.get("industry_text") or prompt),
        state=str(extracted.get("state") or "Maharashtra"),
        monthly_power_kwh=float(extracted.get("monthly_power_kwh") or 8500.0),
        monthly_diesel_liters=float(extracted.get("monthly_diesel_liters") or 250.0),
        workforce_count=int(extracted.get("workforce_count") or 25),
        built_up_area_sqft=float(extracted.get("built_up_area_sqft") or 15000.0),
        monthly_production_units=int(extracted.get("monthly_production_units") or 1000),
        has_chemical_treatment=bool(extracted.get("has_chemical_treatment", False)),
        has_effluent_discharge=bool(extracted.get("has_effluent_discharge", False)),
        has_steam_boiler=bool(extracted.get("has_steam_boiler", False)),
    )

    return run_compliance_assessment(req)
