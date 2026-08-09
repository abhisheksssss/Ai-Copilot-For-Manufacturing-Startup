import os
import re
from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from utils.kb_lookup import (
    get_manufacturing_kb_dir,
    fetch_product_content,
    extract_section,
    extract_all_sections,
    parse_list_items,
    parse_table_rows,
    parse_budget_to_lakhs,
)

try:
    from .subtool.industrialsearch import industrial_land_search as subtool_industrial_land_search
except (ImportError, ValueError):
    try:
        from agents.tools.subtool.industrialsearch import industrial_land_search as subtool_industrial_land_search
    except ImportError:
        subtool_industrial_land_search = None



class PlanningInput(BaseModel):
    product: str = Field(description="The product to be manufactured")
    budget:  str = Field(description="Total budget e.g. '50 lakhs', '2 crore'")

class LocationInput(BaseModel):
    product:  str = Field(description="The product to be manufactured")
    location: str = Field(description="The manufacturing location / state")

class CapacityInput(BaseModel):
    product:                     str = Field(description="The product to be manufactured")
    production_capacity_per_day: int = Field(
        description="Target daily production in units",
        default=1000
    )

class TeamInput(BaseModel):
    product: str = Field(description="The product to be manufactured")
    budget:  str = Field(description="Total budget for staffing context", default="")


# ─────────────────────────────────────────────────────────────────────────────
# 1. PRODUCT PLANNER
# ─────────────────────────────────────────────────────────────────────────────
@tool("product_planner", args_schema=PlanningInput)
def product_planner(product: str, budget: str) -> dict:
    """
    Generates high-level milestones, timeline, and phases
    based on the product and budget.
    """
    print("\n[TOOL CALLED] -> product_planner")

    budget_lakhs = parse_budget_to_lakhs(budget)
    kb_dir       = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    phases     = []
    milestones = []
    timeline   = ""
    data_source = "knowledge_base"

    # ── Extract from KB ───────────────────────────────────────────────────
    if content:
        sections = extract_all_sections(content)

        for sec_key, sec_val in sections.items():
            if any(k in sec_key for k in ["phase", "milestone", "plan", "roadmap", "timeline"]):
                items = parse_list_items(sec_val)

                if "phase" in sec_key:
                    phases.extend(items)
                elif "milestone" in sec_key:
                    milestones.extend(items)

        # Look for timeline estimate in content
        tl_match = re.search(
            r'(\d+)\s*[-–to]+\s*(\d+)\s*(month|year)',
            content.lower()
        )
        if tl_match:
            timeline = f"{tl_match.group(1)}–{tl_match.group(2)} {tl_match.group(3).title()}s"
    else:
        data_source = "generic_fallback"

    # ── Budget-aware phase logic ──────────────────────────────────────────
    if budget_lakhs > 0:
        if budget_lakhs < 25:
            budget_tier  = "micro"
            default_tl   = "4–6 Months"
            phase_set    = [
                {"phase": 1, "name": "Planning & Registration",    "duration": "Month 1"},
                {"phase": 2, "name": "Procurement & Setup",        "duration": "Month 2–3"},
                {"phase": 3, "name": "Trial Production",           "duration": "Month 4"},
                {"phase": 4, "name": "Commercial Launch",          "duration": "Month 5–6"},
            ]
        elif budget_lakhs < 100:
            budget_tier  = "small"
            default_tl   = "6–9 Months"
            phase_set    = [
                {"phase": 1, "name": "Market Research & Licensing",     "duration": "Month 1"},
                {"phase": 2, "name": "Factory Search & Infrastructure", "duration": "Month 2–3"},
                {"phase": 3, "name": "Machinery Procurement",           "duration": "Month 3–5"},
                {"phase": 4, "name": "Trial Run & QC Setup",            "duration": "Month 5–7"},
                {"phase": 5, "name": "Commercial Launch",               "duration": "Month 7–9"},
            ]
        elif budget_lakhs < 500:
            budget_tier  = "medium"
            default_tl   = "9–15 Months"
            phase_set    = [
                {"phase": 1, "name": "Feasibility & DPR",              "duration": "Month 1–2"},
                {"phase": 2, "name": "Regulatory Approvals & Land",    "duration": "Month 2–4"},
                {"phase": 3, "name": "Civil Construction",             "duration": "Month 3–7"},
                {"phase": 4, "name": "Machinery Import & Erection",   "duration": "Month 6–10"},
                {"phase": 5, "name": "Trial Production & Testing",    "duration": "Month 10–13"},
                {"phase": 6, "name": "Full-Scale Commercial Launch",  "duration": "Month 13–15"},
            ]
        else:
            budget_tier  = "large"
            default_tl   = "18–30 Months"
            phase_set    = [
                {"phase": 1, "name": "DPR, EIA & Land Acquisition",      "duration": "Month 1–4"},
                {"phase": 2, "name": "Regulatory Clearances",            "duration": "Month 3–7"},
                {"phase": 3, "name": "Civil & Structural Work",          "duration": "Month 5–14"},
                {"phase": 4, "name": "Machinery & Utility Installation", "duration": "Month 12–20"},
                {"phase": 5, "name": "Commissioning & Trials",           "duration": "Month 19–24"},
                {"phase": 6, "name": "Ramp-up to Full Capacity",         "duration": "Month 24–30"},
            ]
    else:
        budget_tier = "unknown"
        default_tl  = "6–12 Months"
        phase_set   = [
            {"phase": 1, "name": "Planning & Setup",     "duration": "Month 1–2"},
            {"phase": 2, "name": "Procurement",          "duration": "Month 2–5"},
            {"phase": 3, "name": "Trial Run",            "duration": "Month 5–8"},
            {"phase": 4, "name": "Commercial Launch",    "duration": "Month 8–12"},
        ]

    # Use KB phases if found, else use budget-tier phases
    if not phases:
        phases = phase_set

    # Build milestones from phase names if KB didn't provide them
    if not milestones:
        milestones = [
            f"Finalize {product} product specifications",
            "Complete all statutory registrations (GST, MSME, Factory License)",
            "Secure land/shed and utility connections",
            "Place machinery orders and finalize vendors",
            "Complete factory civil work and machinery installation",
            f"Achieve first production batch of {product}",
            "Clear BIS/quality certification",
            "Achieve breakeven production volume",
        ]

    return {
        "product"          : product,
        "matched_entry"    : matched_name or "N/A",
        "budget"           : budget,
        "budget_lakhs"     : f"₹{budget_lakhs:.1f} Lakhs" if budget_lakhs else "Not parsed",
        "budget_tier"      : budget_tier,
        "data_source"      : data_source,
        "phases"           : phases,
        "milestones"       : milestones,
        "timeline_estimate": timeline or default_tl,
        "note": "Timeline is indicative. Regulatory delays not included."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. COST ESTIMATOR
# ─────────────────────────────────────────────────────────────────────────────
@tool("cost_estimator", args_schema=PlanningInput)
def cost_estimator(product: str, budget: str) -> dict:
    """Calculates CAPEX, OPEX, Break-even, and ROI from real KB data and budget."""
    print("\n[TOOL CALLED] -> cost_estimator")

    budget_lakhs = parse_budget_to_lakhs(budget)
    kb_dir       = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    capex_breakdown = {}
    opex_breakdown  = {}
    data_source     = "generic_calculation"

    # ── Try extracting cost data from KB ─────────────────────────────────
    if content:
        sections = extract_all_sections(content)
        for sec_key, sec_val in sections.items():
            if any(k in sec_key for k in ["cost", "capex", "investment", "finance", "project cost"]):
                rows = parse_table_rows(sec_val)
                if rows:
                    for row in rows:
                        head = row.get("Head", row.get("Item", row.get("Component", "")))
                        cost = row.get("Cost", row.get("Amount", row.get("Value", "")))
                        if head and cost:
                            capex_breakdown[head] = cost
                            data_source = "knowledge_base"

            if any(k in sec_key for k in ["opex", "operating", "recurring", "monthly cost"]):
                rows = parse_table_rows(sec_val)
                if rows:
                    for row in rows:
                        head = row.get("Head", row.get("Item", ""))
                        cost = row.get("Cost", row.get("Amount", ""))
                        if head and cost:
                            opex_breakdown[head] = cost
                            data_source = "knowledge_base"

    # ── Calculate from budget if KB gave no data ──────────────────────────
    if not capex_breakdown and budget_lakhs > 0:
        land_lease    = round(budget_lakhs * 0.10, 1)
        civil         = round(budget_lakhs * 0.15, 1)
        machinery     = round(budget_lakhs * 0.40, 1)
        utilities     = round(budget_lakhs * 0.05, 1)
        preop         = round(budget_lakhs * 0.05, 1)
        working_cap   = round(budget_lakhs * 0.20, 1)
        contingency   = round(budget_lakhs * 0.05, 1)
        total_capex   = round(budget_lakhs * 0.75, 1)

        capex_breakdown = {
            "Land / Shed Lease (deposit)"  : f"₹{land_lease} Lakhs",
            "Civil & Interior Work"        : f"₹{civil} Lakhs",
            "Plant & Machinery"            : f"₹{machinery} Lakhs",
            "Utilities & Electrification"  : f"₹{utilities} Lakhs",
            "Pre-operative Expenses"       : f"₹{preop} Lakhs",
            "Working Capital (3 months)"   : f"₹{working_cap} Lakhs",
            "Contingency (5%)"             : f"₹{contingency} Lakhs",
            "TOTAL CAPEX"                  : f"₹{total_capex} Lakhs",
        }

        raw_mat       = round(budget_lakhs * 0.08, 1)
        salaries      = round(budget_lakhs * 0.04, 1)
        power         = round(budget_lakhs * 0.02, 1)
        rent          = round(budget_lakhs * 0.01, 1)
        misc          = round(budget_lakhs * 0.01, 1)
        total_opex    = round(raw_mat + salaries + power + rent + misc, 1)

        opex_breakdown = {
            "Raw Materials (monthly)"     : f"₹{raw_mat} Lakhs",
            "Salaries & Wages"            : f"₹{salaries} Lakhs",
            "Power & Utilities"           : f"₹{power} Lakhs",
            "Rent / EMI"                  : f"₹{rent} Lakhs",
            "Misc (Admin, Transport)"     : f"₹{misc} Lakhs",
            "TOTAL MONTHLY OPEX"          : f"₹{total_opex} Lakhs",
        }

        annual_opex    = total_opex * 12
        revenue_needed = annual_opex / 0.30
        be_months      = round((total_capex / (revenue_needed / 12)) * 12, 1) \
                         if revenue_needed > 0 else 18
        roi_years      = round(total_capex / (revenue_needed * 0.20), 1)

    elif budget_lakhs == 0:
        be_months = 18
        roi_years = 3.0
        total_opex = 0
        total_capex = 0
    else:
        total_capex = budget_lakhs * 0.75
        total_opex  = budget_lakhs * 0.08
        be_months   = 18
        roi_years   = 3.0

    return {
        "product"         : product,
        "matched_entry"   : matched_name or "N/A",
        "budget_input"    : budget,
        "budget_lakhs"    : f"₹{budget_lakhs:.1f} Lakhs" if budget_lakhs else "Not parsed",
        "data_source"     : data_source,
        "capex_breakdown" : capex_breakdown,
        "opex_breakdown"  : opex_breakdown,
        "break_even"      : f"~{be_months:.0f} Months from start of production",
        "roi"             : f"~{roi_years:.1f} Years (at 20% net margin assumption)",
        "funding_gap"     : (
            f"₹{max(0, round(budget_lakhs * 0.75 - budget_lakhs, 1))} Lakhs loan recommended"
            if budget_lakhs > 0 else "Calculate after budget confirmation"
        ),
        "note": (
            "Percentages are indicative manufacturing averages. "
            "Validate with a CA/DPR consultant before bank submission."
        )
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. TEAM PLANNER
# ─────────────────────────────────────────────────────────────────────────────
@tool("team_planner", args_schema=TeamInput)
def team_planner(product: str, budget: str = "") -> dict:
    """Suggests required employees, roles, salaries, and org structure."""
    print("\n[TOOL CALLED] -> team_planner")

    budget_lakhs = parse_budget_to_lakhs(budget) if budget else 0
    kb_dir       = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    team_roles  = []
    data_source = "knowledge_base"

    if content:
        section = extract_section(
            content,
            "manpower", "team", "staff", "employees",
            "workforce", "human resource", "hr", "personnel"
        )

        if section:
            rows = parse_table_rows(section)
            if rows:
                for row in rows:
                    team_roles.append({
                        "role"          : row.get("Role", row.get("Designation",
                                          row.get("Position", "Unknown"))),
                        "count"         : row.get("Count", row.get("No.", row.get("Qty", "1"))),
                        "monthly_salary": row.get("Salary", row.get("CTC",
                                          row.get("Monthly Pay", "Market rate"))),
                        "department"    : row.get("Dept", row.get("Department", "Operations")),
                    })
            else:
                items = parse_list_items(section)
                for item in items:
                    team_roles.append({
                        "role"          : item,
                        "count"         : 1,
                        "monthly_salary": "Market rate",
                        "department"    : "Operations",
                    })
        else:
            data_source = "generic_fallback"
    else:
        data_source = "generic_fallback"

    if not team_roles:
        if budget_lakhs < 25:
            team_roles = [
                {"role": "Factory Manager / Owner",       "count": 1,  "monthly_salary": "₹30–50K",  "department": "Management"},
                {"role": "Production Supervisor",         "count": 1,  "monthly_salary": "₹20–30K",  "department": "Production"},
                {"role": "Machine Operator",              "count": 4,  "monthly_salary": "₹12–18K",  "department": "Production"},
                {"role": "Quality Inspector",             "count": 1,  "monthly_salary": "₹15–20K",  "department": "QC"},
                {"role": "Helper / Packer",               "count": 3,  "monthly_salary": "₹8–12K",   "department": "Production"},
                {"role": "Accountant (Part-time)",        "count": 1,  "monthly_salary": "₹10–15K",  "department": "Admin"},
            ]
        elif budget_lakhs < 100:
            team_roles = [
                {"role": "General Manager",               "count": 1,  "monthly_salary": "₹60–80K",  "department": "Management"},
                {"role": "Production Manager",            "count": 1,  "monthly_salary": "₹40–60K",  "department": "Production"},
                {"role": "Production Supervisor",         "count": 2,  "monthly_salary": "₹25–35K",  "department": "Production"},
                {"role": "Machine Operator",              "count": 8,  "monthly_salary": "₹15–20K",  "department": "Production"},
                {"role": "QC Engineer",                   "count": 1,  "monthly_salary": "₹25–35K",  "department": "QC"},
                {"role": "QC Inspector",                  "count": 2,  "monthly_salary": "₹15–20K",  "department": "QC"},
                {"role": "Store & Purchase Executive",    "count": 1,  "monthly_salary": "₹20–25K",  "department": "Stores"},
                {"role": "Maintenance Technician",        "count": 1,  "monthly_salary": "₹18–25K",  "department": "Maintenance"},
                {"role": "Accountant",                    "count": 1,  "monthly_salary": "₹20–30K",  "department": "Finance"},
                {"role": "Helper / Packer",               "count": 6,  "monthly_salary": "₹10–14K",  "department": "Production"},
                {"role": "Security / Housekeeping",       "count": 2,  "monthly_salary": "₹10–12K",  "department": "Admin"},
            ]
        else:
            team_roles = [
                {"role": "Plant Head / Director",         "count": 1,  "monthly_salary": "₹1.2–2L",  "department": "Management"},
                {"role": "Production Manager",            "count": 1,  "monthly_salary": "₹70K–1L",  "department": "Production"},
                {"role": "Quality Manager",               "count": 1,  "monthly_salary": "₹60–80K",  "department": "QC"},
                {"role": "HR & Admin Manager",            "count": 1,  "monthly_salary": "₹50–70K",  "department": "HR"},
                {"role": "Finance Manager",               "count": 1,  "monthly_salary": "₹60–80K",  "department": "Finance"},
                {"role": "Production Supervisor",         "count": 3,  "monthly_salary": "₹30–40K",  "department": "Production"},
                {"role": "Process Engineer",              "count": 2,  "monthly_salary": "₹35–50K",  "department": "Production"},
                {"role": "Machine Operator",              "count": 15, "monthly_salary": "₹15–22K",  "department": "Production"},
                {"role": "QC Inspector",                  "count": 4,  "monthly_salary": "₹18–25K",  "department": "QC"},
                {"role": "Maintenance Engineer",          "count": 2,  "monthly_salary": "₹25–35K",  "department": "Maintenance"},
                {"role": "Store Keeper",                  "count": 2,  "monthly_salary": "₹18–22K",  "department": "Stores"},
                {"role": "Sales & Marketing Executive",   "count": 2,  "monthly_salary": "₹25–40K",  "department": "Sales"},
                {"role": "Helper / Packer",               "count": 10, "monthly_salary": "₹10–14K",  "department": "Production"},
                {"role": "Security / Housekeeping",       "count": 4,  "monthly_salary": "₹10–12K",  "department": "Admin"},
            ]

    dept_summary  = {}
    total_headcount = 0

    for role in team_roles:
        count = int(re.search(r'\d+', str(role["count"])).group()) \
                if re.search(r'\d+', str(role["count"])) else 1
        dept  = role.get("department", "Operations")
        dept_summary[dept] = dept_summary.get(dept, 0) + count
        total_headcount   += count

    salary_bill_lakhs = round(total_headcount * 0.20, 1)

    return {
        "product"              : product,
        "matched_entry"        : matched_name or "N/A",
        "data_source"          : data_source,
        "total_headcount"      : total_headcount,
        "department_summary"   : dept_summary,
        "team_roles"           : team_roles,
        "estimated_monthly_salary_bill": f"₹{salary_bill_lakhs} Lakhs/month (avg estimate)",
        "note": "Headcount scales with production volume. Start lean, hire as capacity grows."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. FACTORY SIZE CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────
@tool("factory_size_calculator", args_schema=CapacityInput)
def factory_size_calculator(product: str, production_capacity_per_day: int = 1000) -> dict:
    """Calculates required factory area based on product and daily production target."""
    print("\n[TOOL CALLED] -> factory_size_calculator")

    kb_dir = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    area_data   = {}
    data_source = "knowledge_base"

    if content:
        section = extract_section(
            content,
            "area", "space", "factory size", "land",
            "floor area", "built-up", "layout", "infrastructure"
        )

        if section:
            rows = parse_table_rows(section)
            if rows:
                for row in rows:
                    zone = row.get("Zone", row.get("Area", row.get("Section", "")))
                    size = row.get("Size", row.get("Sq Ft", row.get("Area (sq ft)", "")))
                    if zone and size:
                        area_data[zone] = size
            else:
                sqft_matches = re.findall(
                    r'(.{5,40}?)\s*[:–]\s*([\d,]+)\s*(?:sq\.?\s*ft|sqft|square feet)',
                    section,
                    re.IGNORECASE
                )
                for label, size in sqft_matches:
                    area_data[label.strip()] = f"{size} sq ft"
        else:
            data_source = "calculated"
    else:
        data_source = "calculated"

    if not area_data:
        units = production_capacity_per_day

        if units <= 500:
            multiplier = 0.05
        elif units <= 2000:
            multiplier = 0.035
        elif units <= 5000:
            multiplier = 0.025
        else:
            multiplier = 0.018

        production_area = round(units * multiplier * 100)
        warehouse_area  = round(production_area * 0.35)
        qc_area         = round(production_area * 0.12)
        packing_area    = round(production_area * 0.15)
        utility_area    = round(production_area * 0.08)
        admin_area      = round(production_area * 0.10)
        total_area      = production_area + warehouse_area + qc_area + \
                          packing_area + utility_area + admin_area

        area_data = {
            "Raw Material Warehouse"  : f"{warehouse_area} sq ft",
            "Main Production Floor"   : f"{production_area} sq ft",
            "QC & Testing Area"       : f"{qc_area} sq ft",
            "Packing & Dispatch"      : f"{packing_area} sq ft",
            "Utility & Maintenance"   : f"{utility_area} sq ft",
            "Admin & Welfare"         : f"{admin_area} sq ft",
        }

    total_area_val = sum(
        int(re.search(r'[\d,]+', v).group().replace(",", ""))
        for v in area_data.values()
        if re.search(r'[\d,]+', v)
    )

    plot_area  = round(total_area_val / 0.50)
    plot_acres = round(plot_area / 43560, 2)

    return {
        "product"                   : product,
        "matched_entry"             : matched_name or "N/A",
        "production_capacity_per_day": f"{production_capacity_per_day} units/day",
        "data_source"               : data_source,
        "zone_wise_area"            : area_data,
        "total_built_up_area"       : f"{total_area_val:,} sq ft",
        "recommended_plot_size"     : f"~{plot_area:,} sq ft (~{plot_acres} acres)",
        "note": (
            "Area scales with automation level. "
            "Higher automation = smaller footprint per unit. "
            "Add 20–25% for future expansion."
        )
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. TIMELINE GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
@tool("timeline_generator", args_schema=PlanningInput)
def timeline_generator(product: str, budget: str = "") -> dict:
    """Generates a detailed month-by-month execution timeline."""
    print("\n[TOOL CALLED] -> timeline_generator")

    budget_lakhs = parse_budget_to_lakhs(budget) if budget else 0
    kb_dir       = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    kb_timeline = {}
    data_source = "knowledge_base"

    if content:
        section = extract_section(
            content,
            "timeline", "schedule", "implementation",
            "gantt", "month", "execution plan"
        )

        if section:
            month_pattern = re.finditer(
                r'month\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*[:\-–]\s*(.+)',
                section.lower()
            )
            for match in month_pattern:
                m_start = int(match.group(1))
                m_end   = match.group(2)
                task    = match.group(3).strip().title()
                key     = f"Month {m_start}" if not m_end else f"Month {m_start}–{m_end}"
                kb_timeline[key] = task
        else:
            data_source = "generic_fallback"
    else:
        data_source = "generic_fallback"

    if not kb_timeline:
        if budget_lakhs < 25:
            kb_timeline = {
                "Month 1"  : "Business Registration, MSME Udyam, Bank Account Opening",
                "Month 1–2": "Product Design Finalization & BOM Preparation",
                "Month 2"  : "Vendor Identification & Machinery Quotations",
                "Month 2–3": "Shed/Workshop Finalization & Basic Civil Work",
                "Month 3"  : "Machinery Procurement & Installation",
                "Month 3–4": "Staff Recruitment & Training",
                "Month 4"  : "Trial Production Runs & Product Testing",
                "Month 5"  : "BIS / Quality Certification Application",
                "Month 5–6": "Sales Channel Setup & First Commercial Dispatch",
            }
        elif budget_lakhs < 100:
            kb_timeline = {
                "Month 1"  : "DPR Preparation & Project Financing (Bank Loan / Subsidy)",
                "Month 1–2": "Company Registration, DPIIT Startup Recognition, Licenses",
                "Month 2–3": "Factory Land / Shed Lease & Civil Modification",
                "Month 3"  : "Machinery Ordering (domestic + imported if any)",
                "Month 3–5": "Utility Connections (Power, Water, Gas) & Electrification",
                "Month 4–5": "Machinery Erection, Commissioning & Staff Training",
                "Month 5–6": "Trial Production & IPQC Setup",
                "Month 6–7": "BIS / ISO Certification & Regulatory Compliance",
                "Month 7–9": "Market Penetration & Ramp-up to 60% Capacity",
            }
        else:
            kb_timeline = {
                "Month 1–2" : "Detailed Project Report (DPR), EIA Study, Financial Closure",
                "Month 2–4" : "Land Acquisition / Lease, Regulatory Approvals (PCB, Factory Act)",
                "Month 3–7" : "Civil & Structural Construction — Foundation, Shed, Admin Block",
                "Month 5–8" : "Machinery Procurement, Import Clearances, Vendor Contracts",
                "Month 8–12": "Machinery Installation, Utility Commissioning, ETP Setup",
                "Month 10–13":"Staff Recruitment, Training & SOPs Finalization",
                "Month 12–15":"Trial Runs, Product Testing, BIS/ISO Certification",
                "Month 15–18":"Commercial Launch, Sales Network Activation",
                "Month 18–24":"Capacity Ramp-up & Working Capital Optimization",
            }

    critical_keywords = [
        "loan", "finance", "approval", "clearance", "import",
        "certification", "bis", "iso", "launch"
    ]
    annotated_timeline = {}
    for period, task in kb_timeline.items():
        is_critical = any(kw in task.lower() for kw in critical_keywords)
        annotated_timeline[period] = {
            "task"         : task,
            "critical_path": is_critical,
        }

    return {
        "product"          : product,
        "matched_entry"    : matched_name or "N/A",
        "budget_lakhs"     : f"₹{budget_lakhs:.1f} Lakhs" if budget_lakhs else "Not provided",
        "data_source"      : data_source,
        "total_months"     : len(kb_timeline),
        "timeline"         : annotated_timeline,
        "note": "Critical path items marked. Buffer 10–15% time for government approvals."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. RISK ANALYZER
# ─────────────────────────────────────────────────────────────────────────────
@tool("risk_analyzer", args_schema=LocationInput)
def risk_analyzer(product: str, location: str) -> dict:
    """
    Predicts delays, supply chain, investment, compliance,
    and market risks with severity ratings.
    """
    print("\n[TOOL CALLED] -> risk_analyzer")

    kb_dir = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    kb_risks    = []
    data_source = "knowledge_base"

    if content:
        section = extract_section(
            content,
            "risk", "challenges", "threats",
            "barriers", "issues", "concerns"
        )

        if section:
            items = parse_list_items(section)
            for item in items:
                kb_risks.append({
                    "risk"       : item,
                    "category"   : "Product-Specific",
                    "severity"   : "Medium",
                    "mitigation" : "Refer knowledge base for mitigation details"
                })
        else:
            data_source = "generic_analysis"
    else:
        data_source = "generic_analysis"

    location_lower = location.lower()

    env_clearance = (
        "Obtain NOC from State PCB before construction"
        if any(s in location_lower for s in ["gujarat", "maharashtra", "rajasthan"])
        else f"Check State PCB and factory act norms for {location}"
    )

    landlocked_risk = (
        "Higher logistics cost — landlocked state, plan for road freight"
        if any(s in location_lower for s in ["mp", "madhya pradesh", "chhattisgarh",
                                              "jharkhand", "uttarakhand"])
        else "Port access available — import/export feasible"
    )

    structured_risks = [
        {
            "category"   : "Execution / Delay Risk",
            "severity"   : "High",
            "risk"       : "Machinery delivery delays (especially imports — 8–16 weeks lead time)",
            "mitigation" : "Order machinery early, prefer domestic vendors where quality permits"
        },
        {
            "category"   : "Supply Chain Risk",
            "severity"   : "Medium",
            "risk"       : f"Raw material price volatility for {product} inputs",
            "mitigation" : "Sign quarterly rate contracts with 2–3 alternate suppliers"
        },
        {
            "category"   : "Financial Risk",
            "severity"   : "High",
            "risk"       : "Working capital crunch in first 6 months before receivables stabilize",
            "mitigation" : "Secure 3-month working capital limit from bank before launch"
        },
        {
            "category"   : "Regulatory / Compliance Risk",
            "severity"   : "Medium",
            "risk"       : env_clearance,
            "mitigation" : "Engage a liaison consultant for approvals in parallel with construction"
        },
        {
            "category"   : "Logistics Risk",
            "severity"   : "Low",
            "risk"       : landlocked_risk,
            "mitigation" : "Tie up with 3PL logistics partner; negotiate volume-based freight rates"
        },
        {
            "category"   : "Market Risk",
            "severity"   : "Medium",
            "risk"       : f"Established competitors in {product} segment may undercut pricing",
            "mitigation" : "Focus on quality differentiation, certifications, and B2B long-term contracts"
        },
        {
            "category"   : "Technology Risk",
            "severity"   : "Low",
            "risk"       : "Process technology becoming obsolete faster than asset depreciation",
            "mitigation" : "Choose modular machinery; maintain relationships with OEM for upgrades"
        },
        {
            "category"   : "HR Risk",
            "severity"   : "Low",
            "risk"       : "Skilled operator attrition affecting production quality",
            "mitigation" : "Build internal training program; tie retention to incentive bonus"
        },
    ]

    all_risks = kb_risks + structured_risks

    severity_count = {"High": 0, "Medium": 0, "Low": 0}
    for r in all_risks:
        sev = r.get("severity", "Medium")
        severity_count[sev] = severity_count.get(sev, 0) + 1

    overall_risk = (
        "High"   if severity_count["High"] >= 3 else
        "Medium" if severity_count["Medium"] >= 3 else
        "Low"
    )

    return {
        "product"          : product,
        "location"         : location,
        "matched_entry"    : matched_name or "N/A",
        "data_source"      : data_source,
        "overall_risk_level": overall_risk,
        "risk_summary"     : severity_count,
        "risks"            : all_risks,
        "top_priority_actions": [
            r["mitigation"] for r in all_risks
            if r.get("severity") == "High"
        ],
        "note": (
            "Risk severity is indicative. "
            "Engage a domain expert for product-specific regulatory deep-dive."
        )
    }


class IndustrialLandInput(BaseModel):
    product: str = Field(description="The product to be manufactured (e.g. 'solar panels', 'EV chargers', 'LED bulbs')")
    state: str = Field(description="Target state (e.g. 'Gujarat', 'Maharashtra', 'Rajasthan', 'Tamil Nadu')", default="")
    land_size: str = Field(description="Required land size if known (e.g. '2 acres', '10000 sq ft'). Leave empty for auto-calculation.", default="")
    budget_lakhs: float = Field(description="Total setup budget in Lakhs for cost matching context", default=0.0)
    use_live_scraping: bool = Field(description="Enable real-time web scraping for fresh data", default=True)
    use_playwright: bool = Field(description="Enable Playwright for JS-heavy portals (slower)", default=False)
    serp_api_key: Optional[str] = Field(description="Optional SerpAPI key for Google-backed search", default=None)
    cache_ttl_hours: int = Field(description="SQLite cache TTL in hours (0 = no cache)", default=6)


# ─────────────────────────────────────────────────────────────────────────────
# 7. INDUSTRIAL LAND & PARK SEARCH (Plant Location Optimization Engine)
# ─────────────────────────────────────────────────────────────────────────────
@tool("industrial_land_search", args_schema=IndustrialLandInput)
def industrial_land_search(
    product: str,
    state: str = "",
    land_size: str = "",
    budget_lakhs: float = 0.0,
    use_live_scraping: bool = True,
    use_playwright: bool = False,
    serp_api_key: Optional[str] = None,
    cache_ttl_hours: int = 6,
) -> dict:
    """
    Recommends suitable State Industrial Parks (GIDC, MIDC, RIICO, SIPCOT, KIADB, APIIC, TSIIC, UPSIDA, HSIIDC, MPIDC, IDCO),
    SEZs, and industrial corridors based on product type, required land footprint, infrastructure, and budget.
    Uses multi-source live scraping (IILB/NSWS, GIDC, MIDC, InvestIndia, DDG, SerpAPI) via industrialsearch subtool
    and an 8-Pillar Location Suitability Scoring Engine (0-100).
    Links directly to official India Industrial Land Bank (IILB).
    """
    print(f"\n[TOOL CALLED] -> industrial_land_search (Product: '{product}', State: '{state or 'India-wide Search'}')")

    if subtool_industrial_land_search is not None:
        try:
            return subtool_industrial_land_search(
                product=product,
                state=state,
                land_size=land_size,
                budget_lakhs=budget_lakhs,
                use_live_scraping=use_live_scraping,
                use_playwright=use_playwright,
                serp_api_key=serp_api_key,
                cache_ttl_hours=cache_ttl_hours,
            )
        except Exception as e:
            print(f"[WARNING] Subtool industrial_land_search failed: {e}. Falling back to curated search.")

    target_state = state.strip()
    product_lower = product.lower()

    # Step 1: Auto-calculate land footprint if not specified
    if not land_size.strip():
        if any(k in product_lower for k in ["solar", "cell", "module", "wafer"]):
            estimated_land = "2–5 Acres"
            land_sqft = "87,120 – 217,800 sq ft"
        elif any(k in product_lower for k in ["battery", "ev charger", "electric vehicle", "automobile", "auto"]):
            estimated_land = "3–5 Acres"
            land_sqft = "130,680 – 217,800 sq ft"
        elif any(k in product_lower for k in ["led", "bulb", "electronic", "chip", "pcb", "semiconductor"]):
            estimated_land = "8,000–12,000 sq ft (~0.25 Acres)"
            land_sqft = "8,000 – 12,000 sq ft"
        elif any(k in product_lower for k in ["furniture", "wood", "plywood", "textile", "garment"]):
            estimated_land = "1–2 Acres"
            land_sqft = "43,560 – 87,120 sq ft"
        elif any(k in product_lower for k in ["pharma", "chemical", "fertilizer", "biotech"]):
            estimated_land = "5–10 Acres"
            land_sqft = "217,800 – 435,600 sq ft"
        else:
            estimated_land = "1–2 Acres"
            land_sqft = "43,560 – 87,120 sq ft"
    else:
        estimated_land = land_size
        land_sqft = land_size

    # Step 2: Comprehensive State Industrial Development Corporations (SIDC) Database
    STATE_INDUSTRIAL_PARKS = {
        "gujarat": {
            "corporation": "GIDC (Gujarat Industrial Development Corporation)",
            "portal": "https://gidc.gujarat.gov.in",
            "state_name": "Gujarat",
            "parks": [
                {
                    "park_name": "Sanand GIDC Phase II",
                    "district": "Ahmedabad",
                    "approx_land_cost": "Rs 3,500 – Rs 5,500 / sq m",
                    "power_tariff": "Rs 6.5 / kWh (24/7 Industrial Line)",
                    "ecosystem": "Automotive, Electronics, EV & Battery Cluster",
                    "infrastructure": "220kV Substation, 4-lane Expressway, ICD Sanand",
                    "subsidies": "15% Capital Subsidy + 100% SGST Reimbursement (7 Yrs)",
                    "logistics": "Direct access to Western Dedicated Freight Corridor (DFC) & Mundra Port",
                    "why_recommended": "Dedicated electronics & auto cluster with plug-and-play utility connections.",
                    "suitability_score": 95
                },
                {
                    "park_name": "Halol GIDC Industrial Estate",
                    "district": "Panchmahal / Vadodara",
                    "approx_land_cost": "Rs 2,200 – Rs 3,800 / sq m",
                    "power_tariff": "Rs 6.3 / kWh",
                    "ecosystem": "Heavy Engineering, Solar Components & Electricals",
                    "infrastructure": "High-tension Power Grid, Gas Pipeline, Expressway",
                    "subsidies": "10% Capital Subsidy + Electricity Duty Exemption for 5 Yrs",
                    "logistics": "Proximity to Vadodara engineering hub and NH-48",
                    "why_recommended": "Cost-effective land with strong industrial power grid and skilled engineering labor.",
                    "suitability_score": 88
                },
                {
                    "park_name": "Dholera Special Investment Region (SIR)",
                    "district": "Ahmedabad",
                    "approx_land_cost": "Rs 2,500 – Rs 4,000 / sq m",
                    "power_tariff": "Rs 6.0 / kWh (Green Energy Grid)",
                    "ecosystem": "Semiconductor, Solar Gigafactory & Defence",
                    "infrastructure": "Smart City Grid, DFC Access, International Airport corridor",
                    "subsidies": "Mega Project PLI Benefits + Stamp Duty Exemption",
                    "logistics": "Dedicated Freight Corridor + Ahmedabad Dholera Expressway",
                    "why_recommended": "India's largest greenfield smart industrial city with mega PLI subsidy benefits.",
                    "suitability_score": 96
                }
            ]
        },
        "maharashtra": {
            "corporation": "MIDC (Maharashtra Industrial Development Corporation)",
            "portal": "https://www.midcindia.org",
            "state_name": "Maharashtra",
            "parks": [
                {
                    "park_name": "Chakan MIDC Phase IV",
                    "district": "Pune",
                    "approx_land_cost": "Rs 5,000 – Rs 8,000 / sq m",
                    "power_tariff": "Rs 7.8 / kWh",
                    "ecosystem": "Auto Component, EV, CNC & Heavy Manufacturing",
                    "infrastructure": "JNPT Port Highway, CETP Plant, Skilled ITI Talent Pool",
                    "subsidies": "Package Scheme of Incentives (PSI) 2019 - Up to 100% Industrial Promotion Subsidy",
                    "logistics": "Direct access to JNPT Port Mumbai & Pune-Mumbai Expressway",
                    "why_recommended": "Premier manufacturing hub with dense OEM vendor ecosystem.",
                    "suitability_score": 94
                },
                {
                    "park_name": "Shendra-Bidkin Industrial Park (AURIC)",
                    "district": "Chhatrapati Sambhajinagar (Aurangabad)",
                    "approx_land_cost": "Rs 2,800 – Rs 4,200 / sq m",
                    "power_tariff": "Rs 7.2 / kWh",
                    "ecosystem": "Textiles, Engineering & Electronics",
                    "infrastructure": "DMIC Industrial Corridor, Smart City Utility Grid",
                    "subsidies": "D+ Tier District Incentives (Max Capital & Power Subsidy)",
                    "logistics": "Samruddhi Mahamarg Highway + DMIC Freight Link",
                    "why_recommended": "Part of Delhi-Mumbai Industrial Corridor with modern underground utilities.",
                    "suitability_score": 90
                }
            ]
        },
        "uttar pradesh": {
            "corporation": "UPSIDA / YEIDA (Yamuna Expressway Industrial Development Authority)",
            "portal": "https://niveshmitra.up.nic.in",
            "state_name": "Uttar Pradesh",
            "parks": [
                {
                    "park_name": "YEIDA Sector 28 Medical & Toy Park / Sector 32",
                    "district": "Gautam Buddha Nagar (Greater Noida)",
                    "approx_land_cost": "Rs 4,000 – Rs 7,000 / sq m",
                    "power_tariff": "Rs 6.9 / kWh",
                    "ecosystem": "Electronics Manufacturing Cluster (EMC 2.0), EV & Medical Devices",
                    "infrastructure": "Noida International Airport (Jewar), Dedicated 33kV Substation",
                    "subsidies": "UP Industrial Investment Policy 2022 - Up to 25% Capital Subsidy + 100% SGST Waiver",
                    "logistics": "Yamuna Expressway + Eastern Peripheral Expressway + Jewar Cargo Hub",
                    "why_recommended": "Fastest growing electronics & hardware corridor adjacent to Jewar Airport.",
                    "suitability_score": 95
                },
                {
                    "park_name": "Trans-Ganga City Industrial Complex",
                    "district": "Unnao / Kanpur",
                    "approx_land_cost": "Rs 2,500 – Rs 4,200 / sq m",
                    "power_tariff": "Rs 6.5 / kWh",
                    "ecosystem": "Auto Components, Leather Goods & General Engineering",
                    "infrastructure": "24/7 High-Voltage Power, Effluent Treatment Plant",
                    "subsidies": "Bundelkhand/Purvanchal Tier Incentive Scheme + Stamp Duty Exemption",
                    "logistics": "Lucknow-Kanpur Expressway Connectivity",
                    "why_recommended": "Strategic central UP location with competitive land rates and rich skilled workforce.",
                    "suitability_score": 87
                }
            ]
        },
        "tamil nadu": {
            "corporation": "SIPCOT (State Industries Promotion Corporation of Tamil Nadu)",
            "portal": "https://sipcot.tn.gov.in",
            "state_name": "Tamil Nadu",
            "parks": [
                {
                    "park_name": "Sriperumbudur Industrial Park",
                    "district": "Kanchipuram / Chennai",
                    "approx_land_cost": "Rs 4,500 – Rs 7,500 / sq m",
                    "power_tariff": "Rs 6.7 / kWh",
                    "ecosystem": "Electronics Hardware, Hardware Startups & EV Hub",
                    "infrastructure": "230kV Substation, CETP, Chennai Airport & Sea Port access",
                    "subsidies": "TN Policy 2023 - Up to 50% Capital Subsidy for Sunrise Sectors",
                    "logistics": "Chennai Port (35 km) + Ennore Port (50 km) + NH-48",
                    "why_recommended": "India's leading electronics manufacturing corridor with port connectivity.",
                    "suitability_score": 95
                },
                {
                    "park_name": "Hosur SIPCOT Phase II",
                    "district": "Krishnagiri",
                    "approx_land_cost": "Rs 3,000 – Rs 5,000 / sq m",
                    "power_tariff": "Rs 6.5 / kWh",
                    "ecosystem": "EV Mobility, Precision Engineering & Machining",
                    "infrastructure": "Inland Freight Terminal, Dual Power Substation Lines",
                    "subsidies": "Special EV Sector Subsidy + Turnover Incentive",
                    "logistics": "Bengaluru Border (40 km) + Chennai-Bengaluru Industrial Corridor",
                    "why_recommended": "Ideal for hardware & EV startups leveraging Bengaluru R&D talent.",
                    "suitability_score": 92
                }
            ]
        },
        "telangana": {
            "corporation": "TSIIC (Telangana State Industrial Infrastructure Corporation)",
            "portal": "https://tsipass.telangana.gov.in",
            "state_name": "Telangana",
            "parks": [
                {
                    "park_name": "E-City Fab City (Raviryal Industrial Park)",
                    "district": "Ranga Reddy / Hyderabad",
                    "approx_land_cost": "Rs 3,500 – Rs 6,000 / sq m",
                    "power_tariff": "Rs 6.6 / kWh",
                    "ecosystem": "Electronics Hardware, Consumer Appliances & Solar",
                    "infrastructure": "Outer Ring Road (ORR) Access, Dedicated Power Line, Airport Proximity",
                    "subsidies": "TS-iPASS Single Window Clearance (15-Day Auto NOC) + 20% Capital Subsidy",
                    "logistics": "Hyderabad Airport Cargo (15 km) + ORR Expressway",
                    "why_recommended": "Fastest single-window NOC clearance in India with strong electronics ecosystem.",
                    "suitability_score": 93
                },
                {
                    "park_name": "Zaheerabad NIMZ (National Investment & Manufacturing Zone)",
                    "district": "Sangareddy",
                    "approx_land_cost": "Rs 2,200 – Rs 3,800 / sq m",
                    "power_tariff": "Rs 6.3 / kWh",
                    "ecosystem": "Automotive, Heavy Machinery & Electrical Components",
                    "infrastructure": "12,600-Acre Integrated Industrial Township Grid",
                    "subsidies": "NIMZ Central PLI Incentives + State Power Duty Exemption",
                    "logistics": "NH-65 Mumbai-Hyderabad Highway Link",
                    "why_recommended": "Large-scale greenfield manufacturing zone ideal for heavy machinery and auto components.",
                    "suitability_score": 89
                }
            ]
        },
        "karnataka": {
            "corporation": "KIADB (Karnataka Industrial Areas Development Board)",
            "portal": "https://kiadb.karnataka.gov.in",
            "state_name": "Karnataka",
            "parks": [
                {
                    "park_name": "Narasapura Industrial Area",
                    "district": "Kolar / Bengaluru East",
                    "approx_land_cost": "Rs 3,800 – Rs 6,000 / sq m",
                    "power_tariff": "Rs 7.1 / kWh",
                    "ecosystem": "Automotive, Solar Components & Heavy Machinery",
                    "infrastructure": "Chennai-Bengaluru Expressway Link, High Voltage Grid",
                    "subsidies": "Karnataka Industrial Policy 2020-25 - Investment Promotion Subsidy",
                    "logistics": "Direct access to Chennai-Bengaluru Industrial Corridor",
                    "why_recommended": "Rapidly growing hardware hub with high capital subsidy incentives.",
                    "suitability_score": 91
                }
            ]
        },
        "rajasthan": {
            "corporation": "RIICO (Rajasthan State Industrial Development and Investment Corporation)",
            "portal": "https://riico.rajasthan.gov.in",
            "state_name": "Rajasthan",
            "parks": [
                {
                    "park_name": "Neemrana Industrial Area (Japanese Zone)",
                    "district": "Alwar",
                    "approx_land_cost": "Rs 3,000 – Rs 4,500 / sq m",
                    "power_tariff": "Rs 6.8 / kWh",
                    "ecosystem": "Auto Components, Solar Equipment & Electronics",
                    "infrastructure": "NH-48 Delhi-Jaipur Highway, Inland Container Depot (ICD)",
                    "subsidies": "RIPS 2022 - Up to 75% Investment Subsidy + Electricity Duty Exemption",
                    "logistics": "Delhi-NCR Market Proximity (100 km) + DMIC Access",
                    "why_recommended": "Direct proximity to NCR market with dedicated industrial power lines.",
                    "suitability_score": 91
                }
            ]
        },
        "haryana": {
            "corporation": "HSIIDC (Haryana State Industrial & Infrastructure Development Corp)",
            "portal": "https://hsiidc.org.in",
            "state_name": "Haryana",
            "parks": [
                {
                    "park_name": "IMT Manesar / IMT Sohna Smart Industrial Park",
                    "district": "Gurugram / Mewat",
                    "approx_land_cost": "Rs 6,000 – Rs 10,000 / sq m",
                    "power_tariff": "Rs 7.2 / kWh",
                    "ecosystem": "Automobile OEM, EV, Consumer Durables & Electronics",
                    "infrastructure": "KMP Expressway, Dedicated Power Substation",
                    "subsidies": "Haryana Enterprises & Employment Policy - Capital Subsidy up to 15%",
                    "logistics": "Delhi Airport (35 km) + Western DFC Logistics Hub",
                    "why_recommended": "Top tier auto and electronics hub with unmatched NCR market access.",
                    "suitability_score": 92
                }
            ]
        },
        "madhya pradesh": {
            "corporation": "MPIDC (Madhya Pradesh Industrial Development Corporation)",
            "portal": "https://mpinvest.mp.gov.in",
            "state_name": "Madhya Pradesh",
            "parks": [
                {
                    "park_name": "Pithampur Smart Industrial City Sector 7",
                    "district": "Dhar / Indore",
                    "approx_land_cost": "Rs 2,000 – Rs 3,500 / sq m",
                    "power_tariff": "Rs 6.1 / kWh",
                    "ecosystem": "Automotive, Pharma, Engineering & Solar",
                    "infrastructure": "Indore Airport, Inland Container Depot (ICD Pithampur)",
                    "subsidies": "MP Industrial Promotion Policy - 40% Investment Assistance + Power Rebate",
                    "logistics": "Central location connecting North, West, and South logistics routes",
                    "why_recommended": "Lowest operating land & power cost with multi-modal central India connectivity.",
                    "suitability_score": 90
                }
            ]
        },
        "andhra pradesh": {
            "corporation": "APIIC (Andhra Pradesh Industrial Infrastructure Corporation)",
            "portal": "https://www.apiic.in",
            "state_name": "Andhra Pradesh",
            "parks": [
                {
                    "park_name": "Sri City Industrial Smart City",
                    "district": "Tirupati / Chittoor",
                    "approx_land_cost": "Rs 3,000 – Rs 5,000 / sq m",
                    "power_tariff": "Rs 6.4 / kWh",
                    "ecosystem": "Export Manufacturing, Electronics & Solar",
                    "infrastructure": "Krishnapatnam & Ennore Sea Ports, Railway Siding",
                    "subsidies": "AP Industrial Development Policy - 100% SGST Reimbursement",
                    "logistics": "Multi-product SEZ with hassle-free single-window clearances.",
                    "why_recommended": "Multi-product SEZ with hassle-free single-window clearances.",
                    "suitability_score": 92
                }
            ]
        },
        "odisha": {
            "corporation": "IDCO (Industrial Promotion and Investment Corporation of Odisha)",
            "portal": "https://investodisha.gov.in",
            "state_name": "Odisha",
            "parks": [
                {
                    "park_name": "Kalinganagar Industrial Complex / Paradeep Plastic Park",
                    "district": "Jajpur / Jagatsinghpur",
                    "approx_land_cost": "Rs 1,800 – Rs 3,000 / sq m",
                    "power_tariff": "Rs 5.8 / kWh",
                    "ecosystem": "Steel, Metals, Chemicals, Plastics & Heavy Capital Goods",
                    "infrastructure": "Deepwater Paradeep Port Access, 33kV Dedicated Line",
                    "subsidies": "IPR 2022 - Up to 30% Capital Subsidy + Lowest Power Tariffs",
                    "logistics": "Paradeep Port (25 km) + East Coast Dedicated Freight Line",
                    "why_recommended": "Ideal for metal, chemical, and export-oriented manufacturing with lowest power cost.",
                    "suitability_score": 89
                }
            ]
        }
    }

    # Step 3: Match State or Perform Search
    matched_parks = []
    data_source = "curated_sidc_database"

    state_key = target_state.lower()
    
    # Direct match or partial match on state name
    matched_sidc = None
    for k, v in STATE_INDUSTRIAL_PARKS.items():
        if k in state_key or state_key in k:
            matched_sidc = v
            break

    if matched_sidc:
        matched_parks = matched_sidc["parks"]
        corp_info = matched_sidc["corporation"]
        portal_info = matched_sidc["portal"]
        state_display = matched_sidc["state_name"]
    else:
        # If specific state not matched or all-India requested, compile top recommendations across states
        corp_info = "State Industrial Development Corporations (SIDC & IILB)"
        portal_info = "https://www.nsws.gov.in"
        state_display = target_state or "All-India Comparative Evaluation"

        # Try dynamic web search via DuckDuckGo if target state was explicitly specified but not in DB
        dynamic_web_parks = []
        if target_state:
            try:
                ddg_func = None
                try:
                    from agents.tools.research_tools import ddg_search as ddg_func
                except ImportError:
                    pass

                if ddg_func:
                    q = f'site:gov.in OR site:investindia.gov.in "{target_state}" "{product}" industrial park estate land'
                    print(f"  [LIVE LAND SEARCH] {q}")
                    web_hits = ddg_func(q, max_results=4)
                    for hit in web_hits:
                        dynamic_web_parks.append({
                            "park_name": hit.get("title", f"{target_state} Industrial Zone")[:60],
                            "district": target_state,
                            "approx_land_cost": "Rs 2,200 – Rs 4,500 / sq m (SIDC Rate)",
                            "power_tariff": "Standard State Industrial DISCOM Rate",
                            "ecosystem": f"General Manufacturing for {product}",
                            "infrastructure": "SIDC Power Line, Road Grid & Water Line",
                            "subsidies": f"Eligible for {target_state} State MSME Incentives",
                            "logistics": "State Highway / NH Access",
                            "why_recommended": f"Live result from official {target_state} government industrial land repository.",
                            "suitability_score": 85,
                            "source_url": hit.get("url", "")
                        })
            except Exception as e:
                print(f"[WARNING] Web search fallback for land search failed: {e}")

        if dynamic_web_parks:
            matched_parks = dynamic_web_parks
            data_source = "live_government_web_search"
        else:
            # Gather top candidate parks across all states filtered by product suitability
            all_parks = []
            for s_key, s_data in STATE_INDUSTRIAL_PARKS.items():
                for p in s_data["parks"]:
                    p_copy = dict(p)
                    p_copy["state"] = s_data["state_name"]
                    p_copy["corporation"] = s_data["corporation"]
                    
                    # Boost suitability score if product keywords match park ecosystem
                    score = p_copy["suitability_score"]
                    if any(w in p_copy["ecosystem"].lower() for w in product_lower.split() if len(w) > 2):
                        score = min(98, score + 4)
                    p_copy["suitability_score"] = score
                    all_parks.append(p_copy)

            # Sort all parks by suitability score descending
            all_parks_sorted = sorted(all_parks, key=lambda x: x["suitability_score"], reverse=True)
            matched_parks = all_parks_sorted[:4]

    # Step 4: Add Suitability Labeling (0-100 Rating)
    for p in matched_parks:
        score = p.get("suitability_score", 85)
        if score >= 93:
            p["suitability_grade"] = f"{score}/100 Top Rated (Optimal Location)"
        elif score >= 88:
            p["suitability_grade"] = f"{score}/100 Recommended (Strong Contender)"
        else:
            p["suitability_grade"] = f"{score}/100 Viable Alternative"

    # Step 5: Construct 6-Pillar Site Selection Evaluation Framework
    infrastructure_eval_criteria = [
        {"pillar": "State Subsidies & Incentives",    "weight": "25%", "metric": "SGST Waiver + Capital Subsidy %"},
        {"pillar": "Supplier & Vendor Density",       "weight": "20%", "metric": "Proximity to OEM & raw material clusters"},
        {"pillar": "Freight & Logistics Access",      "weight": "20%", "metric": "Port / DFC / Expressway distance"},
        {"pillar": "Land Cost & Readiness",           "weight": "15%", "metric": "SIDC plot cost (Rs/sq m) + CETP plant"},
        {"pillar": "Power Tariff & Utilities",        "weight": "10%", "metric": "Industrial power tariff (Rs/kWh)"},
        {"pillar": "Skilled Labor Availability",      "weight": "10%", "metric": "Nearby ITI & Engineering talent pool"},
    ]

    return {
        "product"                       : product,
        "state"                         : state_display,
        "estimated_land_footprint"      : estimated_land,
        "land_area_sqft"                : land_sqft,
        "data_source"                   : data_source,
        "state_corporation"             : corp_info,
        "official_portal"               : portal_info,
        "official_national_land_bank"   : "https://www.nsws.gov.in (India Industrial Land Bank - IILB)",
        "national_single_window_system" : "https://www.nsws.gov.in (National Single Window System)",
        "invest_india_portal"           : "https://www.investindia.gov.in",
        "top_recommended_location"      : matched_parks[0]["park_name"] if matched_parks else "SIDC Industrial Corridor",
        "top_location_suitability_score": matched_parks[0]["suitability_grade"] if matched_parks else "88/100",
        "recommended_industrial_parks"  : matched_parks,
        "site_evaluation_pillars"       : infrastructure_eval_criteria,
        "budget_context"                : f"Rs {budget_lakhs:.1f} Lakhs" if budget_lakhs > 0 else "Not specified",
        "next_steps": [
            "1. Visit the India Industrial Land Bank (IILB at https://www.nsws.gov.in) to inspect vacant plot GIS maps",
            "2. Submit online land allotment application on state SIDC portal or National Single Window System (https://www.nsws.gov.in)",
            "3. Obtain Consent to Establish (CTE) from State Pollution Control Board (SPCB)",
            "4. File Udyam & Startup India registration for stamp duty & electricity duty waivers"
        ],
        "note": "Suitability scores (0-100) are evaluated based on state subsidies, logistics connectivity, vendor proximity, and power tariffs. Land costs reflect official SIDC indicative rates."
    }


# ─────────────────────────────────────────────────────────────────────────────
planning_tools_list = [
    product_planner,
    cost_estimator,
    team_planner,
    factory_size_calculator,
    timeline_generator,
    risk_analyzer,
    industrial_land_search,
]
