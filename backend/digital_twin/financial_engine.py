"""
Financial Engine — CAPEX, OPEX, Revenue, ROI, and scenario comparison.

All monetary values are in Indian Rupees (INR).
"""
from .models import FactoryConfig, SimulationResult, FinancialSummary


# ─────────────────────────────────────────────────────────────────────────────
# CAPEX ESTIMATION
# ─────────────────────────────────────────────────────────────────────────────

def estimate_capex(config: FactoryConfig, simulation: SimulationResult) -> dict:
    """
    Estimate total capital expenditure.
    
    Components:
    - Machine/equipment cost (from config)
    - Civil construction (₹1,800/sqft industrial standard)
    - Working capital (3 months of raw material + wages)
    - Misc (electrical, plumbing, safety) — 15% of civil + machines
    """
    # Machine costs
    machine_cost = sum(
        step.machine.cost_inr * step.machine.quantity
        for step in config.processes
    ) if config.processes else config.budget_inr * 0.40

    # Civil construction (₹1,800/sqft for industrial shed in India)
    civil_cost = config.total_area_sqft * 1800.0

    # Electrical, fire safety, plumbing = 15% of (machines + civil)
    misc_infra = (machine_cost + civil_cost) * 0.15

    # Working capital = 3 months raw material + 3 months labour
    monthly_raw_material = _estimate_raw_material_cost(config, simulation)
    monthly_labour = simulation.total_workers * 18000  # avg ₹18k/worker/month
    working_capital = (monthly_raw_material + monthly_labour) * 3

    total_capex = machine_cost + civil_cost + misc_infra + working_capital

    return {
        "machine_cost_inr": round(machine_cost, 0),
        "civil_construction_inr": round(civil_cost, 0),
        "misc_infra_inr": round(misc_infra, 0),
        "working_capital_inr": round(working_capital, 0),
        "total_capex_inr": round(total_capex, 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# OPEX ESTIMATION
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_raw_material_cost(config: FactoryConfig, simulation: SimulationResult) -> float:
    """
    Rough raw material cost: assume RM = 45% of selling price × units produced.
    This is a typical ratio for light manufacturing.
    """
    monthly_units = simulation.effective_throughput_per_month
    return monthly_units * config.selling_price_per_unit * 0.45


def estimate_opex(config: FactoryConfig, simulation: SimulationResult) -> dict:
    """
    Monthly operating expenditure breakdown.
    """
    labour_cost = simulation.total_workers * 18000  # ₹18k/worker/month avg
    power_cost = simulation.estimated_monthly_power_cost_inr
    raw_material = _estimate_raw_material_cost(config, simulation)
    # Packaging, consumables, maintenance, rent (if leased)
    overhead = (labour_cost + power_cost + raw_material) * 0.12

    total_opex = labour_cost + power_cost + raw_material + overhead

    return {
        "labour_cost_monthly_inr": round(labour_cost, 0),
        "power_cost_monthly_inr": round(power_cost, 0),
        "raw_material_cost_monthly_inr": round(raw_material, 0),
        "overhead_monthly_inr": round(overhead, 0),
        "total_opex_monthly_inr": round(total_opex, 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# REVENUE & PROFIT
# ─────────────────────────────────────────────────────────────────────────────

def calculate_revenue_and_profit(
    config: FactoryConfig,
    simulation: SimulationResult,
    opex: dict,
) -> dict:
    monthly_revenue = (
        simulation.effective_throughput_per_month * config.selling_price_per_unit
    )
    total_opex = opex["total_opex_monthly_inr"]
    monthly_profit = monthly_revenue - total_opex
    gross_margin = (monthly_profit / monthly_revenue * 100) if monthly_revenue > 0 else 0

    return {
        "monthly_revenue_inr": round(monthly_revenue, 0),
        "monthly_profit_inr": round(monthly_profit, 0),
        "gross_margin_percent": round(gross_margin, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROI & BREAK-EVEN
# ─────────────────────────────────────────────────────────────────────────────

def calculate_roi(total_capex: float, monthly_profit: float) -> dict:
    """Break-even in months; annual ROI as % of CAPEX."""
    if monthly_profit <= 0:
        return {
            "break_even_months": float("inf"),
            "annual_roi_percent": 0.0,
        }
    break_even_months = total_capex / monthly_profit
    annual_roi = (monthly_profit * 12 / total_capex * 100) if total_capex > 0 else 0
    return {
        "break_even_months": round(break_even_months, 1),
        "annual_roi_percent": round(annual_roi, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO COMPARISON
# ─────────────────────────────────────────────────────────────────────────────

def _build_scenario(label: str, units_factor: float, config: FactoryConfig, simulation: SimulationResult) -> dict:
    """Build a single scenario by scaling production units."""
    scaled_units = simulation.effective_throughput_per_month * units_factor
    raw_material = scaled_units * config.selling_price_per_unit * 0.45
    labour = simulation.total_workers * units_factor * 18000
    power = simulation.estimated_monthly_power_cost_inr * (units_factor ** 0.7)
    overhead = (labour + power + raw_material) * 0.12
    opex = raw_material + labour + power + overhead
    revenue = scaled_units * config.selling_price_per_unit
    profit = revenue - opex
    gross_margin = (profit / revenue * 100) if revenue > 0 else 0

    # Capex scales roughly with machine count (not linearly — economies of scale)
    base_capex = config.budget_inr
    capex = base_capex * (units_factor ** 0.65)
    break_even = capex / profit if profit > 0 else 999
    roi = (profit * 12 / capex * 100) if capex > 0 else 0

    return {
        "label": label,
        "monthly_units": round(scaled_units, 0),
        "capex_inr": round(capex, 0),
        "monthly_opex_inr": round(opex, 0),
        "monthly_revenue_inr": round(revenue, 0),
        "monthly_profit_inr": round(profit, 0),
        "gross_margin_percent": round(gross_margin, 1),
        "break_even_months": round(break_even, 1),
        "annual_roi_percent": round(roi, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN: FULL FINANCIAL MODEL
# ─────────────────────────────────────────────────────────────────────────────

def full_financial_model(
    config: FactoryConfig,
    simulation: SimulationResult,
) -> FinancialSummary:
    """
    Compute the complete financial picture including three scenarios.
    """
    capex_breakdown = estimate_capex(config, simulation)
    opex_breakdown = estimate_opex(config, simulation)
    revenue_data = calculate_revenue_and_profit(config, simulation, opex_breakdown)
    roi_data = calculate_roi(
        capex_breakdown["total_capex_inr"],
        revenue_data["monthly_profit_inr"],
    )

    conservative = _build_scenario("Conservative (60%)", 0.60, config, simulation)
    balanced = _build_scenario("Balanced (100%)", 1.00, config, simulation)
    aggressive = _build_scenario("Aggressive (150%)", 1.50, config, simulation)

    return FinancialSummary(
        total_capex_inr=capex_breakdown["total_capex_inr"],
        machine_cost_inr=capex_breakdown["machine_cost_inr"],
        civil_construction_inr=capex_breakdown["civil_construction_inr"],
        working_capital_inr=capex_breakdown["working_capital_inr"],
        monthly_opex_inr=opex_breakdown["total_opex_monthly_inr"],
        labour_cost_monthly_inr=opex_breakdown["labour_cost_monthly_inr"],
        power_cost_monthly_inr=opex_breakdown["power_cost_monthly_inr"],
        raw_material_cost_monthly_inr=opex_breakdown["raw_material_cost_monthly_inr"],
        monthly_revenue_inr=revenue_data["monthly_revenue_inr"],
        monthly_profit_inr=revenue_data["monthly_profit_inr"],
        gross_margin_percent=revenue_data["gross_margin_percent"],
        break_even_months=roi_data["break_even_months"],
        annual_roi_percent=roi_data["annual_roi_percent"],
        conservative=conservative,
        balanced=balanced,
        aggressive=aggressive,
    )
