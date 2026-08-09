"""
Financial Engine — CAPEX, OPEX, Revenue, ROI, and scenario comparison.

All monetary values are in Indian Rupees (INR).
This version aligns finance with the richer simulation outputs:
- input-vs-good-unit economics
- maintenance and inventory carrying costs
- depreciation
- scrap / quality burden
- scenario CAPEX derived from the same base model
"""
from .models import FactoryConfig, SimulationResult, FinancialSummary


# ─────────────────────────────────────────────────────────────────────────────
# CAPEX ESTIMATION
# ─────────────────────────────────────────────────────────────────────────────

def _machine_cost(config: FactoryConfig) -> float:
    return sum(
        step.machine.cost_inr * step.machine.quantity
        for step in config.processes
    ) if config.processes else config.budget_inr * 0.40


def estimate_capex(config: FactoryConfig, simulation: SimulationResult) -> dict:
    """
    Estimate total capital expenditure.

    Components:
    - Machine/equipment cost
    - Civil construction
    - Misc infra
    - Working capital based on richer monthly opex drivers
    """
    machine_cost = _machine_cost(config)
    civil_cost = config.total_area_sqft * 1800.0
    misc_infra = (machine_cost + civil_cost) * 0.15

    monthly_raw_material = _estimate_raw_material_cost(config, simulation)
    monthly_labour = simulation.total_workers * config.labour_cost_per_worker_month_inr
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
    Raw material should be based on total input units needed, not only saleable units,
    so scrap/yield losses are priced in.
    """
    monthly_input_units = simulation.monthly_input_units_required or simulation.effective_throughput_per_month
    return monthly_input_units * config.selling_price_per_unit * config.raw_material_cost_ratio


def _estimate_maintenance_cost(config: FactoryConfig) -> float:
    """Assume annual maintenance = 6% of machine asset value."""
    return _machine_cost(config) * 0.06 / 12.0


def _estimate_inventory_carrying_cost(config: FactoryConfig, simulation: SimulationResult) -> float:
    """Simple carrying cost on one month of RM + finished goods buffer."""
    raw_material = _estimate_raw_material_cost(config, simulation)
    fg_value = simulation.effective_throughput_per_month * config.selling_price_per_unit * 0.08
    inventory_base = raw_material + fg_value
    return inventory_base * 0.015


def _estimate_qc_and_scrap_cost(config: FactoryConfig, simulation: SimulationResult) -> float:
    """
    Additional quality burden on top of raw material:
    inspection consumables + disposal + rework handling.
    """
    scrap_material_loss = simulation.monthly_scrap_units * config.selling_price_per_unit * config.raw_material_cost_ratio * 0.10
    qc_overhead = simulation.effective_throughput_per_month * config.selling_price_per_unit * 0.01
    return scrap_material_loss + qc_overhead


def _estimate_depreciation_monthly(config: FactoryConfig, capex_breakdown: dict) -> float:
    """
    Straight-line approximation:
    - machines over 8 years
    - civil over 20 years
    - misc infra over 10 years
    """
    machine_dep = capex_breakdown["machine_cost_inr"] / (8 * 12)
    civil_dep = capex_breakdown["civil_construction_inr"] / (20 * 12)
    misc_dep = capex_breakdown["misc_infra_inr"] / (10 * 12)
    return machine_dep + civil_dep + misc_dep


def estimate_opex(config: FactoryConfig, simulation: SimulationResult, capex_breakdown: dict) -> dict:
    """Monthly operating expenditure breakdown."""
    labour_cost = simulation.total_workers * config.labour_cost_per_worker_month_inr
    power_cost = simulation.estimated_monthly_power_cost_inr
    raw_material = _estimate_raw_material_cost(config, simulation)
    maintenance = _estimate_maintenance_cost(config)
    inventory_carrying = _estimate_inventory_carrying_cost(config, simulation)
    qc_and_scrap = _estimate_qc_and_scrap_cost(config, simulation)

    overhead_base = labour_cost + power_cost + raw_material + maintenance + inventory_carrying + qc_and_scrap
    overhead = overhead_base * 0.08
    depreciation = _estimate_depreciation_monthly(config, capex_breakdown)

    total_opex = overhead_base + overhead + depreciation

    return {
        "labour_cost_monthly_inr": round(labour_cost, 0),
        "power_cost_monthly_inr": round(power_cost, 0),
        "raw_material_cost_monthly_inr": round(raw_material, 0),
        "maintenance_cost_monthly_inr": round(maintenance, 0),
        "inventory_carrying_cost_monthly_inr": round(inventory_carrying, 0),
        "qc_and_scrap_cost_monthly_inr": round(qc_and_scrap, 0),
        "depreciation_monthly_inr": round(depreciation, 0),
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
    monthly_revenue = simulation.effective_throughput_per_month * config.selling_price_per_unit
    total_opex = opex["total_opex_monthly_inr"]
    monthly_profit = monthly_revenue - total_opex
    gross_margin = (monthly_profit / monthly_revenue * 100.0) if monthly_revenue > 0 else 0.0

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
    if monthly_profit <= 0 or total_capex <= 0:
        return {
            "break_even_months": 999.0,
            "annual_roi_percent": 0.0,
        }
    break_even_months = total_capex / monthly_profit
    annual_roi = (monthly_profit * 12.0 / total_capex) * 100.0
    return {
        "break_even_months": round(break_even_months, 1),
        "annual_roi_percent": round(annual_roi, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO COMPARISON
# ─────────────────────────────────────────────────────────────────────────────

def _build_scenario(
    label: str,
    units_factor: float,
    config: FactoryConfig,
    simulation: SimulationResult,
    base_capex: float,
    base_machine_cost: float,
) -> dict:
    """Build a single scenario by scaling production units consistently."""
    scaled_good_units = simulation.effective_throughput_per_month * units_factor
    scaled_input_units = simulation.monthly_input_units_required * units_factor

    raw_material = scaled_input_units * config.selling_price_per_unit * config.raw_material_cost_ratio
    labour = simulation.total_workers * config.labour_cost_per_worker_month_inr * (0.85 + 0.15 * units_factor)
    power = simulation.estimated_monthly_power_cost_inr * (units_factor ** 0.85)
    maintenance = base_machine_cost * (0.06 / 12.0) * (0.9 + 0.1 * units_factor)
    inventory_carrying = (raw_material + scaled_good_units * config.selling_price_per_unit * 0.08) * 0.015
    qc_and_scrap = (simulation.monthly_scrap_units * units_factor) * config.selling_price_per_unit * config.raw_material_cost_ratio * 0.10
    qc_and_scrap += scaled_good_units * config.selling_price_per_unit * 0.01
    overhead = (labour + power + raw_material + maintenance + inventory_carrying + qc_and_scrap) * 0.08

    revenue = scaled_good_units * config.selling_price_per_unit

    scenario_capex = base_capex * (units_factor ** 0.65)
    depreciation = scenario_capex * 0.045 / 12.0
    opex = labour + power + raw_material + maintenance + inventory_carrying + qc_and_scrap + overhead + depreciation
    profit = revenue - opex
    gross_margin = (profit / revenue * 100.0) if revenue > 0 else 0.0
    break_even = scenario_capex / profit if profit > 0 else 999.0
    roi = (profit * 12 / scenario_capex * 100.0) if scenario_capex > 0 else 0.0

    return {
        "label": label,
        "monthly_units": round(scaled_good_units, 0),
        "capex_inr": round(scenario_capex, 0),
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
    """Compute the complete financial picture including three scenarios."""
    capex_breakdown = estimate_capex(config, simulation)
    opex_breakdown = estimate_opex(config, simulation, capex_breakdown)
    revenue_data = calculate_revenue_and_profit(config, simulation, opex_breakdown)
    roi_data = calculate_roi(
        capex_breakdown["total_capex_inr"],
        revenue_data["monthly_profit_inr"],
    )

    base_capex = capex_breakdown["total_capex_inr"]
    base_machine_cost = capex_breakdown["machine_cost_inr"]
    conservative = _build_scenario("Conservative (60%)", 0.60, config, simulation, base_capex, base_machine_cost)
    balanced = _build_scenario("Balanced (100%)", 1.00, config, simulation, base_capex, base_machine_cost)
    aggressive = _build_scenario("Aggressive (150%)", 1.50, config, simulation, base_capex, base_machine_cost)

    return FinancialSummary(
        total_capex_inr=capex_breakdown["total_capex_inr"],
        machine_cost_inr=capex_breakdown["machine_cost_inr"],
        civil_construction_inr=capex_breakdown["civil_construction_inr"],
        misc_infra_inr=capex_breakdown["misc_infra_inr"],
        working_capital_inr=capex_breakdown["working_capital_inr"],
        monthly_opex_inr=opex_breakdown["total_opex_monthly_inr"],
        labour_cost_monthly_inr=opex_breakdown["labour_cost_monthly_inr"],
        power_cost_monthly_inr=opex_breakdown["power_cost_monthly_inr"],
        raw_material_cost_monthly_inr=opex_breakdown["raw_material_cost_monthly_inr"],
        maintenance_cost_monthly_inr=opex_breakdown["maintenance_cost_monthly_inr"],
        inventory_carrying_cost_monthly_inr=opex_breakdown["inventory_carrying_cost_monthly_inr"],
        qc_and_scrap_cost_monthly_inr=opex_breakdown["qc_and_scrap_cost_monthly_inr"],
        depreciation_monthly_inr=opex_breakdown["depreciation_monthly_inr"],
        monthly_revenue_inr=revenue_data["monthly_revenue_inr"],
        monthly_profit_inr=revenue_data["monthly_profit_inr"],
        gross_margin_percent=revenue_data["gross_margin_percent"],
        break_even_months=roi_data["break_even_months"],
        annual_roi_percent=roi_data["annual_roi_percent"],
        conservative=conservative,
        balanced=balanced,
        aggressive=aggressive,
    )
