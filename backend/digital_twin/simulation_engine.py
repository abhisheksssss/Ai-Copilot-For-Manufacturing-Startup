"""
Simulation Engine — Pure mathematical factory simulation.

No external simulation library required. All calculations are deterministic
algebra over the factory configuration produced by the LLM parser.

Key computations:
  - Capacity per process step (machines × rate × hours)
  - Bottleneck detection (minimum throughput across all steps)
  - Machine utilization percentage
  - Workforce and power totals
  - Optimization suggestions (add machines to remove bottleneck)
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

def _step_capacity_per_hour(step: ProcessStep) -> float:
    """
    Calculate how many units this step can handle per hour.
    
    capacity_per_hour is defined per machine.
    Total = capacity_per_hour × quantity
    """
    return step.machine.capacity_per_hour * step.machine.quantity


def _step_capacity_per_day(step: ProcessStep, daily_hours: float) -> float:
    """Units this step can produce in a full working day."""
    return _step_capacity_per_hour(step) * daily_hours


def _step_capacity_per_month(step: ProcessStep, daily_hours: float, operating_days: int) -> float:
    return _step_capacity_per_day(step, daily_hours) * operating_days


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: STEP-LEVEL ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def analyze_step(
    step: ProcessStep,
    factory_config: FactoryConfig,
    effective_demand_per_day: float,
) -> StepCapacity:
    """
    Compute capacity and utilization for a single process step.
    
    Utilization is calculated against the effective demand (limited by
    bottleneck), not the target, to give a realistic picture.
    """
    daily_hours = factory_config.daily_hours
    cap_per_hour = _step_capacity_per_hour(step)
    cap_per_day = _step_capacity_per_day(step, daily_hours)
    cap_per_month = _step_capacity_per_month(
        step, daily_hours, factory_config.operating_days_per_month
    )

    utilization = min(
        (effective_demand_per_day / cap_per_day * 100) if cap_per_day > 0 else 0,
        100.0
    )

    return StepCapacity(
        step_name=step.name,
        sequence=step.sequence,
        capacity_per_hour=round(cap_per_hour, 2),
        capacity_per_day=round(cap_per_day, 2),
        capacity_per_month=round(cap_per_month, 0),
        utilization_percent=round(utilization, 1),
        is_bottleneck=False,  # Will be set after all steps are analyzed
        machine_count=step.machine.quantity,
        workers=step.workers_required,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: FACTORY-LEVEL SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

def run_full_simulation(config: FactoryConfig) -> SimulationResult:
    """
    Run the complete factory simulation.
    
    Algorithm:
    1. Sort process steps by sequence
    2. Calculate each step's capacity per day
    3. Effective throughput = min(all step capacities) — the bottleneck
    4. Mark the bottleneck step
    5. Recalculate utilization based on effective throughput
    6. Compute workforce, power, and optimization suggestions
    """
    if not config.processes:
        # Default minimal simulation when no processes defined
        return _default_simulation(config)

    daily_hours = config.daily_hours
    target_per_day = config.target_daily_units

    # Sort by sequence
    steps = sorted(config.processes, key=lambda s: s.sequence)

    # First pass: get raw capacities per day
    step_daily_caps = {
        step.name: _step_capacity_per_day(step, daily_hours)
        for step in steps
    }

    # Effective throughput is constrained by the weakest link
    effective_per_day = min(step_daily_caps.values()) if step_daily_caps else target_per_day
    effective_per_month = effective_per_day * config.operating_days_per_month

    # Find bottleneck
    bottleneck_name = min(step_daily_caps, key=step_daily_caps.get)
    bottleneck_cap = step_daily_caps[bottleneck_name]

    # Second pass: build StepCapacity objects with accurate utilization
    step_capacities: list[StepCapacity] = []
    for step in steps:
        sc = analyze_step(step, config, effective_per_day)
        sc.is_bottleneck = (step.name == bottleneck_name)
        step_capacities.append(sc)

    # Workforce and power totals
    total_workers = sum(s.workers_required for s in steps)
    total_power_kw = sum(
        s.machine.power_kw * s.machine.quantity for s in steps
    )
    # Add HVAC, lighting (estimated at 30% overhead)
    total_power_kw *= 1.30

    # Monthly power cost (avg ₹8/kWh industrial tariff in India)
    kwh_per_month = total_power_kw * daily_hours * config.operating_days_per_month
    power_cost_monthly = kwh_per_month * 8.0

    # Production gap vs target
    production_gap = effective_per_month - config.target_monthly_units

    # Optimization suggestions
    suggestions = _generate_suggestions(steps, bottleneck_name, effective_per_day, target_per_day)

    return SimulationResult(
        effective_throughput_per_day=round(effective_per_day, 0),
        effective_throughput_per_month=round(effective_per_month, 0),
        target_met=effective_per_month >= config.target_monthly_units,
        production_gap=round(production_gap, 0),
        bottleneck_step=bottleneck_name,
        bottleneck_capacity_per_day=round(bottleneck_cap, 0),
        step_capacities=step_capacities,
        total_workers=total_workers,
        total_power_kw=round(total_power_kw, 1),
        estimated_monthly_power_cost_inr=round(power_cost_monthly, 0),
        optimization_suggestions=suggestions,
    )


def _default_simulation(config: FactoryConfig) -> SimulationResult:
    """Fallback when no processes were extracted — use rough estimates."""
    target_per_day = config.target_daily_units
    return SimulationResult(
        effective_throughput_per_day=target_per_day,
        effective_throughput_per_month=config.target_monthly_units,
        target_met=True,
        production_gap=0,
        bottleneck_step="Not analyzed",
        bottleneck_capacity_per_day=target_per_day,
        step_capacities=[],
        total_workers=30,
        total_power_kw=300.0,
        estimated_monthly_power_cost_inr=300000.0,
        optimization_suggestions=["Provide more details for a refined simulation."],
    )


def _generate_suggestions(
    steps: list[ProcessStep],
    bottleneck_name: str,
    effective_per_day: float,
    target_per_day: float,
) -> list[str]:
    """
    Generate actionable optimization suggestions by iteratively simulating
    adding machines to the bottleneck until the target is met.
    """
    suggestions = []
    bottleneck_step = next((s for s in steps if s.name == bottleneck_name), None)

    if not bottleneck_step:
        return suggestions

    if effective_per_day >= target_per_day:
        suggestions.append(
            f"✅ Current configuration meets the production target. "
            f"Factory can produce {effective_per_day:.0f} units/day."
        )
        return suggestions

    # How many extra machines are needed?
    cap_per_machine_per_day = (
        bottleneck_step.machine.capacity_per_hour
        * (bottleneck_step.machine.quantity or 1)
        / (bottleneck_step.machine.quantity or 1)
    )
    # capacity per day per machine
    hours_per_day = 16  # assume 2 shifts
    cap_single_machine_day = bottleneck_step.machine.capacity_per_hour * hours_per_day
    deficit_per_day = target_per_day - effective_per_day
    extra_machines = max(1, int(deficit_per_day / cap_single_machine_day) + 1)

    suggestions.append(
        f"⚠️ Bottleneck: '{bottleneck_name}' limits output to {effective_per_day:.0f} units/day "
        f"(target: {target_per_day:.0f} units/day)."
    )
    suggestions.append(
        f"💡 Adding {extra_machines} more machine(s) to '{bottleneck_name}' "
        f"should resolve the bottleneck."
    )

    # Check if adding machines to bottleneck would reveal the next bottleneck
    sorted_by_cap = sorted(steps, key=lambda s: _step_capacity_per_day(s, hours_per_day))
    if len(sorted_by_cap) > 1:
        second_bottleneck = sorted_by_cap[1]
        if second_bottleneck.name != bottleneck_name:
            second_cap = _step_capacity_per_day(second_bottleneck, hours_per_day)
            if second_cap < target_per_day:
                suggestions.append(
                    f"🔍 After resolving '{bottleneck_name}', the next bottleneck will be "
                    f"'{second_bottleneck.name}' at {second_cap:.0f} units/day."
                )

    return suggestions
