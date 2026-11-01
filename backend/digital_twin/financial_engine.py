"""
Financial Engine — GAAP-aligned CAPEX, COGS, EBITDA, Net Profit, Unit Economics, and Scenarios.
"""
from .models import FactoryConfig, SimulationResult, FinancialSummary


def _machine_cost(config: FactoryConfig) -> float:
    return (
        sum(step.machine.cost_inr * step.machine.quantity for step in config.processes)
        if config.processes
        else config.budget_inr * 0.40
    )


def estimate_capex(config: FactoryConfig, simulation: SimulationResult) -> dict:
    """
    Estimate total capital expenditure and compare against user's target budget.
    """
    machine_cost = _machine_cost(config)
    # Scale civil cost intelligently so small-budget brownfield/leased setups aren't penalized with ₹5Cr+ land costs
    implied_civil = config.total_area_sqft * 1400.0
    max_reasonable_civil = max(config.budget_inr * 0.35, machine_cost * 0.55)
    civil_cost = min(implied_civil, max_reasonable_civil)

    misc_infra = (machine_cost + civil_cost) * 0.12  # Electrical transformer, piping, ETP, fire safety

    monthly_raw_material = _estimate_raw_material_cost(config, simulation)
    monthly_labour = simulation.total_workers * config.labour_cost_per_worker_month_inr
    # Net working capital (45 days of RM + labour buffer)
    working_capital = (monthly_raw_material + monthly_labour) * 1.5

    total_capex = machine_cost + civil_cost + misc_infra + working_capital
    budget_variance = config.budget_inr - total_capex

    return {
        "machine_cost_inr": round(machine_cost, 0),
        "civil_construction_inr": round(civil_cost, 0),
        "misc_infra_inr": round(misc_infra, 0),
        "working_capital_inr": round(working_capital, 0),
        "total_capex_inr": round(total_capex, 0),
        "budget_variance_inr": round(budget_variance, 0),
        "within_budget": total_capex <= (config.budget_inr * 1.05),
    }


def _estimate_raw_material_cost(config: FactoryConfig, simulation: SimulationResult) -> float:
    monthly_input_units = (
        simulation.monthly_input_units_required or simulation.effective_throughput_per_month
    )
    return monthly_input_units * config.selling_price_per_unit * config.raw_material_cost_ratio


def _estimate_maintenance_cost(config: FactoryConfig) -> float:
    return _machine_cost(config) * 0.055 / 12.0


def _estimate_inventory_carrying_cost(config: FactoryConfig, simulation: SimulationResult) -> float:
    raw_material = _estimate_raw_material_cost(config, simulation)
    fg_value = simulation.effective_throughput_per_month * config.selling_price_per_unit * 0.06
    return (raw_material + fg_value) * 0.012


def _estimate_qc_and_scrap_cost(config: FactoryConfig, simulation: SimulationResult) -> float:
    scrap_disposal_and_rework = (
        (simulation.monthly_scrap_units * 0.08 + simulation.monthly_rework_units * 0.04)
        * config.selling_price_per_unit
        * config.raw_material_cost_ratio
    )
    qc_consumables = simulation.effective_throughput_per_month * config.selling_price_per_unit * 0.006
    return scrap_disposal_and_rework + qc_consumables


def _estimate_depreciation_monthly(capex_breakdown: dict) -> float:
    machine_dep = capex_breakdown["machine_cost_inr"] / (8 * 12)
    civil_dep = capex_breakdown["civil_construction_inr"] / (20 * 12)
    misc_dep = capex_breakdown["misc_infra_inr"] / (10 * 12)
    return machine_dep + civil_dep + misc_dep


def estimate_opex(
    config: FactoryConfig,
    simulation: SimulationResult,
    capex_breakdown: dict,
) -> dict:
    labour_cost = simulation.total_workers * config.labour_cost_per_worker_month_inr
    power_cost = simulation.estimated_monthly_power_cost_inr
    raw_material = _estimate_raw_material_cost(config, simulation)
    maintenance = _estimate_maintenance_cost(config)
    inventory_carrying = _estimate_inventory_carrying_cost(config, simulation)
    qc_and_scrap = _estimate_qc_and_scrap_cost(config, simulation)

    direct_cogs = raw_material + labour_cost + power_cost + maintenance + qc_and_scrap
    overhead = (direct_cogs + inventory_carrying) * 0.065  # Admin, insurance, SG&A
    depreciation = _estimate_depreciation_monthly(capex_breakdown)

    cash_opex = direct_cogs + inventory_carrying + overhead
    total_opex = cash_opex + depreciation

    return {
        "labour_cost_monthly_inr": round(labour_cost, 0),
        "power_cost_monthly_inr": round(power_cost, 0),
        "raw_material_cost_monthly_inr": round(raw_material, 0),
        "maintenance_cost_monthly_inr": round(maintenance, 0),
        "inventory_carrying_cost_monthly_inr": round(inventory_carrying, 0),
        "qc_and_scrap_cost_monthly_inr": round(qc_and_scrap, 0),
        "depreciation_monthly_inr": round(depreciation, 0),
        "overhead_monthly_inr": round(overhead, 0),
        "direct_cogs_monthly_inr": round(direct_cogs, 0),
        "cash_opex_monthly_inr": round(cash_opex, 0),
        "total_opex_monthly_inr": round(total_opex, 0),
    }


def calculate_revenue_and_profit(
    config: FactoryConfig,
    simulation: SimulationResult,
    opex: dict,
) -> dict:
    good_units = max(simulation.effective_throughput_per_month, 1.0)
    monthly_revenue = simulation.effective_throughput_per_month * config.selling_price_per_unit

    gross_profit = monthly_revenue - opex["direct_cogs_monthly_inr"]
    ebitda = monthly_revenue - opex["cash_opex_monthly_inr"]
    net_profit = monthly_revenue - opex["total_opex_monthly_inr"]

    gross_margin = (gross_profit / monthly_revenue * 100.0) if monthly_revenue > 0 else 0.0
    ebitda_margin = (ebitda / monthly_revenue * 100.0) if monthly_revenue > 0 else 0.0
    net_margin = (net_profit / monthly_revenue * 100.0) if monthly_revenue > 0 else 0.0

    unit_cost = opex["total_opex_monthly_inr"] / good_units
    unit_profit = config.selling_price_per_unit - unit_cost

    return {
        "monthly_revenue_inr": round(monthly_revenue, 0),
        "monthly_ebitda_inr": round(ebitda, 0),
        "monthly_profit_inr": round(net_profit, 0),
        "gross_margin_percent": round(gross_margin, 1),
        "ebitda_margin_percent": round(ebitda_margin, 1),
        "net_margin_percent": round(net_margin, 1),
        "unit_cost_inr": round(unit_cost, 1),
        "unit_profit_inr": round(unit_profit, 1),
    }


def calculate_roi(total_capex: float, monthly_profit: float, monthly_ebitda: float) -> dict:
    """
    Payback period uses Operating Cash Flow (EBITDA) while Annual ROI uses Net Operating Profit.
    """
    cash_flow_monthly = max(monthly_ebitda, monthly_profit)
    if cash_flow_monthly <= 0 or total_capex <= 0:
        return {
            "break_even_months": 999.0,
            "annual_roi_percent": 0.0,
        }
    break_even_months = total_capex / cash_flow_monthly
    annual_roi = (max(monthly_profit, 0.0) * 12.0 / total_capex) * 100.0
    return {
        "break_even_months": round(break_even_months, 1),
        "annual_roi_percent": round(annual_roi, 1),
    }


def _build_scenario(
    label: str,
    units_factor: float,
    config: FactoryConfig,
    simulation: SimulationResult,
    base_capex: float,
    base_machine_cost: float,
) -> dict:
    scaled_good_units = simulation.effective_throughput_per_month * units_factor
    scaled_input_units = simulation.monthly_input_units_required * units_factor

    raw_material = scaled_input_units * config.selling_price_per_unit * config.raw_material_cost_ratio
    labour = simulation.total_workers * config.labour_cost_per_worker_month_inr * (0.80 + 0.20 * units_factor)
    power = simulation.estimated_monthly_power_cost_inr * (0.25 + 0.75 * units_factor)
    maintenance = base_machine_cost * (0.055 / 12.0) * (0.9 + 0.1 * units_factor)
    inventory_carrying = (raw_material + scaled_good_units * config.selling_price_per_unit * 0.06) * 0.012
    qc_and_scrap = (
        (simulation.monthly_scrap_units * units_factor * 0.08)
        * config.selling_price_per_unit
        * config.raw_material_cost_ratio
    ) + (scaled_good_units * config.selling_price_per_unit * 0.006)

    direct_cogs = raw_material + labour + power + maintenance + qc_and_scrap
    overhead = (direct_cogs + inventory_carrying) * 0.065

    scenario_capex = base_capex * (units_factor ** 0.55) if units_factor > 1.0 else base_capex * (0.9 + 0.1 * units_factor)
    depreciation = scenario_capex * 0.045 / 12.0

    cash_opex = direct_cogs + inventory_carrying + overhead
    total_opex = cash_opex + depreciation

    revenue = scaled_good_units * config.selling_price_per_unit
    ebitda = revenue - cash_opex
    profit = revenue - total_opex
    gross_margin = ((revenue - direct_cogs) / revenue * 100.0) if revenue > 0 else 0.0
    break_even = scenario_capex / ebitda if ebitda > 0 else 999.0
    roi = (max(profit, 0.0) * 12.0 / scenario_capex * 100.0) if scenario_capex > 0 else 0.0

    return {
        "label": label,
        "monthly_units": round(scaled_good_units, 0),
        "capex_inr": round(scenario_capex, 0),
        "monthly_opex_inr": round(total_opex, 0),
        "monthly_revenue_inr": round(revenue, 0),
        "monthly_profit_inr": round(profit, 0),
        "gross_margin_percent": round(gross_margin, 1),
        "break_even_months": round(break_even, 1),
        "annual_roi_percent": round(roi, 1),
    }


def full_financial_model(
    config: FactoryConfig,
    simulation: SimulationResult,
) -> FinancialSummary:
    capex_breakdown = estimate_capex(config, simulation)
    opex_breakdown = estimate_opex(config, simulation, capex_breakdown)
    revenue_data = calculate_revenue_and_profit(config, simulation, opex_breakdown)
    roi_data = calculate_roi(
        capex_breakdown["total_capex_inr"],
        revenue_data["monthly_profit_inr"],
        revenue_data["monthly_ebitda_inr"],
    )

    base_capex = capex_breakdown["total_capex_inr"]
    base_machine_cost = capex_breakdown["machine_cost_inr"]
    conservative = _build_scenario("Conservative (65%)", 0.65, config, simulation, base_capex, base_machine_cost)
    balanced = _build_scenario("Balanced (100%)", 1.00, config, simulation, base_capex, base_machine_cost)
    aggressive = _build_scenario("Expanded (135%)", 1.35, config, simulation, base_capex, base_machine_cost)

    return FinancialSummary(
        total_capex_inr=capex_breakdown["total_capex_inr"],
        budget_variance_inr=capex_breakdown["budget_variance_inr"],
        within_budget=capex_breakdown["within_budget"],
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
        monthly_ebitda_inr=revenue_data["monthly_ebitda_inr"],
        monthly_profit_inr=revenue_data["monthly_profit_inr"],
        gross_margin_percent=revenue_data["gross_margin_percent"],
        ebitda_margin_percent=revenue_data["ebitda_margin_percent"],
        net_margin_percent=revenue_data["net_margin_percent"],
        unit_cost_inr=revenue_data["unit_cost_inr"],
        unit_profit_inr=revenue_data["unit_profit_inr"],
        break_even_months=roi_data["break_even_months"],
        annual_roi_percent=roi_data["annual_roi_percent"],
        conservative=conservative,
        balanced=balanced,
        aggressive=aggressive,
    )