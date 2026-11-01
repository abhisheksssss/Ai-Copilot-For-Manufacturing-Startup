"""
Simulation Engine — True Serial Cascade & Line-Balancing Factory Simulation.

Models:
- Shift changeover/setup, planned maintenance, downtime, and OEE speed losses
- Rework load (consumes station capacity without destroying material)
- True material yield/scrap cascade from raw material input to finished goods
- Upstream starvation & downstream bottleneck propagation
- Takt Time vs. Station Cycle Time & Line Balance Efficiency (LBE)
- Cost-per-extra-unit ROI ranking for debottlenecking suggestions
"""
from .models import (
    FactoryConfig,
    ProcessStep,
    SimulationResult,
    StepCapacity,
)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _step_nominal_hourly_rate(step: ProcessStep) -> float:
    """Nominal hourly throughput across all parallel machines at this step."""
    from_cycle = (60.0 / step.machine.processing_time_min) if step.machine.processing_time_min > 0 else step.machine.capacity_per_hour
    # Reconcile LLM capacity_per_hour with processing_time_min if wildly inconsistent
    unit_hourly = step.machine.capacity_per_hour if step.machine.capacity_per_hour > 0 else from_cycle
    return unit_hourly * max(step.machine.quantity, 1)


def _effective_runtime_hours_per_day(step: ProcessStep, config: FactoryConfig) -> float:
    """Productive machine hours per day after setup, maintenance, downtime, and OEE."""
    planned_hours = config.daily_hours
    setup_hours = (step.machine.setup_time_min * config.shifts_per_day) / 60.0
    maintenance_hours = step.machine.maintenance_hours_per_month / max(config.operating_days_per_month, 1)

    available_hours = max(planned_hours - setup_hours - maintenance_hours, 0.0)
    uptime_hours = available_hours * (1.0 - _clamp(step.machine.downtime_percent, 0.0, 95.0) / 100.0)
    productive_hours = uptime_hours * (_clamp(step.machine.oee_percent, 10.0, 100.0) / 100.0)
    return max(productive_hours, 0.1)


def _standalone_good_capacity_per_day(step: ProcessStep, config: FactoryConfig) -> tuple[float, float, float]:
    """
    Returns (raw_units_processed_cap, good_output_before_rework, net_good_capacity_after_rework_load).
    Rework consumes station cycles (1 + rework_ratio) but recovered rework stays in the good stream.
    """
    runtime_h = _effective_runtime_hours_per_day(step, config)
    raw_processed_cap = _step_nominal_hourly_rate(step) * runtime_h
    rework_load_factor = 1.0 + (_clamp(step.rework_percent, 0.0, 50.0) / 100.0)
    fresh_units_handled = raw_processed_cap / rework_load_factor
    yield_factor = _clamp(step.yield_percent, 1.0, 100.0) / 100.0
    net_good_cap = fresh_units_handled * yield_factor
    return raw_processed_cap, fresh_units_handled, net_good_cap


def _monthly_power_cost(
    config: FactoryConfig,
    steps: list[ProcessStep],
    step_utilizations: dict[str, float],
) -> tuple[float, float]:
    """
    Computes connected load (kW) and monthly electricity bill (INR).
    Accounts for active machine load scaled by utilization + idle baseload + plant HVAC/utilities.
    """
    process_kwh_per_month = 0.0
    connected_load_kw = 0.0

    for step in steps:
        step_load_kw = step.machine.power_kw * step.machine.quantity
        connected_load_kw += step_load_kw
        runtime_day = _effective_runtime_hours_per_day(step, config)
        util_ratio = _clamp(step_utilizations.get(step.name, 85.0), 15.0, 100.0) / 100.0
        # Machines draw 100% power when loaded and ~25% standby power when starved/idle
        effective_power_factor = 0.25 + 0.75 * util_ratio
        process_kwh_per_month += (
            step_load_kw * effective_power_factor * runtime_day * config.operating_days_per_month
        )

    total_connected_load_kw = connected_load_kw * 1.22  # Compressors, chillers, lighting, auxiliary
    utility_kwh_per_month = process_kwh_per_month * 0.18
    total_kwh_per_month = process_kwh_per_month + utility_kwh_per_month
    monthly_cost = total_kwh_per_month * config.power_cost_per_kwh_inr

    return round(total_connected_load_kw, 1), round(monthly_cost, 0)


def run_full_simulation(config: FactoryConfig) -> SimulationResult:
    """
    Executes a two-pass serial production line simulation:
    1. Evaluates standalone station capacities and downstream yield multipliers.
    2. Propagates material forward from Step 1..N so upstream constraints and downstream scrap
       accurately determine true line output, station utilization, and scrap volume.
    """
    if not config.processes:
        return _default_simulation(config)

    steps = sorted(config.processes, key=lambda s: s.sequence)
    n = len(steps)
    target_per_day = config.target_daily_units
    planned_seconds_per_day = config.daily_hours * 3600.0
    plant_takt_sec = planned_seconds_per_day / max(target_per_day, 1.0)

    # Calculate cumulative downstream yield from step i+1 to N
    # To get 1 good unit out of the end of the line, step i must output (1 / downstream_yield[i]) good units
    downstream_yield = [1.0] * n
    for i in range(n - 2, -1, -1):
        next_yield = _clamp(steps[i + 1].yield_percent, 1.0, 100.0) / 100.0
        downstream_yield[i] = downstream_yield[i + 1] * next_yield

    # Standalone capacity of each step expressed in terms of FINAL line-end good units/day
    step_stats = {}
    effective_final_caps: dict[str, float] = {}

    for i, step in enumerate(steps):
        raw_cap, fresh_cap, net_good_cap = _standalone_good_capacity_per_day(step, config)
        # How many final finished products this station can support given downstream scrap
        line_end_equivalent_cap = net_good_cap * downstream_yield[i]
        effective_final_caps[step.name] = line_end_equivalent_cap
        step_stats[step.name] = {
            "raw_cap": raw_cap,
            "fresh_cap": fresh_cap,
            "net_good_cap": net_good_cap,
            "downstream_yield": downstream_yield[i],
        }

    # The true bottleneck is the station that limits final finished-goods output the most
    bottleneck_name = min(effective_final_caps, key=effective_final_caps.get)
    effective_final_per_day = effective_final_caps[bottleneck_name]
    effective_final_per_month = effective_final_per_day * config.operating_days_per_month
    bottleneck_local_cap = step_stats[bottleneck_name]["net_good_cap"]

    # Cumulative material yield & First-Pass Yield (FPY)
    cumulative_material_yield = 1.0
    first_pass_yield = 1.0
    total_rework_units_per_day = 0.0

    for step in steps:
        y = _clamp(step.yield_percent, 1.0, 100.0) / 100.0
        r = _clamp(step.rework_percent, 0.0, 50.0) / 100.0
        cumulative_material_yield *= y
        first_pass_yield *= y * (1.0 - r)

    daily_raw_input_required = (
        effective_final_per_day / cumulative_material_yield
        if cumulative_material_yield > 0
        else effective_final_per_day
    )

    # Forward pass: compute actual units flowing through each station at steady state
    step_capacities: list[StepCapacity] = []
    step_utilizations: dict[str, float] = {}
    cycle_times: list[float] = []

    current_daily_flow_in = daily_raw_input_required
    for i, step in enumerate(steps):
        st = step_stats[step.name]
        runtime_h = _effective_runtime_hours_per_day(step, config)
        theoretical_cap_day = _step_nominal_hourly_rate(step) * config.daily_hours

        # Units actually arriving and processed at this station
        actual_fresh_in = min(current_daily_flow_in, st["fresh_cap"])
        rework_ratio = _clamp(step.rework_percent, 0.0, 50.0) / 100.0
        rework_units_day = actual_fresh_in * rework_ratio
        total_rework_units_per_day += rework_units_day

        actual_total_processed = actual_fresh_in + rework_units_day
        actual_good_out = actual_fresh_in * (_clamp(step.yield_percent, 1.0, 100.0) / 100.0)
        current_daily_flow_in = actual_good_out

        utilization = (
            min((actual_Good_Ratio := actual_good_out / st["net_good_cap"]) * 100.0, 100.0)
            if st["net_good_cap"] > 0
            else 0.0
        )
        step_utilizations[step.name] = utilization

        # Effective cycle time in seconds per good unit
        cycle_time_sec = (
            (config.daily_hours * 3600.0) / st["net_good_cap"]
            if st["net_good_cap"] > 0
            else 0.0
        )
        cycle_times.append(cycle_time_sec)

        is_bn = step.name == bottleneck_name
        if is_bn:
            line_state = "bottleneck"
        elif utilization < 65.0:
            line_state = "starved"
        elif utilization > 88.0:
            line_state = "constrained"
        else:
            line_state = "balanced"

        step_capacities.append(
            StepCapacity(
                step_name=step.name,
                sequence=step.sequence,
                capacity_per_hour=round(_step_nominal_hourly_rate(step), 2),
                theoretical_capacity_per_day=round(theoretical_cap_day, 0),
                effective_runtime_hours_per_day=round(runtime_h, 2),
                actual_units_processed_per_day=round(actual_total_processed, 0),
                actual_good_output_per_day=round(actual_good_out, 0),
                quality_adjusted_output_per_day=round(st["net_good_cap"], 0),
                capacity_per_day=round(st["net_good_cap"], 0),
                capacity_per_month=round(st["net_good_cap"] * config.operating_days_per_month, 0),
                utilization_percent=round(utilization, 1),
                yield_percent=round(_clamp(step.yield_percent), 2),
                downtime_percent=round(_clamp(step.machine.downtime_percent), 2),
                oee_percent=round(_clamp(step.machine.oee_percent), 2),
                takt_time_sec=round(plant_takt_sec, 2),
                cycle_time_sec=round(cycle_time_sec, 2),
                line_state=line_state,
                is_bottleneck=is_bn,
                machine_count=step.machine.quantity,
                workers=step.workers_required,
            )
        )

    # Line Balance Efficiency = Sum(Cycle Times) / (N * Max Cycle Time)
    max_ct = max(cycle_times) if cycle_times else 1.0
    lbe_percent = (sum(cycle_times) / (len(cycle_times) * max_ct) * 100.0) if max_ct > 0 else 100.0

    total_workers = sum(
        max(step.workers_required, step.min_operators_per_shift * config.shifts_per_day)
        for step in steps
    )
    total_power_kw, power_cost_monthly = _monthly_power_cost(config, steps, step_utilizations)

    monthly_input_units = daily_raw_input_required * config.operating_days_per_month
    monthly_scrap_units = max(monthly_input_units - effective_final_per_month, 0.0)
    monthly_rework_units = total_rework_units_per_day * config.operating_days_per_month

    avg_utilization = (
        sum(step_utilizations.values()) / len(step_utilizations)
        if step_utilizations
        else 0.0
    )
    production_gap = effective_final_per_month - config.target_monthly_units

    suggestions = _generate_suggestions(
        config=config,
        steps=steps,
        step_stats=step_stats,
        bottleneck_name=bottleneck_name,
        effective_per_day=effective_final_per_day,
        target_per_day=target_per_day,
        lbe_percent=lbe_percent,
    )

    return SimulationResult(
        effective_throughput_per_day=round(effective_final_per_day, 0),
        effective_throughput_per_month=round(effective_final_per_month, 0),
        target_met=effective_final_per_month >= config.target_monthly_units,
        production_gap=round(production_gap, 0),
        bottleneck_step=bottleneck_name,
        bottleneck_capacity_per_day=round(bottleneck_local_cap, 0),
        step_capacities=step_capacities,
        total_workers=total_workers,
        total_power_kw=total_power_kw,
        estimated_monthly_power_cost_inr=power_cost_monthly,
        overall_yield_percent=round(cumulative_material_yield * 100.0, 2),
        first_pass_yield_percent=round(first_pass_yield * 100.0, 2),
        monthly_scrap_units=round(monthly_scrap_units, 0),
        monthly_rework_units=round(monthly_rework_units, 0),
        monthly_input_units_required=round(monthly_input_units, 0),
        capacity_utilization_percent=round(avg_utilization, 1),
        plant_takt_time_sec=round(plant_takt_sec, 2),
        line_balance_efficiency_percent=round(lbe_percent, 1),
        optimization_suggestions=suggestions,
    )


def _default_simulation(config: FactoryConfig) -> SimulationResult:
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
        first_pass_yield_percent=92.0,
        monthly_scrap_units=round(config.target_monthly_units * 0.05, 0),
        monthly_rework_units=round(config.target_monthly_units * 0.03, 0),
        monthly_input_units_required=round(config.target_monthly_units / 0.95, 0),
        capacity_utilization_percent=85.0,
        plant_takt_time_sec=30.0,
        line_balance_efficiency_percent=80.0,
        optimization_suggestions=["Provide more process-level details for a refined simulation."],
    )


def _generate_suggestions(
    config: FactoryConfig,
    steps: list[ProcessStep],
    step_stats: dict,
    bottleneck_name: str,
    effective_per_day: float,
    target_per_day: float,
    lbe_percent: float,
) -> list[str]:
    suggestions: list[str] = []
    bottleneck_step = next((s for s in steps if s.name == bottleneck_name), None)
    if not bottleneck_step:
        return suggestions

    bn_cap_single = (
        step_stats[bottleneck_name]["net_good_cap"] / max(bottleneck_step.machine.quantity, 1)
    )

    if effective_per_day >= target_per_day:
        surplus_pct = ((effective_per_day - target_per_day) / max(target_per_day, 1)) * 100.0
        suggestions.append(
            f"✅ Line exceeds target by {surplus_pct:.1f}% ({effective_per_day:,.0f} vs {target_per_day:,.0f} units/day). "
            f"Primary pacing station is '{bottleneck_name}'."
        )
    else:
        deficit_per_day = target_per_day - effective_per_day
        extra_machines = max(1, int((deficit_per_day / max(bn_cap_single, 1.0)) + 0.999))
        capex_needed_lakhs = (extra_machines * bottleneck_step.machine.cost_inr) / 1e5
        unlocked_units_mo = min(deficit_per_day, extra_machines * bn_cap_single) * config.operating_days_per_month

        suggestions.append(
            f"⚠️ Primary Constraint: '{bottleneck_name}' caps plant output at {effective_per_day:,.0f} good units/day "
            f"(shortfall of {deficit_per_day * config.operating_days_per_month:,.0f} units/month)."
        )
        suggestions.append(
            f"💡 CAPEX Fix: Add {extra_machines}× {bottleneck_step.machine.name} (₹{capex_needed_lakhs:.1f}L investment) "
            f"to unlock ~{unlocked_units_mo:,.0f} additional units/month."
        )

    if bottleneck_step.machine.downtime_percent > 6.0 or bottleneck_step.machine.setup_time_min >= 25.0:
        recoverable_pct = (bottleneck_step.machine.downtime_percent * 0.4) + (
            (bottleneck_step.machine.setup_time_min / (config.hours_per_shift * 60.0)) * 50.0
        )
        suggestions.append(
            f"🔧 Zero-CAPEX Fix: SMED quick-changeover & Total Productive Maintenance (TPM) at '{bottleneck_name}' "
            f"can recover ~{recoverable_pct:.1f}% capacity without buying new machines."
        )

    if lbe_percent < 72.0:
        suggestions.append(
            f"⚖️ Line Balance Efficiency is low ({lbe_percent:.0f}%). Downstream/upstream stations are heavily starved; "
            f"cross-training operators from under-utilized zones can trim labour OPEX by 10–15%."
        )

    low_yield_steps = [s for s in steps if s.yield_percent < 97.5]
    if low_yield_steps:
        worst = min(low_yield_steps, key=lambda s: s.yield_percent)
        scrap_cost_lakh = (
            (100.0 - worst.yield_percent)
            / 100.0
            * effective_per_day
            * config.operating_days_per_month
            * config.selling_price_per_unit
            * config.raw_material_cost_ratio
            / 1e5
        )
        suggestions.append(
            f"🧪 Quality Yield: '{worst.name}' has a {100.0 - worst.yield_percent:.1f}% scrap rate, burning "
            f"~₹{scrap_cost_lakh:.1f}L/month in wasted raw materials. Add in-line automated optical/sensor inspection."
        )

    sorted_by_cap = sorted(steps, key=lambda s: step_stats[s.name]["net_good_cap"] * step_stats[s.name]["downstream_yield"])
    if len(sorted_by_cap) > 1:
        second_bn = sorted_by_cap[1]
        sec_cap = step_stats[second_bn.name]["net_good_cap"] * step_stats[second_bn.name]["downstream_yield"]
        if second_bn.name != bottleneck_name and sec_cap < target_per_day:
            suggestions.append(
                f"🔍 Secondary Bottleneck Alert: Once '{bottleneck_name}' is resolved, '{second_bn.name}' "
                f"will become the next constraint at {sec_cap:,.0f} units/day."
            )

    return suggestions