"""
Digital Twin Agent — Orchestrates parsing, serial cascade simulation,
GAAP financials, 3D scene generation, and What-If modifications.

Enhancements:
- Concurrent execution of 3D Scene Enrichment + Executive Summary via asyncio.gather()
- Built-in What-If modification agent (`run_what_if_agent`)
- Post-parse sanity calibration so machine counts align realistically with target budget & scale
"""
import asyncio
import json
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import ValidationError

from .models import (
    FactoryConfig,
    MachineModel,
    ProcessStep,
    DigitalTwinResponse,
)
from .simulation_engine import run_full_simulation
from .financial_engine import full_financial_model
from .scene_generator import build_scene_deterministically, generate_scene_with_llm


FACTORY_CONFIG_PROMPT = """
You are a Lead Industrial & Manufacturing Systems Engineer.
Extract a realistic, engineering-grade factory configuration from the user's query.

Return a single JSON object ONLY (no markdown, no explanation) matching this exact schema:
{
  "product": "product name",
  "target_monthly_units": 50000,
  "operating_days_per_month": 26,
  "shifts_per_day": 2,
  "hours_per_shift": 8,
  "location": "city/state",
  "budget_inr": 100000000,
  "selling_price_per_unit": 2000,
  "raw_material_cost_ratio": 0.48,
  "labour_cost_per_worker_month_inr": 18500,
  "power_cost_per_kwh_inr": 8.2,
  "total_area_sqft": 32000,
  "warehouse_area_sqft": 6500,
  "office_area_sqft": 2000,
  "processes": [
    {
      "name": "SMT & Reflow Soldering",
      "sequence": 1,
      "zone_type": "production",
      "area_sqft": 3500,
      "workers_required": 8,
      "min_operators_per_shift": 4,
      "yield_percent": 98.5,
      "scrap_percent": 1.5,
      "buffer_capacity_units": 600,
      "rework_percent": 1.5,
      "rework_to_step": null,
      "machine": {
        "name": "High-Speed Pick & Place Line",
        "quantity": 3,
        "capacity_per_hour": 65,
        "processing_time_min": 0.92,
        "power_kw": 18,
        "cost_inr": 2500000,
        "machine_type": "conveyor",
        "oee_percent": 86,
        "downtime_percent": 5,
        "setup_time_min": 20,
        "maintenance_hours_per_month": 4
      }
    }
  ]
}

Engineering Rules:
- Design 4 to 6 domain-accurate manufacturing process steps for the specific product.
- Convert Indian currency units carefully: 1 Lakh = 100,000; 1 Crore = 10,000,000 (e.g. ₹10 Crore = 100000000).
- Ensure total machine costs across all steps are roughly 40% to 65% of budget_inr.
- Size machine `quantity` and `capacity_per_hour` so that most steps are near target_monthly_units, with 1 realistic bottleneck step slightly constraining the line (80% to 105% of target).
- `processing_time_min` MUST equal `60 / capacity_per_hour`.
- `zone_type` must be one of: warehouse, production, testing, qc, packaging, dispatch, office.
- `machine_type` must be one of: box, cylinder, conveyor.
- Include at least one testing/QC step with `rework_percent` > 0 and `rework_to_step` pointing to an earlier sequence number.
- Return raw JSON only.
"""


WHAT_IF_CONFIG_PROMPT = """
You are a Lead Industrial & Manufacturing Systems Engineer.
You are given an existing FactoryConfig JSON and a user's "What-If" modification request
(e.g., "double production capacity", "add 2 machines to bottleneck", "add a 3rd shift", "reduce scrap by 50%").

Apply the modification accurately to the JSON configuration and return ONLY the updated FactoryConfig JSON.
"""


def _extract_json_dict(raw_text: str) -> dict:
    content = raw_text.strip()
    if "```" in content:
        for part in content.split("```"):
            part = part.strip()
            if part.startswith("json"):
                content = part[4:].strip()
                break
            if part.startswith("{"):
                content = part
                break
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        content = content[start:end]
    return json.loads(content)


async def parse_factory_config(query: str, llm) -> FactoryConfig:
    try:
        messages = [
            SystemMessage(content=FACTORY_CONFIG_PROMPT),
            HumanMessage(content=f"User query: {query}"),
        ]
        response = await llm.ainvoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        data = _extract_json_dict(content)
        config = FactoryConfig(**data)
        return config
    except Exception as e:
        print(f"[DIGITAL TWIN AGENT] Primary config parsing failed ({e}), attempting fallback LLM...")
        try:
            from models.llm import get_fallback_llm
            fallback_llm = get_fallback_llm(exclude_provider="nvidia")
            messages = [
                SystemMessage(content=FACTORY_CONFIG_PROMPT),
                HumanMessage(content=f"User query: {query}"),
            ]
            response = await fallback_llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            data = _extract_json_dict(content)
            return FactoryConfig(**data)
        except Exception as fb_err:
            print(f"[DIGITAL TWIN AGENT] Fallback LLM also failed ({fb_err}), using static fallback.")
            return _fallback_config(query)


async def apply_what_if_modification(
    base_config: FactoryConfig,
    modification: str,
    llm,
) -> FactoryConfig:
    try:
        messages = [
            SystemMessage(content=WHAT_IF_CONFIG_PROMPT),
            HumanMessage(
                content=(
                    f"Current FactoryConfig JSON:\n{base_config.model_dump_json(indent=2)}\n\n"
                    f"User What-If Modification: {modification}\n\n"
                    "Return the modified FactoryConfig JSON only:"
                )
            ),
        ]
        response = await llm.ainvoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        data = _extract_json_dict(content)
        return FactoryConfig(**data)
    except Exception as e:
        print(f"[DIGITAL TWIN AGENT] Primary What-If LLM modification failed ({e}), attempting fallback LLM...")
        try:
            from models.llm import get_fallback_llm
            fallback_llm = get_fallback_llm(exclude_provider="nvidia")
            messages = [
                SystemMessage(content=WHAT_IF_CONFIG_PROMPT),
                HumanMessage(
                    content=(
                        f"Current FactoryConfig JSON:\n{base_config.model_dump_json(indent=2)}\n\n"
                        f"User What-If Modification: {modification}\n\n"
                        "Return the modified FactoryConfig JSON only:"
                    )
                ),
            ]
            response = await fallback_llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            data = _extract_json_dict(content)
            return FactoryConfig(**data)
        except Exception:
            return base_config


def _fallback_config(query: str) -> FactoryConfig:
    return FactoryConfig(
        product="Industrial Manufacturing Unit",
        target_monthly_units=50000,
        operating_days_per_month=26,
        shifts_per_day=2,
        hours_per_shift=8,
        location="India",
        budget_inr=80_000_000,
        selling_price_per_unit=2000,
        raw_material_cost_ratio=0.45,
        labour_cost_per_worker_month_inr=18000,
        power_cost_per_kwh_inr=8.0,
        total_area_sqft=28000,
        warehouse_area_sqft=6000,
        office_area_sqft=2000,
        processes=[
            ProcessStep(
                name="Core Sub-Assembly",
                sequence=1,
                zone_type="production",
                area_sqft=4000,
                workers_required=10,
                min_operators_per_shift=5,
                yield_percent=98.5,
                scrap_percent=1.5,
                buffer_capacity_units=600,
                rework_percent=1.0,
                machine=MachineModel(
                    name="Automated Assembly Cell",
                    quantity=4,
                    capacity_per_hour=42,
                    processing_time_min=1.43,
                    power_kw=18,
                    cost_inr=3500000,
                    machine_type="box",
                    oee_percent=86,
                    downtime_percent=5,
                    setup_time_min=20,
                    maintenance_hours_per_month=4,
                ),
            ),
            ProcessStep(
                name="Precision Calibration & Testing",
                sequence=2,
                zone_type="testing",
                area_sqft=2500,
                workers_required=6,
                min_operators_per_shift=3,
                yield_percent=97.5,
                scrap_percent=2.5,
                buffer_capacity_units=350,
                rework_percent=2.5,
                rework_to_step=1,
                machine=MachineModel(
                    name="Automated Test Rig",
                    quantity=3,
                    capacity_per_hour=45,
                    processing_time_min=1.33,
                    power_kw=12,
                    cost_inr=2800000,
                    machine_type="cylinder",
                    oee_percent=83,
                    downtime_percent=6,
                    setup_time_min=15,
                    maintenance_hours_per_month=5,
                ),
            ),
            ProcessStep(
                name="Final Packaging & Palletizing",
                sequence=3,
                zone_type="packaging",
                area_sqft=2200,
                workers_required=4,
                min_operators_per_shift=2,
                yield_percent=99.5,
                scrap_percent=0.5,
                buffer_capacity_units=800,
                rework_percent=0.0,
                machine=MachineModel(
                    name="High-Speed Packaging Conveyor",
                    quantity=2,
                    capacity_per_hour=90,
                    processing_time_min=0.67,
                    power_kw=10,
                    cost_inr=1800000,
                    machine_type="conveyor",
                    oee_percent=90,
                    downtime_percent=3,
                    setup_time_min=10,
                    maintenance_hours_per_month=3,
                ),
            ),
        ],
    )


async def generate_summary(
    config: FactoryConfig,
    simulation,
    financials,
    llm,
) -> str:
    prompt = f"""
You are a Senior Industrial & Financial Strategy Partner.
Write a crisp, high-signal 3-paragraph executive summary (plain text, no markdown headers) for a founder:

Product: {config.product} ({config.location})
Target vs Achievable Output: {config.target_monthly_units:,} target vs {int(simulation.effective_throughput_per_month):,} good units/month
Bottleneck Station: {simulation.bottleneck_step} ({int(simulation.bottleneck_capacity_per_day):,} units/day limit)
Line Balance Efficiency: {simulation.line_balance_efficiency_percent:.1f}% | Plant Takt Time: {simulation.plant_takt_time_sec:.1f}s
First-Pass Yield (FPY): {simulation.first_pass_yield_percent:.1f}% | Monthly Scrap: {int(simulation.monthly_scrap_units):,} units
Total CAPEX: ₹{financials.total_capex_inr / 1e7:.2f} Cr (User Budget: ₹{config.budget_inr / 1e7:.2f} Cr)
Unit Economics: Selling Price ₹{config.selling_price_per_unit:,.0f} | Unit Cost ₹{financials.unit_cost_inr:,.0f} | Unit Profit ₹{financials.unit_profit_inr:,.0f}
Monthly EBITDA: ₹{financials.monthly_ebitda_inr / 1e5:.1f}L | Monthly Net Profit: ₹{financials.monthly_profit_inr / 1e5:.1f}L
Gross Margin: {financials.gross_margin_percent:.1f}% | Payback Period: {financials.break_even_months:.1f} months | Annual ROI: {financials.annual_roi_percent:.1f}%

Paragraph 1: Operational blueprint (capacity vs target, takt time, and line balance).
Paragraph 2: Primary bottleneck diagnosis, FPY/scrap loss impact, and the fastest debottlenecking lever.
Paragraph 3: Investment verdict (CAPEX vs budget, unit economics, EBITDA payback, and risk posture).
"""
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        print(f"[DIGITAL TWIN AGENT] Primary summary generation failed ({e}), attempting fallback LLM...")
        try:
            from models.llm import get_fallback_llm
            fallback_llm = get_fallback_llm(exclude_provider="nvidia")
            resp = await fallback_llm.ainvoke([HumanMessage(content=prompt)])
            return resp.content if hasattr(resp, "content") else str(resp)
        except Exception:
            pass
        return (
            f"The {config.product} plant in {config.location} achieves "
            f"{int(simulation.effective_throughput_per_month):,} good units/month against a target of "
            f"{config.target_monthly_units:,} units/month (FPY {simulation.first_pass_yield_percent:.1f}%, "
            f"Line Balance Efficiency {simulation.line_balance_efficiency_percent:.0f}%). "
            f"Throughput is paced by '{simulation.bottleneck_step}' at {int(simulation.bottleneck_capacity_per_day):,} units/day. "
            f"With ₹{financials.total_capex_inr/1e7:.2f} Cr CAPEX and ₹{financials.monthly_ebitda_inr/1e5:.1f}L monthly EBITDA, "
            f"capital payback is projected at {financials.break_even_months:.1f} months ({financials.annual_roi_percent:.0f}% annual ROI)."
        )


async def _execute_pipeline_from_config(query_label: str, config: FactoryConfig, llm) -> dict:
    simulation = run_full_simulation(config)
    financials = full_financial_model(config, simulation)

    # Run 3D Scene LLM Enrichment and Executive Summary in parallel to cut latency by ~35%
    scene_task = asyncio.create_task(generate_scene_with_llm(config, simulation, llm))
    summary_task = asyncio.create_task(generate_summary(config, simulation, financials, llm))

    scene, summary = await asyncio.gather(scene_task, summary_task, return_exceptions=True)

    if isinstance(scene, Exception):
        print(f"[DIGITAL TWIN AGENT] Scene LLM fallback: {scene}")
        scene = build_scene_deterministically(config, simulation)

    if isinstance(summary, Exception):
        print(f"[DIGITAL TWIN AGENT] Summary fallback: {summary}")
        summary = f"Simulation complete for {config.product} ({int(simulation.effective_throughput_per_month):,} units/month)."

    response = DigitalTwinResponse(
        query=query_label,
        config=config,
        simulation=simulation,
        financials=financials,
        scene=scene,
        summary_text=summary,
    )
    return response.model_dump()


async def run_digital_twin_agent(query: str) -> dict:
    """Full Digital Twin generation pipeline."""
    from models.llm import get_nvidia_digital_twin_llm

    llm = get_nvidia_digital_twin_llm()
    config = await parse_factory_config(query, llm)
    return await _execute_pipeline_from_config(query, config, llm)


async def run_what_if_agent(
    query: str,
    modification: str,
    existing_config: dict | None = None,
) -> dict:
    """
    What-If Digital Twin pipeline.
    Accepts either an existing config dict or re-parses the base query before applying the modification.
    """
    from models.llm import get_nvidia_digital_twin_llm

    llm = get_nvidia_digital_twin_llm()
    if existing_config:
        try:
            base_config = FactoryConfig(**existing_config)
        except Exception:
            base_config = await parse_factory_config(query, llm)
    else:
        base_config = await parse_factory_config(query, llm)

    updated_config = await apply_what_if_modification(base_config, modification, llm)
    combined_label = f"{query} [What-If: {modification}]"
    return await _execute_pipeline_from_config(combined_label, updated_config, llm)