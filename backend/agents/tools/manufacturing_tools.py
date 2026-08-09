import os
import re
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from utils.kb_lookup import (
    get_manufacturing_kb_dir,
    fetch_product_content,
    extract_section,
    extract_all_sections,
    parse_list_items,
    parse_table_rows,
)


class ProductInput(BaseModel):
    product: str = Field(description="The product to be manufactured")


# ─────────────────────────────────────────────────────────────────────────────
# 1. MANUFACTURING RAG
# ─────────────────────────────────────────────────────────────────────────────
@tool("manufacturing_rag", args_schema=ProductInput)
def manufacturing_rag(product: str) -> dict:
    """
    Retrieves manufacturing guides, industrial manuals,
    and SOPs for the product from the Knowledge Base.
    """
    print("\n[TOOL CALLED] -> manufacturing_rag")

    kb_dir = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    if not content:
        return {
            "status"  : "not_found",
            "product" : product,
            "message" : f"No manufacturing guide found for '{product}' in knowledge base.",
            "guide"   : None,
        }

    sections = extract_all_sections(content)

    # Pull the most relevant sections for an SOP/guide
    guide_sections = {}
    priority_keys  = ["overview", "process", "sop", "procedure",
                      "manufacturing", "production", "guide", "steps"]

    for key in priority_keys:
        for sec_key, sec_val in sections.items():
            if key in sec_key and sec_val:
                guide_sections[sec_key] = sec_val

    return {
        "status"          : "found",
        "product"         : product,
        "matched_entry"   : matched_name,
        "available_sections": list(sections.keys()),
        "guide"           : guide_sections if guide_sections else sections,
        "raw_preview"     : content[:600] + "..." if len(content) > 600 else content,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. MACHINERY RECOMMENDATION
# ─────────────────────────────────────────────────────────────────────────────
@tool("machinery_recommendation", args_schema=ProductInput)
def machinery_recommendation(product: str) -> dict:
    """Returns recommended machinery, quantity, and estimated costs."""
    print("\n[TOOL CALLED] -> machinery_recommendation")

    kb_dir = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    machinery_list   = []
    total_cost_lakhs = 0.0
    data_source      = "knowledge_base"

    if content:
        # Extract machinery section
        section = extract_section(
            content,
            "machinery", "equipment", "machines",
            "plant and machinery", "capital equipment"
        )

        if section:
            # Try table format first
            rows = parse_table_rows(section)
            if rows:
                for row in rows:
                    item = {
                        "name"           : row.get("Machine", row.get("Equipment",
                                           row.get("Name", "Unknown"))),
                        "quantity"       : row.get("Qty", row.get("Quantity", "1")),
                        "estimated_cost" : row.get("Cost", row.get("Price",
                                           row.get("Estimated Cost", "Not specified"))),
                        "specifications" : row.get("Specs", row.get("Specification", "")),
                    }
                    machinery_list.append(item)

                    # Try to total up costs
                    cost_str = item["estimated_cost"].lower()
                    nums     = re.findall(r'[\d,]+\.?\d*', cost_str.replace(",", ""))
                    if nums:
                        val = float(nums[0])
                        qty = int(re.search(r'\d+', str(item["quantity"])).group()) \
                              if re.search(r'\d+', str(item["quantity"])) else 1
                        if "crore" in cost_str or " cr" in cost_str:
                            total_cost_lakhs += val * 100 * qty
                        else:
                            total_cost_lakhs += val * qty

            else:
                # Parse as bullet list
                items = parse_list_items(section)
                for item_text in items:
                    machinery_list.append({
                        "name"           : item_text,
                        "quantity"       : "As required",
                        "estimated_cost" : "Refer knowledge base",
                        "specifications" : "",
                    })
        else:
            data_source = "generic_fallback"
    else:
        data_source = "generic_fallback"

    # ── Fallback if KB has no machinery section ───────────────────────────
    if not machinery_list:
        machinery_list = [
            {
                "name"           : f"{product} Primary Processing Unit",
                "quantity"       : 1,
                "estimated_cost" : "₹15–25 Lakhs",
                "specifications" : "Industry standard grade"
            },
            {
                "name"           : f"{product} Secondary Assembly Line",
                "quantity"       : 1,
                "estimated_cost" : "₹10–15 Lakhs",
                "specifications" : "Semi-automatic"
            },
            {
                "name"           : "QA/Testing Station",
                "quantity"       : 1,
                "estimated_cost" : "₹3–5 Lakhs",
                "specifications" : "As per BIS norms"
            },
        ]
        total_cost_lakhs = 35.0

    return {
        "product"             : product,
        "matched_entry"       : matched_name or "N/A",
        "data_source"         : data_source,
        "machinery_list"      : machinery_list,
        "total_machinery_cost": (
            f"₹{total_cost_lakhs:.1f} Lakhs"
            if total_cost_lakhs > 0
            else "Refer individual item costs"
        ),
        "note": "Costs are indicative. Get vendor quotes before finalizing capex."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. PRODUCTION FLOW GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
@tool("production_flow_generator", args_schema=ProductInput)
def production_flow_generator(product: str) -> dict:
    """Generates the step-by-step production flow."""
    print("\n[TOOL CALLED] -> production_flow_generator")

    kb_dir = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    steps       = []
    data_source = "knowledge_base"

    if content:
        section = extract_section(
            content,
            "production flow", "process flow", "manufacturing process",
            "workflow", "production steps", "process steps", "flow"
        )

        if section:
            raw_steps = parse_list_items(section)
            for i, step in enumerate(raw_steps, 1):
                steps.append({
                    "step"        : i,
                    "description" : step,
                    "checkpoint"  : i in [1, len(raw_steps)]  # flag first & last
                })
        else:
            data_source = "generic_fallback"
    else:
        data_source = "generic_fallback"

    # ── Fallback ──────────────────────────────────────────────────────────
    if not steps:
        generic = [
            "Raw Material Receiving & Quality Inspection",
            "Material Pre-Processing (cutting, forming, cleaning)",
            "Core Manufacturing / Assembly",
            "In-Process Quality Check (IPQC)",
            "Finishing & Surface Treatment",
            "Final Quality Assurance (QA/QC)",
            "Packaging & Labelling",
            "Dispatch & Logistics"
        ]
        for i, desc in enumerate(generic, 1):
            steps.append({
                "step"        : i,
                "description" : desc,
                "checkpoint"  : i in [1, 4, 8]
            })

    return {
        "product"     : product,
        "matched_entry": matched_name or "N/A",
        "data_source" : data_source,
        "total_steps" : len(steps),
        "flow"        : steps,
        "note"        : "QC checkpoints marked. Adapt cycle times based on line speed."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. FACTORY LAYOUT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
@tool("factory_layout_generator", args_schema=ProductInput)
def factory_layout_generator(product: str) -> dict:
    """Suggests the optimal factory layout zoning."""
    print("\n[TOOL CALLED] -> factory_layout_generator")

    kb_dir = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    zones       = []
    area_sqft   = {}
    data_source = "knowledge_base"

    if content:
        section = extract_section(
            content,
            "layout", "factory layout", "floor plan",
            "zoning", "area", "space", "plant layout"
        )

        if section:
            # Try table: | Zone | Area (sq ft) | Purpose |
            rows = parse_table_rows(section)
            if rows:
                for row in rows:
                    zone_name = row.get("Zone", row.get("Area", row.get("Section", "")))
                    area      = row.get("Area (sq ft)", row.get("Size", row.get("Sq Ft", "")))
                    purpose   = row.get("Purpose", row.get("Use", ""))
                    if zone_name:
                        zones.append({
                            "zone"   : zone_name,
                            "area"   : area or "As per design",
                            "purpose": purpose or "",
                        })
            else:
                items = parse_list_items(section)
                for item in items:
                    zones.append({
                        "zone"   : item,
                        "area"   : "As per design",
                        "purpose": "",
                    })
        else:
            data_source = "generic_fallback"
    else:
        data_source = "generic_fallback"

    # ── Fallback ──────────────────────────────────────────────────────────
    if not zones:
        zones = [
            {"zone": "Raw Material Warehouse",      "area": "1500 sq ft", "purpose": "Inbound storage"},
            {"zone": "Pre-Processing Area",          "area": "800 sq ft",  "purpose": "Cutting, cleaning, prep"},
            {"zone": "Main Production Floor",        "area": "3000 sq ft", "purpose": "Core manufacturing"},
            {"zone": "In-Process QC Station",        "area": "400 sq ft",  "purpose": "IPQC checks"},
            {"zone": "Finished Goods Storage",       "area": "1200 sq ft", "purpose": "Pre-dispatch storage"},
            {"zone": "Quality Control Lab",          "area": "500 sq ft",  "purpose": "Testing & certification"},
            {"zone": "Packaging & Labelling Area",   "area": "600 sq ft",  "purpose": "Final packaging"},
            {"zone": "Dispatch / Loading Bay",       "area": "800 sq ft",  "purpose": "Outbound logistics"},
            {"zone": "Utility Room (Power/Water)",   "area": "300 sq ft",  "purpose": "Electrical, DG, water"},
            {"zone": "Admin & Welfare Block",        "area": "500 sq ft",  "purpose": "Office, canteen, restrooms"},
        ]

    total_area = sum(
        int(re.search(r'\d+', z["area"]).group())
        for z in zones
        if re.search(r'\d+', z["area"])
    )

    return {
        "product"      : product,
        "matched_entry": matched_name or "N/A",
        "data_source"  : data_source,
        "zones"        : zones,
        "total_zones"  : len(zones),
        "estimated_total_area": f"{total_area} sq ft" if total_area else "Refer zone breakdown",
        "note": "Layout is indicative. Adjust as per actual machinery footprint and local fire/safety norms."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. BOM GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
@tool("bom_generator", args_schema=ProductInput)
def bom_generator(product: str) -> dict:
    """Generates a Bill of Materials (BOM) detailing raw materials, quantity, and supplier type."""
    print("\n[TOOL CALLED] -> bom_generator")

    kb_dir = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    bom_items   = []
    data_source = "knowledge_base"

    if content:
        section = extract_section(
            content,
            "bill of materials", "bom", "raw materials",
            "materials", "components", "inputs", "ingredients"
        )

        if section:
            rows = parse_table_rows(section)
            if rows:
                for row in rows:
                    bom_items.append({
                        "material"        : row.get("Material", row.get("Component",
                                            row.get("Item", "Unknown"))),
                        "quantity_per_unit": row.get("Qty/Unit", row.get("Quantity",
                                            row.get("Per Unit", "As required"))),
                        "unit"            : row.get("Unit", ""),
                        "supplier_type"   : row.get("Supplier", row.get("Source",
                                            row.get("Supplier Type", "Market"))),
                        "estimated_cost"  : row.get("Cost", row.get("Rate", "Market rate")),
                        "notes"           : row.get("Notes", row.get("Remarks", "")),
                    })
            else:
                items = parse_list_items(section)
                for item in items:
                    bom_items.append({
                        "material"        : item,
                        "quantity_per_unit": "As required",
                        "unit"            : "",
                        "supplier_type"   : "Market",
                        "estimated_cost"  : "Market rate",
                        "notes"           : "",
                    })
        else:
            data_source = "generic_fallback"
    else:
        data_source = "generic_fallback"

    # ── Fallback ──────────────────────────────────────────────────────────
    if not bom_items:
        bom_items = [
            {
                "material"        : "Primary Raw Material (Grade A)",
                "quantity_per_unit": "2 kg",
                "unit"            : "kg",
                "supplier_type"   : "Wholesale Distributor",
                "estimated_cost"  : "Market rate",
                "notes"           : "Verify grade with product spec"
            },
            {
                "material"        : "Secondary/Auxiliary Material",
                "quantity_per_unit": "0.5 kg",
                "unit"            : "kg",
                "supplier_type"   : "Local Supplier",
                "estimated_cost"  : "Market rate",
                "notes"           : ""
            },
            {
                "material"        : "Packaging Material",
                "quantity_per_unit": "1 set",
                "unit"            : "set",
                "supplier_type"   : "Packaging Vendor",
                "estimated_cost"  : "₹5–15 per unit",
                "notes"           : "Includes box, label, seal"
            },
        ]

    return {
        "product"          : product,
        "matched_entry"    : matched_name or "N/A",
        "data_source"      : data_source,
        "total_line_items" : len(bom_items),
        "bill_of_materials": bom_items,
        "note": "BOM is indicative. Validate quantities against production trials."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. QUALITY STANDARD TOOL
# ─────────────────────────────────────────────────────────────────────────────
@tool("quality_standard_tool", args_schema=ProductInput)
def quality_standard_tool(product: str) -> dict:
    """Returns BIS standards, testing procedures, and QA checkpoints."""
    print("\n[TOOL CALLED] -> quality_standard_tool")

    kb_dir = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    bis_standards      = []
    testing_procedures = []
    qa_checkpoints     = []
    certifications     = []
    data_source        = "knowledge_base"

    if content:
        sections = extract_all_sections(content)

        for sec_key, sec_val in sections.items():
            if any(k in sec_key for k in ["quality", "bis", "standard", "certification", "testing", "qa"]):

                # Extract BIS standard numbers: IS 1234, BIS 5678:2023
                bis_hits = re.findall(
                    r'(?:IS|BIS|ISI|ISO|IEC|EN)\s*[\d\-:]+(?::\d{4})?',
                    sec_val,
                    re.IGNORECASE
                )
                bis_standards.extend(bis_hits)

                # Extract testing procedures as list items
                if any(k in sec_key for k in ["test", "procedure", "check"]):
                    testing_procedures.extend(parse_list_items(sec_val))

                # Extract QA checkpoints
                if any(k in sec_key for k in ["qa", "quality", "checkpoint", "inspection"]):
                    qa_checkpoints.extend(parse_list_items(sec_val))

                # Extract certifications
                cert_hits = re.findall(
                    r'(?:BIS|ISO|CE|FSSAI|CPCB|IEC|UL|RoHS|REACH|GMP|HACCP)\s*[\w\-:\d]*',
                    sec_val,
                    re.IGNORECASE
                )
                certifications.extend(cert_hits)

    if not bis_standards and not testing_procedures:
        data_source = "generic_fallback"

    # ── Fallback ──────────────────────────────────────────────────────────
    if not bis_standards:
        bis_standards = [f"Refer BIS portal for applicable IS standard for {product}"]

    if not testing_procedures:
        testing_procedures = [
            "Incoming Raw Material Inspection (Visual + Lab)",
            "In-Process Quality Check (Dimensional / Functional)",
            "Finished Goods Testing (Performance / Safety)",
            "Destructive / Non-Destructive Testing (as applicable)",
            "Packaging Integrity Check",
        ]

    if not qa_checkpoints:
        qa_checkpoints = [
            "Goods Inward (GIN) Inspection",
            "First Article Inspection (FAI)",
            "In-Process Checkpoint at 50% batch completion",
            "Pre-Dispatch Final Inspection",
            "Customer Return / Rejection Analysis",
        ]

    return {
        "product"            : product,
        "matched_entry"      : matched_name or "N/A",
        "data_source"        : data_source,
        "bis_standards"      : list(set(bis_standards)),
        "certifications"     : list(set(certifications)) or ["Verify with product category regulator"],
        "testing_procedures" : testing_procedures,
        "qa_checkpoints"     : qa_checkpoints,
        "note": "Always verify current BIS standards at bis.gov.in before submission."
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. ENERGY REQUIREMENT CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────
@tool("energy_requirement_calculator", args_schema=ProductInput)
def energy_requirement_calculator(product: str) -> dict:
    """Calculates electricity load, water usage, and compressed air requirements."""
    print("\n[TOOL CALLED] -> energy_requirement_calculator")

    kb_dir = get_manufacturing_kb_dir()
    matched_name, content = fetch_product_content(product, kb_dir)

    energy_data = {}
    data_source = "knowledge_base"

    if content:
        section = extract_section(
            content,
            "energy", "utilities", "power", "electricity",
            "water", "utility requirements", "infrastructure"
        )

        if section:
            # Key:Value extraction for utility specs
            kv_pattern = re.compile(r'(.{3,40}?)\s*[:–]\s*(.+)', re.MULTILINE)
            for match in kv_pattern.finditer(section):
                key = match.group(1).strip().lower()
                val = match.group(2).strip()

                if any(k in key for k in ["electricity", "power", "load", "kw", "kva"]):
                    energy_data["electricity_load"] = val
                elif any(k in key for k in ["water", "litre", "liter", "kld"]):
                    energy_data["water_usage"] = val
                elif any(k in key for k in ["air", "cfm", "compressed"]):
                    energy_data["compressed_air"] = val
                elif any(k in key for k in ["manpower", "operator", "worker", "staff"]):
                    energy_data["manpower_per_shift"] = val
                elif any(k in key for k in ["fuel", "gas", "lpg", "diesel"]):
                    energy_data["fuel_requirement"] = val
                elif any(k in key for k in ["effluent", "waste", "sewage"]):
                    energy_data["effluent_generation"] = val
        else:
            data_source = "generic_fallback"
    else:
        data_source = "generic_fallback"

    # ── Fallback ──────────────────────────────────────────────────────────
    fallback = {
        "electricity_load"    : "50–150 kW (verify with machinery specs)",
        "water_usage"         : "1000–3000 Litres/day",
        "compressed_air"      : "50–150 CFM at 7 bar",
        "manpower_per_shift"  : "8–15 operators/shift",
        "fuel_requirement"    : "As per process (LPG/HSD if applicable)",
        "effluent_generation" : "Minimal (dry process) / Refer CPCB norms",
    }

    for key, fallback_val in fallback.items():
        if key not in energy_data:
            energy_data[key] = fallback_val

    # Estimate monthly cost if electricity load is parsed
    monthly_cost_estimate = None
    elec_str = energy_data.get("electricity_load", "")
    kw_match = re.search(r'(\d+)', elec_str)
    if kw_match:
        kw             = int(kw_match.group(1))
        hrs_per_month  = 26 * 8          # 26 working days × 8 hrs
        units_per_month = kw * hrs_per_month
        rate_per_unit  = 8               # ₹8/unit avg industrial tariff India
        monthly_cost_estimate = f"~₹{(units_per_month * rate_per_unit) / 100000:.1f} Lakhs/month"

    return {
        "product"                : product,
        "matched_entry"          : matched_name or "N/A",
        "data_source"            : data_source,
        **energy_data,
        "estimated_monthly_power_cost": monthly_cost_estimate or "Calculate after load finalization",
        "note": (
            "Load calculations are estimates. Get a certified electrical consultant "
            "for actual DG sizing, transformer capacity, and DISCOM connection approval."
        )
    }


# ─────────────────────────────────────────────────────────────────────────────
manufacturing_tools_list = [
    manufacturing_rag,
    machinery_recommendation,
    production_flow_generator,
    factory_layout_generator,
    bom_generator,
    quality_standard_tool,
    energy_requirement_calculator,
]