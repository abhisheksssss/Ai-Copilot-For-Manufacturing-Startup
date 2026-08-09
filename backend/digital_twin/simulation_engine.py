"""
Simulation Engine — Pure mathematical factory simulation.

This version moves beyond a simple min-capacity model by accounting for:
- setup / changeover losses
- planned maintenance
- downtime and minor stoppages
- OEE / speed losses
- yield and scrap losses
- rework pressure on effective output
"""
from .models import (
    FactoryConfig,
    ProcessStep,
    SimulationResult,
    StepCapacity,
)


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_percent(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _step_capacity_per_hour(step: ProcessStep) -> float:
    """Nominal hourly throughput for the step."""
    return step.machine.capacity_per_hour * step.machine.quantity


def _effective_runtime_hours_per_day(step: ProcessStep, config: FactoryConfig) -> float:
    """
    Estimate productive runtime after setup, maintenance, and downtime.

    Runtime logic:
    - start from planned daily hours
    - subtract setup loss for each shift
    - subtract planned maintenance allocated per day
    - apply downtime loss
    - apply OEE/performance loss
    """
    planned_hours = config.daily_hours
    setup_hours = (step.machine.setup_time_min * config.shifts_per_day) / 60.0
    maintenance_hours = step.machine.maintenance_hours_per_month / max(config.operating_days_per_month, 1)

    available_hours = max(planned_hours - setup_hours - maintenance_hours, 0.0)
    available_hours *= (1.0 - _safe_percent(step.machine.downtime_percent) / 100.0)
    productive_hours = available_hours * (_safe_percent(step.machine.oee_percent) / 100.0)
    return max(productive_hours, 0.0)


def _processed_units_per_day(step: ProcessStep, config: FactoryConfig) -> float:
    return _step_capacity_per_hour(step) * _effective_runtime_hours_per_day(step, config)


def _good_units_per_day(step: ProcessStep, config: FactoryConfig) -> float:
    processed = _processed_units_per_day(step, config)
    yield_factor = _safe_percent(step.yield_percent) / 100.0
    rework_factor = 1.0 + max(step.rework_percent, 0.0) / 100.0
    return processed * yield_factor / rework_factor


def _monthly_power_cost(config: FactoryConfig, steps: list[ProcessStep]) -> tuple[float, float]:
    """
    Returns (total_power_kw_including_utilities, monthly_cost_inr).
    Uses productive runtime rather than planned full-time runtime.
    """
    process_kwh_per_month = 0.0
    connected_load_kw = 0.0

    for step in steps:
        step_load_kw = step.machine.power_kw * step.machine.quantity
        connected_load_kw += step_load_kw
        productive_hours_day = _effective_runtime_hours_per_day(step, config)
        process_kwh_per_month += step_load_kw * productive_hours_day * config.operating_days_per_month

    # plant-level utilities: HVAC, compressors, lighting, IT rooms, etc.
    total_connected_load_kw = connected_load_kw * 1.25
    utility_kwh_per_month = process_kwh_per_month * 0.18
    total_kwh_per_month = process_kwh_per_month + utility_kwh_per_month
    monthly_cost = total_kwh_per_month * config.power_cost_per_kwh_inr

    return round(total_connected_load_kw, 1), round(monthly_cost, 0)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: STEP-LEVEL ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def analyze_step(
    step: ProcessStep,
    factory_config: FactoryConfig,
    effective_demand_per_day: float,
) -> StepCapacity:
    """Compute realistic step output and utilization."""
    theoretical_capacity_per_day = _step_capacity_per_hour(step) * factory_config.daily_hours
    runtime_hours = _effective_runtime_hours_per_day(step, factory_config)
    processed_units = _processed_units_per_day(step, factory_config)
    good_units = processed_units * (_safe_percent(step.yield_percent) / 100.0)
    rework_factor = 1.0 + max(step.rework_percent, 0.0) / 100.0
    quality_adjusted_output = good_units / rework_factor
    monthly_output = quality_adjusted_output * factory_config.operating_days_per_month

    utilization = min(
        (effective_demand_per_day / quality_adjusted_output * 100.0)
        if quality_adjusted_output > 0 else 0.0,
        100.0,
    )

    return StepCapacity(
        step_name=step.name,
        sequence=step.sequence,
        capacity_per_hour=round(_step_capacity_per_hour(step), 2),
        theoretical_capacity_per_day=round(theoretical_capacity_per_day, 2),
        effective_runtime_hours_per_day=round(runtime_hours, 2),
        actual_units_processed_per_day=round(processed_units, 2),
        actual_good_output_per_day=round(good_units, 2),
        quality_adjusted_output_per_day=round(quality_adjusted_output, 2),
        capacity_per_day=round(quality_adjusted_output, 2),
        capacity_per_month=round(monthly_output, 0),
        utilization_percent=round(utilization, 1),
        yield_percent=round(_safe_percent(step.yield_percent), 2),
        downtime_percent=round(_safe_percent(step.machine.downtime_percent), 2),
        oee_percent=round(_safe_percent(step.machine.oee_percent), 2),
        is_bottleneck=False,
        machine_count=step.machine.quantity,
        workers=step.workers_required,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: FACTORY-LEVEL SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

def run_full_simulation(config: FactoryConfig) -> SimulationResult:
    """
    Run the complete factory simulation.

    This version models realistic production losses before identifying the
    bottleneck, making the twin much closer to actual factory behavior.
    """
    if not config.processes:
        return _default_simulation(config)

    steps = sorted(config.processes, key=lambda s: s.sequence)
    target_per_day = config.target_daily_units

    step_daily_caps = {
        step.name: _good_units_per_day(step, config)
        for step in steps
    }

    effective_per_day = min(step_daily_caps.values()) if step_daily_caps else target_per_day
    effective_per_month = effective_per_day * config.operating_days_per_month

    bottleneck_name = min(step_daily_caps, key=step_daily_caps.get)
    bottleneck_cap = step_daily_caps[bottleneck_name]

    step_capacities: list[StepCapacity] = []
    for step in steps:
        sc = analyze_step(step, config, effective_per_day)
        sc.is_bottleneck = (step.name == bottleneck_name)
        step_capacities.append(sc)

    total_workers = sum(
        max(step.workers_required, step.min_operators_per_shift * config.shifts_per_day)
        for step in steps
    )
    total_power_kw, power_cost_monthly = _monthly_power_cost(config, steps)

    overall_yield_factor = 1.0
    for step in steps:
        overall_yield_factor *= (_safe_percent(step.yield_percent) / 100.0)
        overall_yield_factor /= (1.0 + max(step.rework_percent, 0.0) / 100.0)

    overall_yield_percent = overall_yield_factor * 100.0
    monthly_input_units_required = (
        effective_per_month / overall_yield_factor if overall_yield_factor > 0 else effective_per_month
    )
    monthly_scrap_units = max(monthly_input_units_required - effective_per_month, 0.0)
    capacity_utilization_percent = (
        (config.target_monthly_units / effective_per_month) * 100.0
        if effective_per_month > 0 else 0.0
    )

    production_gap = effective_per_month - config.target_monthly_units

    suggestions = _generate_suggestions(
        config=config,
        steps=steps,
        bottleneck_name=bottleneck_name,
        effective_per_day=effective_per_day,
        target_per_day=target_per_day,
    )

    return SimulationResult(
        effective_throughput_per_day=round(effective_per_day, 0),
        effective_throughput_per_month=round(effective_per_month, 0),
        target_met=effective_per_month >= config.target_monthly_units,
        production_gap=round(production_gap, 0),
        bottleneck_step=bottleneck_name,
        bottleneck_capacity_per_day=round(bottleneck_cap, 0),
        step_capacities=step_capacities,
        total_workers=total_workers,
        total_power_kw=total_power_kw,
        estimated_monthly_power_cost_inr=power_cost_monthly,
        overall_yield_percent=round(overall_yield_percent, 2),
        monthly_scrap_units=round(monthly_scrap_units, 0),
        monthly_input_units_required=round(monthly_input_units_required, 0),
        capacity_utilization_percent=round(capacity_utilization_percent, 1),
        optimization_suggestions=suggestions,
    )


def _default_simulation(config: FactoryConfig) -> SimulationResult:
    """Fallback when no processes were extracted — use rough estimates."""
    target_per_day = config.target_daily_units
    return SimulationResult(
        effective_throughput_per_day=round(target_per_day, 0),
        effective_throughput_per_month=round(config.target_monthly_units, 0),
        target_met=True,
        production_gap=0,
        bottleneck_step="Not analyzed",
        bottleneck_capacity_per_day=round(target_per_day, 0),
        step_capacities=[],
        total_workers=30,
        total_power_kw=300.0,
        estimated_monthly_power_cost_inr=300000.0,
        overall_yield_percent=95.0,
        monthly_scrap_units=round(config.target_monthly_units * 0.05, 0),
        monthly_input_units_required=round(config.target_monthly_units / 0.95, 0),
        capacity_utilization_percent=100.0,
        optimization_suggestions=["Provide more process-level details for a refined simulation."],
    )


def _generate_suggestions(
    config: FactoryConfig,
    steps: list[ProcessStep],
    bottleneck_name: str,
    effective_per_day: float,
    target_per_day: float,
) -> list[str]:
    """Generate actionable optimization suggestions."""
    suggestions: list[str] = []
    bottleneck_step = next((s for s in steps if s.name == bottleneck_name), None)

    if not bottleneck_step:
        return suggestions

    if effective_per_day >= target_per_day:
        suggestions.append(
            f"✅ Current configuration meets the production target at about {effective_per_day:.0f} good units/day."
        )
    else:
        cap_single_machine_day = max(
            bottleneck_step.machine.capacity_per_hour * _effective_runtime_hours_per_day(bottleneck_step, config),
            1.0,
        )
        deficit_per_day = target_per_day - effective_per_day
        extra_machines = max(1, int(deficit_per_day / cap_single_machine_day) + 1)

        suggestions.append(
            f"⚠️ Bottleneck: '{bottleneck_name}' limits output to {effective_per_day:.0f} good units/day "
            f"against a target of {target_per_day:.0f} units/day."
        )
        suggestions.append(
            f"💡 Adding about {extra_machines} more machine(s) to '{bottleneck_name}' or parallelizing this step "
            f"is the fastest way to close the throughput gap."
        )

    if bottleneck_step.machine.downtime_percent > 8:
        suggestions.append(
            f"🔧 Downtime at '{bottleneck_name}' is high ({bottleneck_step.machine.downtime_percent:.0f}%). "
            f"Preventive maintenance and spare-parts planning could recover output without new CAPEX."
        )

    if bottleneck_step.machine.setup_time_min >= 30:
        suggestions.append(
            f"⏱️ Setup time at '{bottleneck_name}' is material ({bottleneck_step.machine.setup_time_min:.0f} min/shift). "
            f"SMED/changeover reduction can unlock more daily capacity."
        )

    low_yield_steps = [s for s in steps if s.yield_percent < 97]
    if low_yield_steps:
        worst_yield = min(low_yield_steps, key=lambda s: s.yield_percent)
        suggestions.append(
            f"🧪 Improve first-pass yield at '{worst_yield.name}' ({worst_yield.yield_percent:.1f}% yield) "
            f"to reduce scrap and improve effective throughput."
        )

    sorted_by_cap = sorted(steps, key=lambda s: _good_units_per_day(s, config))
    if len(sorted_by_cap) > 1:
        second_bottleneck = sorted_by_cap[1]
        second_cap = _good_units_per_day(second_bottleneck, config)
        if second_bottleneck.name != bottleneck_name and second_cap < target_per_day:
            suggestions.append(
                f"🔍 After debottlenecking '{bottleneck_name}', the next likely constraint is "
                f"'{second_bottleneck.name}' at roughly {second_cap:.0f} good units/day."
            )

    return suggestions
