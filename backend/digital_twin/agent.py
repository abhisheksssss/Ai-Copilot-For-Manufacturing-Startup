"""
Digital Twin Agent — Orchestrates all steps to produce a complete Digital Twin.

Flow:
  1. Parse the user's natural-language query into a structured FactoryConfig (NVIDIA LLM)
  2. Run the mathematical simulation (SimulationEngine — pure Python)
  3. Run financial projections (FinancialEngine — pure Python)
  4. Generate the 3D scene descriptor (deterministic + NVIDIA LLM enrichment)
  5. Generate a plain-English summary (NVIDIA LLM)
  6. Return the complete DigitalTwinResponse

This version improves the twin by:
- extracting richer operational assumptions
- simulating setup, downtime, OEE, yield, and scrap
- aligning finance with input-unit economics
- surfacing better scene metadata
"""
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


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Parse user query → FactoryConfig
# ─────────────────────────────────────────────────────────────────────────────

FACTORY_CONFIG_PROMPT = """
You are an expert manufacturing process engineer.
Extract a structured factory configuration from the user's query.

Return a single JSON object ONLY (no markdown, no explanation) with this schema:
{
  "product": "product name",
  "target_monthly_units": 50000,
  "operating_days_per_month": 26,
  "shifts_per_day": 2,
  "hours_per_shift": 8,
  "location": "city/state",
  "budget_inr": 10000000,
  "selling_price_per_unit": 2000,
  "raw_material_cost_ratio": 0.45,
  "labour_cost_per_worker_month_inr": 18000,
  "power_cost_per_kwh_inr": 8,
  "total_area_sqft": 35000,
  "warehouse_area_sqft": 8000,
  "office_area_sqft": 2000,
  "processes": [
    {
      "name": "PCB Assembly",
      "sequence": 1,
      "zone_type": "production",
      "area_sqft": 3000,
      "workers_required": 8,
      "min_operators_per_shift": 4,
      "yield_percent": 98,
      "scrap_percent": 2,
      "buffer_capacity_units": 500,
      "rework_percent": 1,
      "rework_to_step": null,
      "machine": {
        "name": "PCB Assembly Machine",
        "quantity": 3,
        "capacity_per_hour": 60,
        "processing_time_min": 1,
        "power_kw": 15,
        "cost_inr": 800000,
        "machine_type": "box",
        "oee_percent": 85,
        "downtime_percent": 5,
        "setup_time_min": 20,
        "maintenance_hours_per_month": 4
      }
    }
  ]
}

Rules:
- Use 3-6 process steps appropriate for the product.
- Infer realistic values for Indian manufacturing.
- zone_type must be one of: warehouse, production, testing, qc, packaging, dispatch, office
- machine_type must be one of: box, cylinder, conveyor
- Keep yield_percent usually between 94 and 99.5 depending on process maturity.
- Keep downtime_percent usually between 3 and 12 unless the process is fragile.
- Keep oee_percent usually between 70 and 90.
- setup_time_min should reflect practical shift-level changeover time.
- min_operators_per_shift should be consistent with workers_required.
- Use null for rework_to_step when there is no rework loop.
- Return JSON only.
"""


async def parse_factory_config(query: str, llm) -> FactoryConfig:
    """
    Use NVIDIA LLM to extract a structured FactoryConfig from a free-text query.
    Falls back to a default config if parsing fails.
    """
    try:
        messages = [
            SystemMessage(content=FACTORY_CONFIG_PROMPT),
            HumanMessage(content=f"User query: {query}"),
        ]
        response = await llm.ainvoke(messages)
        content = response.content if hasattr(response, "content") else str(response)

        content = content.strip()
        if "```" in content:
            parts = content.split("```")
            for part in parts:
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

        data = json.loads(content)
        config = FactoryConfig(**data)
        print(
            f"[DIGITAL TWIN AGENT] Parsed config: {config.product}, "
            f"{config.target_monthly_units} units/month"
        )
        return config

    except (json.JSONDecodeError, ValidationError, Exception) as e:
        print(f"[DIGITAL TWIN AGENT] Config parsing failed ({e}), using fallback.")
        return _fallback_config(query)


def _fallback_config(query: str) -> FactoryConfig:
    """Sensible default when LLM extraction fails."""
    return FactoryConfig(
        product="Manufacturing Unit",
        target_monthly_units=50000,
        operating_days_per_month=26,
        shifts_per_day=2,
        hours_per_shift=8,
        location="India",
        budget_inr=10_000_000,
        selling_price_per_unit=2000,
        raw_material_cost_ratio=0.45,
        labour_cost_per_worker_month_inr=18000,
        power_cost_per_kwh_inr=8.0,
        total_area_sqft=30000,
        warehouse_area_sqft=8000,
        office_area_sqft=2000,
        processes=[
            ProcessStep(
                name="Assembly",
                sequence=1,
                zone_type="production",
                area_sqft=4000,
                workers_required=10,
                min_operators_per_shift=5,
                yield_percent=98.0,
                scrap_percent=2.0,
                buffer_capacity_units=600,
                rework_percent=1.0,
                machine=MachineModel(
                    name="Assembly Station",
                    quantity=4,
                    capacity_per_hour=60,
                    processing_time_min=1.0,
                    power_kw=20,
                    cost_inr=500000,
                    machine_type="box",
                    oee_percent=86,
                    downtime_percent=5,
                    setup_time_min=20,
                    maintenance_hours_per_month=4,
                ),
            ),
            ProcessStep(
                name="Testing & QC",
                sequence=2,
                zone_type="testing",
                area_sqft=2500,
                workers_required=6,
                min_operators_per_shift=3,
                yield_percent=97.0,
                scrap_percent=3.0,
                buffer_capacity_units=300,
                rework_percent=3.0,
                rework_to_step=1,
                machine=MachineModel(
                    name="Test Bench",
                    quantity=3,
                    capacity_per_hour=40,
                    processing_time_min=1.5,
                    power_kw=12,
                    cost_inr=600000,
                    machine_type="box",
                    oee_percent=82,
                    downtime_percent=7,
                    setup_time_min=15,
                    maintenance_hours_per_month=5,
                ),
            ),
            ProcessStep(
                name="Packaging",
                sequence=3,
                zone_type="packaging",
                area_sqft=2000,
                workers_required=4,
                min_operators_per_shift=2,
                yield_percent=99.0,
                scrap_percent=1.0,
                buffer_capacity_units=800,
                rework_percent=0.0,
                machine=MachineModel(
                    name="Packaging Line",
                    quantity=2,
                    capacity_per_hour=80,
                    processing_time_min=0.75,
                    power_kw=10,
                    cost_inr=350000,
                    machine_type="conveyor",
                    oee_percent=88,
                    downtime_percent=4,
                    setup_time_min=10,
                    maintenance_hours_per_month=3,
                ),
            ),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Generate plain-English summary
# ─────────────────────────────────────────────────────────────────────────────

async def generate_summary(
    config: FactoryConfig,
    simulation,
    financials,
    llm,
) -> str:
    """Use NVIDIA LLM to write a crisp business-oriented summary."""
    prompt = f"""
You are an expert manufacturing business consultant.
Write a concise 3-paragraph summary (no markdown headers, plain text) for a founder
considering this factory investment:

Product: {config.product}
Location: {config.location}
Budget: ₹{config.budget_inr / 1e7:.1f} crore
Target production: {config.target_monthly_units:,} units/month
Actual achievable: {int(simulation.effective_throughput_per_month):,} units/month
Bottleneck: {simulation.bottleneck_step}
Workers needed: {simulation.total_workers}
Overall yield: {simulation.overall_yield_percent:.1f}%
Monthly scrap units: {int(simulation.monthly_scrap_units):,}
Total CAPEX: ₹{financials.total_capex_inr / 1e7:.2f} crore
Monthly profit: ₹{financials.monthly_profit_inr / 1e5:.1f} lakh
Break-even: {financials.break_even_months:.0f} months
Annual ROI: {financials.annual_roi_percent:.0f}%

Key optimization suggestions:
{chr(10).join(simulation.optimization_suggestions)}

Paragraph 1: Summarize the factory setup and what it will produce.
Paragraph 2: Highlight the key bottleneck, yield losses, and how to improve them.
Paragraph 3: Give a financial verdict.
"""
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        print(f"[DIGITAL TWIN AGENT] Summary generation failed: {e}")
        return (
            f"The proposed {config.product} factory in {config.location} is designed to produce "
            f"{config.target_monthly_units:,} units/month. Current simulation shows "
            f"{int(simulation.effective_throughput_per_month):,} units/month achievable at an "
            f"overall yield of {simulation.overall_yield_percent:.1f}%. The main bottleneck is "
            f"{simulation.bottleneck_step}. With ₹{financials.total_capex_inr/1e7:.2f} crore CAPEX, "
            f"break-even is projected at {financials.break_even_months:.0f} months."
        )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN: run_digital_twin_agent
# ─────────────────────────────────────────────────────────────────────────────

async def run_digital_twin_agent(query: str) -> dict:
    """
    Full Digital Twin pipeline.

    Returns a dict matching DigitalTwinResponse that can be JSON-serialized
    and sent to the frontend.
    """
    from models.llm import get_nvidia_digital_twin_llm

    llm = get_nvidia_digital_twin_llm()

    print(f"\n=== DIGITAL TWIN AGENT: '{query[:80]}' ===")

    print("[1/5] Parsing factory configuration...")
    config = await parse_factory_config(query, llm)

    print("[2/5] Running production simulation...")
    simulation = run_full_simulation(config)
    print(
        f"      Bottleneck: {simulation.bottleneck_step} | "
        f"Throughput: {simulation.effective_throughput_per_month:.0f}/month | "
        f"Yield: {simulation.overall_yield_percent:.1f}%"
    )

    print("[3/5] Computing financial projections...")
    financials = full_financial_model(config, simulation)
    print(
        f"      CAPEX: Rs. {financials.total_capex_inr/1e7:.2f}Cr | "
        f"Break-even: {financials.break_even_months:.0f} months"
    )

    print("[4/5] Building 3D factory scene...")
    try:
        scene = await generate_scene_with_llm(config, simulation, llm)
    except Exception as e:
        print(f"      LLM scene enrichment failed ({e}), using deterministic scene.")
        scene = build_scene_deterministically(config, simulation)

    print("[5/5] Generating insight summary...")
    summary = await generate_summary(config, simulation, financials, llm)

    print("=== DIGITAL TWIN COMPLETE ===\n")

    response = DigitalTwinResponse(
        query=query,
        config=config,
        simulation=simulation,
        financials=financials,
        scene=scene,
        summary_text=summary,
    )

    return response.model_dump()
