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
    SectorSummary,
    VerifiedSource,
    NonComplianceRiskItem
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
    raw_words = [w for w in re.split(r"\W+", search_text) if len(w) > 2]

    stop_words = {
        "and", "with", "for", "from", "without", "area", "sqft", "workers", "facility",
        "unit", "plant", "only", "any", "feet", "employees", "setting", "want", "start",
        "dry", "process", "operation", "operations", "making", "manufacturing", "industry",
        "effluent", "discharge", "waste", "haridwar", "pune", "mumbai", "delhi", "bangalore"
    }
    generic_words = {"packaging", "packing", "storage", "terminal", "blending", "assembly", "fabrication"}

    synonyms = {
        "herbal": ["ayurvedic", "medicines", "pharmaceutical"],
        "ayurveda": ["ayurvedic", "medicines", "pharmaceutical"],
        "ayurvedic": ["ayurvedic", "medicines", "pharmaceutical"],
        "pharma": ["pharmaceutical", "medicines", "formulation"],
        "pharmaceutical": ["pharmaceutical", "medicines", "formulation"],
        "formulation": ["formulation", "pharmaceuticals", "medicines"],
        "solar": ["solar", "photovoltaic", "non-conventional"],
        "battery": ["battery", "accumulator", "cell"],
        "lithium": ["battery", "excluding", "non-lead"],
        "pack": ["assembling", "assembly"],
        "ev": ["automobile", "battery", "electric vehicle"],
        "plastic": ["plastic", "polythene", "injection molding"],
        "cnc": ["engineering", "machining", "fabrication"],
        "gear": ["engineering", "machining", "automobile"],
    }

    core_words = [w for w in raw_words if w not in stop_words]
    if not core_words:
        core_words = raw_words

    expanded_words = list(core_words)
    for w in core_words:
        if w in synonyms:
            expanded_words.extend(synonyms[w])

    is_lithium = any(k in search_text for k in ["lithium", "li-ion", "li ion", "lfp", "nmc"])
    has_explicit_lead = "lead" in search_text and not is_lithium

    best_match = None
    best_score = 0

    for slug, item in sectors.items():
        title_lower = str(item.get("title", "")).lower()
        tags_lower = [str(t).lower() for t in item.get("tags", [])]

        is_excluding_lead = "excluding lead" in title_lower or "excluding lead-acid" in title_lower
        has_lead_mfg = (
            "lead-acid" in title_lower
            or "lead acid" in title_lower
            or "acid lead" in title_lower
            or "lead-acid" in slug
        ) and not is_excluding_lead

        # Prevent false-positive lead-acid matching for modern Lithium-ion batteries
        if is_lithium and not has_explicit_lead and has_lead_mfg:
            continue

        score = 0
        for word in expanded_words:
            weight = 1 if word in generic_words else 5
            if word in slug:
                score += 3 * weight
            if word in title_lower:
                score += 4 * weight
            if word in tags_lower:
                score += 2 * weight
            if re.search(r"\b" + re.escape(word) + r"\b", title_lower):
                score += 5 * weight

        # Bonus for official non-lead acid CPCB sector
        if is_lithium and is_excluding_lead:
            score += 300

        if score > best_score:
            best_score = score
            best_match = item

    if best_match and best_score >= 10:
        return best_match, f"Best match for query '{search_text}' with confidence score {best_score}."

    # 3. Default fallback
    if is_lithium:
        fallback_slug = "battery-manufacturing-without-boiler-excluding-lead-acid-battery"
    elif "battery" in search_text or "chemical" in search_text:
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


def generate_legal_risk_matrix(
    category: str,
    state: str,
    matched_title: str,
    requires_cte: bool,
    requires_cto: bool,
    workforce_count: int = 25,
    has_effluent: bool = False
) -> List[NonComplianceRiskItem]:
    spcb_name = f"{state} Pollution Control Board" if "Delhi" not in state else "Delhi Pollution Control Committee (DPCC)"
    matched_lower = matched_title.lower()

    # Determine EPR specific regulation
    if "battery" in matched_lower:
        epr_violation = "Operating without Central CPCB EPR Registration & Default on Battery Waste Collection Quotas"
        epr_statute = "Battery Waste Management Rules, 2022 (Rule 13, 14 & 24) under Environment (Protection) Act, 1986"
        epr_penalty = "Revocation of CPCB producer registration; mandatory Environmental Compensation (EC) on each uncollected kg/MT of battery scrap; personal prosecution notice to founders."
        epr_impact = "Immediate blacklisting on CPCB portal; customs holding of imported lithium cells/components; bar on commercial sales invoices."
        epr_fine = "INR 10,000 to INR 25,000 per MT of shortfall in fulfillment of minimum collection/recycling targets; compounding annually."
        epr_sev = "HIGH"
    elif any(k in matched_lower for k in ["plastic", "polythene", "packaging", "moulding", "bottle"]):
        epr_violation = "Commercial Plastic Processing / Packaging without CPCB EPR Registration & Mandatory Recycled Content"
        epr_statute = "Plastic Waste Management Rules, 2022 (PWM Rules) & Environment (Protection) Act, 1986"
        epr_penalty = "Prosecution under Section 15 of EP Act; retrospective Environmental Compensation levied on non-recycled plastic throughput."
        epr_impact = "Revocation of SPCB Consent to Operate (CTO); seizure of plastic raw material granules; disconnection of commercial electricity."
        epr_fine = "INR 5,000 to INR 10,000 per tonne of unregistered plastic processed, plus forfeiture of bank guarantees."
        epr_sev = "HIGH"
    elif any(k in matched_lower for k in ["electronic", "electrical", "pcb", "e-waste"]):
        epr_violation = "Non-Fulfillment of Extended Producer Responsibility (EPR) & Failure to Tie Up with Authorized Recyclers"
        epr_statute = "E-Waste (Management) Rules, 2022 & Environment (Protection) Act, 1986"
        epr_penalty = "De-registration of EPR Certificate; seizure of finished inventory; penalty proceedings before National Green Tribunal (NGT)."
        epr_impact = "Inability to sell products on e-commerce platforms (Amazon/Flipkart) and rejection of government GEM portal tenders."
        epr_fine = "INR 5,000 to INR 20,000 per MT shortfall in recycling target + prosecution of designated directors."
        epr_sev = "HIGH"
    elif category == "Red" or has_effluent:
        epr_violation = "Illegal Storage, Handling, or Disposal of Industrial Hazardous Waste / ETP Sludge without TSDF Tie-up"
        epr_statute = "Hazardous and Other Wastes (Management & Transboundary Movement) Rules, 2016 (Rule 6, 23 & 24)"
        epr_penalty = "Criminal prosecution under Section 15 Environment (Protection) Act; immediate SPCB closure orders."
        epr_impact = "Immediate shutdown of chemical production lines; sealing of hazardous waste storage sheds; cancellation of CTO."
        epr_fine = "INR 1,00,000 to INR 25,00,000+ calculated via CPCB Hazardous Waste Environmental Compensation formula."
        epr_sev = "CRITICAL"
    else:
        epr_violation = "Improper Industrial Solid & Hazardous Waste Manifest Maintenance (Form 10)"
        epr_statute = "Hazardous and Other Wastes Rules, 2016 & Solid Waste Management Rules, 2016"
        epr_penalty = "Issue of Show Cause Notice under Rule 6; potential downgrade of factory green categorization."
        epr_impact = "Revocation of simplified compliance status; surprise site inspections by SPCB environmental vigilance officers."
        epr_fine = "INR 25,000 to INR 1,00,000 compounding per inspection default."
        epr_sev = "MEDIUM"

    matrix: List[NonComplianceRiskItem] = [
        # 1. CTE violation
        NonComplianceRiskItem(
            violation="Breaking Ground / Factory Construction without Prior Consent to Establish (CTE)",
            statutory_act=f"Water Act 1974 (Sec 25/44) & Air Act 1981 (Sec 21/37) [{spcb_name}]",
            penal_provision="Cognizable criminal offense: Imprisonment from 1.5 to 6 years for Directors/Occupier plus continuous daily fine if civil work commences before CTE issuance.",
            financial_liability="INR 10,000 to INR 1,00,000 per day Environmental Compensation (EC) levied retrospectively under NGT/CPCB formula (EC = PI x N x R x S x LF).",
            operational_impact="Immediate Stop-Work order; industrial site sealed by District Magistrate; forfeiture of industrial development rights and loss of state industrial subsidies.",
            severity="CRITICAL" if category != "White" else "LOW",
        ),
        # 2. Section 33A / 31A Power (CTO violation)
        NonComplianceRiskItem(
            violation="Operating Plant / Commercial Production without Valid Consent to Operate (CTO)",
            statutory_act=f"Section 33A (Water Act 1974) & Section 31A (Air Act 1981) - Summary Powers of {spcb_name}",
            penal_provision="Summary Closure Order without prior trial court summons. Statutory directions issued directly to power DISCOM and water boards under Sec 33A/31A.",
            financial_liability="Retroactive penal consent fee (3x to 5x standard tariff), freezing of factory bank accounts, and daily damages up to INR 10,000/day from commercial startup.",
            operational_impact="Factory 3-phase electricity disconnected by DISCOM & municipal water supply cut within 48-72 hours; factory gates locked; invalidation of GST e-way bills.",
            severity="CRITICAL" if category != "White" else "LOW",
        ),
        # 3. Factories Act 1948 Sec 92
        NonComplianceRiskItem(
            violation="Occupying Shed & Deploying Workforce without Approved Blueprints & DISH Factory License",
            statutory_act=f"Factories Act, 1948 (Section 6, 7 & 92) / State Directorate of Industrial Safety & Health (DISH)",
            penal_provision="Criminal complaint filed against Occupier/Managing Director in Chief Judicial Magistrate (CJM) court; imprisonment up to 2 years.",
            financial_liability="Fine up to INR 1,00,000 per violation; INR 1,000/day continuing fine. Personal bail bonds required from designated Directors.",
            operational_impact="Factory closure notice; complete repudiation of Group Accidental / Workmen Compensation Insurance coverage in the event of an industrial incident.",
            severity="HIGH" if workforce_count >= 10 else "MEDIUM",
        ),
        # 4. Fire Safety NOC
        NonComplianceRiskItem(
            violation="Factory Operation without Fire Safety No Objection Certificate (Fire NOC)",
            statutory_act=f"{state} Fire Prevention and Life Safety Measures Act & NBC 2016 (Part 4 Industrial Occupancy)",
            penal_provision="Physical sealing of premises under Municipal Fire Act; personal criminal liability under IPC Section 304A (culpable homicide) during fires.",
            financial_liability="100% loss repudiation: Immediate cancellation and rejection of all industrial property, inventory, and plant & machinery insurance claims by underwriters.",
            operational_impact="Immediate suspension of Municipal Trade License; physical padlocking of factory premises until full fire hydrant, riser, and alarm installation clears inspection.",
            severity="HIGH",
        ),
        # 5. EPR / Waste Rules
        NonComplianceRiskItem(
            violation=epr_violation,
            statutory_act=epr_statute,
            penal_provision=epr_penalty,
            financial_liability=epr_fine,
            operational_impact=epr_impact,
            severity=epr_sev,
        ),
        # 6. Groundwater Extraction NOC
        NonComplianceRiskItem(
            violation="Drawing Borewell / Tube-well Groundwater without Central Ground Water Authority (CGWA) NOC",
            statutory_act="Environment (Protection) Act, 1986 (Section 15) & Central Ground Water Authority (CGWA) Public Guidelines",
            penal_provision="Physical sealing of borewells, confiscation of submersible pumping equipment, and lodging of FIR against factory plant management.",
            financial_liability="Groundwater Environmental Compensation (EC) ranging from INR 1,00,000 to INR 20,00,000+ depending on extraction volume (m3/day) and block water stress level.",
            operational_impact="Total disruption of wet processes, cooling towers, and employee sanitation amenities; compulsory switch to costly licensed external water tankers.",
            severity="HIGH" if (category == "Red" or has_effluent) else "MEDIUM",
        ),
    ]

    return matrix


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


def verify_assessment_with_web_search(
    query: str,
    matched_title: str,
    category: str,
    state: str,
) -> Tuple[Optional[str], List[VerifiedSource]]:
    """
    Performs live web search on CPCB/SPCB regulatory databases and invokes Groq LLM
    to cross-examine, verify statutory permits, and return live regulatory insights with source citations.
    """
    print(f"[COMPLIANCE VERIFIER] Starting live web search for: '{matched_title}' in {state}...", flush=True)
    search_hits = []
    try:
        from agents.tools.research_tools import ddg_search
        search_query = f"CPCB {matched_title} {state} pollution control board guidelines CTE CTO {category} category"
        search_hits = ddg_search(search_query, max_results=3)
        if not search_hits:
            # Fallback broader query
            search_query_fallback = f"CPCB {matched_title} pollution category guidelines"
            search_hits = ddg_search(search_query_fallback, max_results=3)
    except Exception as search_err:
        print(f"[COMPLIANCE VERIFIER] Search tool error: {search_err}", flush=True)
        search_hits = []

    verified_sources: List[VerifiedSource] = []
    search_context_lines = []
    for h in search_hits:
        title = str(h.get("title", "")).strip()
        url = str(h.get("url", "")).strip()
        snippet = str(h.get("snippet", "")).strip()
        if title and url:
            verified_sources.append(VerifiedSource(title=title, url=url, snippet=snippet))
            search_context_lines.append(f"- Source: {title} ({url})\n  Snippet: {snippet}")

    search_context = "\n".join(search_context_lines) if search_context_lines else "No direct live web results returned."

    # Groq LLM verification
    verification_text: Optional[str] = None
    try:
        from models.llm import get_groq_llm
        llm = get_groq_llm(model_name="openai/gpt-oss-20b", temperature=0.1, max_tokens=1000)

        verify_prompt = (
            f"You are an expert Indian industrial legal, environmental, and statutory compliance verifier.\n"
            f"Cross-examine the following factory assessment against live web search findings and official CPCB/SPCB rules:\n\n"
            f"Founder Factory Plan: \"{query}\"\n"
            f"Matched Sector: \"{matched_title}\"\n"
            f"Assigned CPCB Category: {category} Category\n"
            f"Location: {state}, India\n\n"
            f"Live Web Search Findings:\n"
            f"{search_context}\n\n"
            f"Provide a concise, professional 3-point statutory verification report:\n"
            f"1. Category & Environmental Law: Confirm CPCB/SPCB categorization under the Water Act 1974 & Air Act 1981.\n"
            f"2. Mandatory Portal & Clearances: Specify the online single-window clearance portal for {state} (e.g. OCMMS) and mandatory CTE/CTO/DISH requirements.\n"
            f"3. Live Safeguards & Waste Management: Highlight critical environmental safeguards (e.g., Battery/Plastic EPR Rules 2022, Fire NOC, or ETP/ZLD norms).\n"
            f"Format as crisp bullet points. Be direct, authoritative, and concise."
        )

        resp = llm.invoke(verify_prompt)
        verification_text = resp.content if hasattr(resp, "content") else str(resp)
        print(f"[COMPLIANCE VERIFIER] Successfully generated live regulatory verification.", flush=True)
    except Exception as llm_err:
        print(f"[COMPLIANCE VERIFIER] Groq verification LLM error: {llm_err}", flush=True)
        verification_text = (
            f"- CPCB Harmonized Category: Classified as {category} Category under CPCB 2025 guidelines.\n"
            f"- State Clearance Portal: Applications for Consent to Establish (CTE) and Consent to Operate (CTO) must be filed through the {state} SPCB OCMMS portal.\n"
            f"- Statutory Compliance: Unit must comply with the Water Act 1974, Air Act 1981, and relevant waste management rules (Hazardous/Battery/E-Waste)."
        )

    return verification_text, verified_sources


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

    # Live Web Search Regulatory Verification
    regulatory_verification, verified_sources = verify_assessment_with_web_search(
        query=req.custom_industry_text or matched_data.get("title", "Sector"),
        matched_title=matched_data.get("title", "Sector"),
        category=category,
        state=req.state,
    )

    # Statutory Non-Compliance & Legal Risk Matrix
    legal_risks = generate_legal_risk_matrix(
        category=category,
        state=req.state,
        matched_title=matched_data.get("title", "Sector"),
        requires_cte=matched_data.get("requires_cte", True) if category != "White" else False,
        requires_cto=matched_data.get("requires_cto", True) if category != "White" else False,
        workforce_count=req.workforce_count,
        has_effluent=req.has_effluent_discharge
    )

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
        sector_guidelines_markdown=markdown_content,
        regulatory_verification=regulatory_verification,
        verified_sources=verified_sources,
        legal_risk_matrix=legal_risks,
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

    print("\n" + "=" * 75, flush=True)
    print(f"[COMPLIANCE ENGINE] >>> INCOMING QUERY RECEIVED:", flush=True)
    print(f"\"{prompt}\"", flush=True)
    print("=" * 75, flush=True)

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

        # 4. Truncated JSON auto-repair (if missing closing brace)
        if "{" in text:
            start_pos = text.find("{")
            partial = text[start_pos:].strip()
            if not partial.endswith("}"):
                for suffix in ["}", '"}', '": false}', '": true}', '": 0}']:
                    try:
                        data = json.loads(partial + suffix)
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
        '  "has_chemical_treatment": false (true ONLY if process performs chemical surface treatment like acid baths, electroplating, anodizing or chemical synthesis; false for dry mechanical assembly, battery pack assembly, electronics assembly),\n'
        '  "has_effluent_discharge": false (true ONLY if industrial trade effluent is discharged from process; false for dry mechanical assembly, electronics, or battery pack assembly),\n'
        '  "has_steam_boiler": false (true ONLY if plant operates high-pressure steam boiler)\n'
        "}"
    )

    # 1. Attempt Primary Groq LLM
    try:
        from models.llm import get_groq_llm
        llm = get_groq_llm(model_name="openai/gpt-oss-20b", temperature=0.1, max_tokens=1500)
        resp = llm.invoke(f"{sys_prompt}\n\nFounder Query: {prompt}")
        raw = resp.content if hasattr(resp, "content") else str(resp)
        extracted = _extract_json_dict(raw)
        if extracted:
            print(f"[COMPLIANCE AI] Successfully extracted parameters via Groq LLM.")
    except Exception as err:
        print(f"[COMPLIANCE AI] Primary Groq LLM extraction failed: {err}. Trying fallback...")
        extracted = None

    # 2. Attempt Fallback LLM if primary failed
    if not extracted:
        try:
            from models.llm import get_fallback_llm
            fallback_llm = get_fallback_llm(exclude_provider="groq", temperature=0.1, max_tokens=1500)
            resp = fallback_llm.invoke(f"{sys_prompt}\n\nFounder Query: {prompt}")
            raw = resp.content if hasattr(resp, "content") else str(resp)
            extracted = _extract_json_dict(raw)
            if extracted:
                print(f"[COMPLIANCE AI] Successfully extracted parameters via fallback LLM.")
        except Exception as err2:
            print(f"[COMPLIANCE AI] Fallback LLM also failed: {err2}.")
            extracted = None

    # 3. Heuristic extraction fallback
    if not extracted or not isinstance(extracted, dict):
        states = [
            "Uttarakhand", "Himachal Pradesh", "Maharashtra", "Gujarat", "Tamil Nadu",
            "Karnataka", "Telangana", "Uttar Pradesh", "Rajasthan", "Haryana",
            "Madhya Pradesh", "Andhra Pradesh", "Punjab", "West Bengal", "Kerala",
            "Odisha", "Delhi NCR", "Assam", "Goa", "Jharkhand", "Chhattisgarh"
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

        has_chem = any(k in prompt.lower() for k in ["chemical", "plating", "electroplating", "acid", "toxic", "anodiz"])
        has_eff = any(k in prompt.lower() for k in ["effluent", "discharge", "liquid waste", "drain", "water wash"])
        if any(neg in prompt.lower() for neg in ["without effluent", "no effluent", "zero effluent", "zero liquid discharge", "zld", "dry process"]):
            has_eff = False

        has_boiler = any(k in prompt.lower() for k in ["boiler", "steam", "furnace", "combustion", "heat treatment"])

        extracted = {
            "industry_text": prompt,
            "state": matched_state,
            "monthly_power_kwh": power,
            "monthly_diesel_liters": 250.0,
            "workforce_count": workers,
            "built_up_area_sqft": area,
            "monthly_production_units": units,
            "has_chemical_treatment": has_chem,
            "has_effluent_discharge": has_eff,
            "has_steam_boiler": has_boiler,
        }

    print("-" * 75, flush=True)
    print(f"[COMPLIANCE ENGINE] EXTRACTED OPERATIONAL PARAMETERS:", flush=True)
    for k, v in extracted.items():
        print(f"  * {k:25}: {v}", flush=True)
    print("-" * 75, flush=True)

    # 3. Construct ComplianceAssessmentRequest
    full_industry = f"{extracted.get('industry_text', '')} {prompt}".strip() if extracted.get("industry_text") else prompt
    req = ComplianceAssessmentRequest(
        custom_industry_text=full_industry,
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

    assessment = run_compliance_assessment(req)

    print("=" * 75, flush=True)
    print(f"[COMPLIANCE ENGINE] <<< GENERATED ASSESSMENT OUTPUT:", flush=True)
    print(f"  * Matched CPCB Sector : {assessment.matched_sector.title} (Slug: {assessment.matched_sector.slug})", flush=True)
    print(f"  * SPCB Category       : {assessment.spcb_category} (Pollution Index: {assessment.pollution_index_score})", flush=True)
    print(f"  * Category Rationale  : {assessment.category_rationale}", flush=True)
    print(f"  * Star Rating Eligible: {assessment.star_rating_eligible}", flush=True)
    print(f"  * Statutory Permits ({len(assessment.required_permits)} items):", flush=True)
    for idx, p in enumerate(assessment.required_permits, 1):
        mand = "MANDATORY" if p.mandatory else "RECOMMENDED"
        print(f"    {idx}. [{mand}] {p.name} ({p.authority}) - {p.lead_time_days} days | INR {p.estimated_fee_inr:,.0f}", flush=True)
    if assessment.carbon_metrics:
        cm = assessment.carbon_metrics
        print(f"  * Carbon Footprint    : Annual {cm.total_carbon_tons_annual:,.2f} Tons CO2e (Monthly Scope 1: {cm.scope_1_kg_co2_monthly:,.1f} kg, Scope 2: {cm.scope_2_kg_co2_monthly:,.1f} kg)", flush=True)
    if assessment.solar_projection:
        sp = assessment.solar_projection
        print(f"  * Solar Projection    : {sp.recommended_capacity_kwp} kWp (Offset: {sp.annual_carbon_offset_tons:.1f} tons/yr, Savings: INR {sp.annual_savings_inr:,.0f}/yr, Payback: {sp.payback_period_years} yrs)", flush=True)
    print(f"  * Roadmap Steps ({len(assessment.compliance_roadmap)} phases):", flush=True)
    for step in assessment.compliance_roadmap:
        print(f"    - {step}", flush=True)
    if assessment.regulatory_verification:
        print("-" * 75, flush=True)
        print(f"[COMPLIANCE ENGINE] LIVE REGULATORY WEB VERIFICATION:", flush=True)
        clean_text = assessment.regulatory_verification.encode("ascii", "replace").decode("ascii")
        for line in clean_text.split("\n"):
            if line.strip():
                print(f"  {line}", flush=True)
    if assessment.verified_sources:
        print(f"  * Verified Citations & Portals ({len(assessment.verified_sources)}):", flush=True)
        for s in assessment.verified_sources:
            clean_title = s.title.encode("ascii", "replace").decode("ascii")
            print(f"    - {clean_title} -> {s.url}", flush=True)
    if assessment.legal_risk_matrix:
        print("-" * 75, flush=True)
        print(f"[COMPLIANCE ENGINE] STATUTORY NON-COMPLIANCE & LEGAL RISK MATRIX ({len(assessment.legal_risk_matrix)} Liabilities):", flush=True)
        for r in assessment.legal_risk_matrix:
            print(f"  * [{r.severity}] {r.violation}", flush=True)
            print(f"    - Act / Section : {r.statutory_act}", flush=True)
            print(f"    - Penal Powers  : {r.penal_provision}", flush=True)
            print(f"    - Financial Fine: {r.financial_liability}", flush=True)
            print(f"    - Disruption    : {r.operational_impact}", flush=True)
    print("=" * 75 + "\n", flush=True)

    return assessment
